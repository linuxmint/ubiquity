import subprocess

import dbus


NM = 'org.freedesktop.NetworkManager'
NM_DEVICE = 'org.freedesktop.NetworkManager.Device'
NM_DEVICE_WIFI = 'org.freedesktop.NetworkManager.Device.Wireless'
NM_AP = 'org.freedesktop.NetworkManager.AccessPoint'
NM_SETTINGS = 'org.freedesktop.NetworkManager.Settings'
NM_SETTINGS_CONN = 'org.freedesktop.NetworkManager.Settings.Connection'
NM_SETTINGS_PATH = '/org/freedesktop/NetworkManager/Settings'
NM_ERROR_NOSECRETS = 'org.freedesktop.NetworkManager.AgentManager.NoSecrets'
DEVICE_TYPE_WIFI = 2
NM_STATE_DISCONNECTED = 20
NM_STATE_CONNECTING = 40
NM_STATE_CONNECTED_GLOBAL = 70


# TODO: DBus exceptions.  Catch 'em all.

def decode_ssid(characters):
    return bytearray(characters).decode('UTF-8', 'replace')


def get_prop(obj, iface, prop):
    try:
        return obj.Get(iface, prop, dbus_interface=dbus.PROPERTIES_IFACE)
    except dbus.DBusException as e:
        if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownMethod':
            return None
        else:
            raise


def get_vendor_and_model(udi):
    vendor = ''
    model = ''
    cmd = ['/sbin/udevadm', 'info', '--path=%s' % udi, '--query=property']
    with open('/dev/null', 'w') as devnull:
        out = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=devnull,
            universal_newlines=True)
        out = out.communicate()
    if not out[1]:
        for prop in out[0].split('\n'):
            if prop.startswith('ID_VENDOR_FROM_DATABASE'):
                vendor = prop.split('ID_VENDOR_FROM_DATABASE=')[1]
            elif prop.startswith('ID_MODEL_FROM_DATABASE'):
                model = prop.split('ID_MODEL_FROM_DATABASE=')[1]
    return (vendor, model)


def wireless_hardware_present():
    # NetworkManager keeps DBus objects for wireless devices around even when
    # the hardware switch is off.
    bus = dbus.SystemBus()
    manager = bus.get_object(NM, '/org/freedesktop/NetworkManager')
    try:
        devices = manager.GetDevices()
    except dbus.DBusException:
        return False
    for device_path in devices:
        device_obj = bus.get_object(NM, device_path)
        if get_prop(device_obj, NM_DEVICE, 'DeviceType') == DEVICE_TYPE_WIFI:
            return True
    return False


class QueuedCaller(object):
    """
    Abstract class providing queued calls.

    When 'start()' is called, implementation must ensure 'callback' is called
    after 'timeout' milliseconds.
    """
    def __init__(self, timeout, callback):
        self.timeout = timeout
        self.callback = callback

    def start(self):
        raise NotImplementedError


class NetworkStore(object):
    """
    Abstract class which stores the tree of network devices and their
    associated access-points.
    """
    def get_device_ids(self):
        raise NotImplementedError

    def add_device(self, devid, vendor, model):
        raise NotImplementedError

    def has_device(self, devid):
        raise NotImplementedError

    def remove_devices_not_in(self, devids):
        raise NotImplementedError

    def add_ap(self, devid, ssid, secure, strength):
        raise NotImplementedError

    def has_ap(self, devid, ssid):
        raise NotImplementedError

    def set_ap_strength(self, devid, ssid, strength):
        raise NotImplementedError

    def remove_aps_not_in(self, devid, ssids):
        raise NotImplementedError


class NetworkManager:
    def __init__(self, model, queued_caller_class, state_changed=None):
        self.model = model
        self.build_cache_caller = queued_caller_class(500, self.build_cache)
        self.start(state_changed)
        self.active_connection = None
        self.active_device_obj = None
        self.active_conn = None

    def start(self, state_changed=None):
        self.bus = dbus.SystemBus()
        self.manager = self.bus.get_object(
            NM, '/org/freedesktop/NetworkManager')
        add = self.bus.add_signal_receiver
        add(self.queue_build_cache, 'AccessPointAdded', NM_DEVICE_WIFI, NM)
        add(self.queue_build_cache, 'AccessPointRemoved', NM_DEVICE_WIFI, NM)
        if state_changed:
            add(state_changed, 'StateChanged', NM, NM)
        add(self.queue_build_cache, 'DeviceAdded', NM, NM)
        add(self.queue_build_cache, 'DeviceRemoved', NM, NM)
        add(self.properties_changed, 'PropertiesChanged', NM_AP,
            path_keyword='path')
        self.build_cache()
        self.build_passphrase_cache()

    def get_state(self):
        return self.manager.state()

    def is_connected(self, device, ap):
        device_obj = self.bus.get_object(NM, device)
        connectedap = get_prop(device_obj, NM_DEVICE_WIFI, 'ActiveAccessPoint')
        if not connectedap:
            return False
        connect_obj = self.bus.get_object(NM, connectedap)
        ssid = get_prop(connect_obj, NM_AP, 'Ssid')
        if ssid:
            return ap == decode_ssid(ssid)
        else:
            return False

    def connect_to_ap(self, device, ap, passphrase=None):
        device_obj = self.bus.get_object(NM, device)
        ap_list = device_obj.GetAccessPoints(dbus_interface=NM_DEVICE_WIFI)
        saved_strength = 0
        saved_path = ''
        for ap_path in ap_list:
            ap_obj = self.bus.get_object(NM, ap_path)
            ssid = get_prop(ap_obj, NM_AP, 'Ssid')
            if ssid:
                strength = get_prop(ap_obj, NM_AP, 'Strength')
                if decode_ssid(ssid) == ap and saved_strength < strength:
                    # Connect to the strongest AP.
                    saved_strength = strength
                    saved_path = ap_path
        if not saved_path:
            return

        obj = dbus.Dictionary(signature='sa{sv}')
        if passphrase:
            obj['802-11-wireless-security'] = {'psk': passphrase}
        self.active_conn, self.active_connection = (
            self.manager.AddAndActivateConnection(
                obj, dbus.ObjectPath(device), dbus.ObjectPath(saved_path),
                signature='a{sa{sv}}oo'))
        self.active_device_obj = device_obj

    def disconnect_from_ap(self):
        if self.active_connection is not None:
            self.manager.DeactivateConnection(self.active_connection)
            self.active_connection = None
        if self.active_device_obj is not None:
            self.active_device_obj.Disconnect()
            self.active_device_obj = None
        if self.active_conn is not None:
            conn_obj = self.bus.get_object(NM, self.active_conn)
            conn_obj.Delete()
            self.active_conn = None

    def build_passphrase_cache(self):
        self.passphrases_cache = {}
        settings_obj = self.bus.get_object(NM, NM_SETTINGS_PATH)
        for conn in settings_obj.ListConnections(dbus_interface=NM_SETTINGS):
            conn_obj = self.bus.get_object(NM, conn)
            props = conn_obj.GetSettings(dbus_interface=NM_SETTINGS_CONN)
            if '802-11-wireless-security' in props:
                try:
                    sec = conn_obj.GetSecrets('802-11-wireless-security',
                                              dbus_interface=NM_SETTINGS_CONN)
                    sec = list(sec['802-11-wireless-security'].values())[0]
                    ssid = decode_ssid(props['802-11-wireless']['ssid'])
                    self.passphrases_cache[ssid] = sec
                except dbus.exceptions.DBusException as e:
                    if e.get_dbus_name() != NM_ERROR_NOSECRETS:
                        raise

    def queue_build_cache(self, *args):
        self.build_cache_caller.start()

    def properties_changed(self, props, path=None):
        if 'Strength' in props:
            ap_obj = self.bus.get_object(NM, path)
            ssid = get_prop(ap_obj, NM_AP, 'Ssid')
            if ssid:
                ssid = decode_ssid(ssid)
                strength = int(props['Strength'])
                for devid in self.model.get_device_ids():
                    if self.model.has_ap(devid, ssid):
                        self.model.set_ap_strength(devid, ssid, strength)

    def build_cache(self):
        devices = self.manager.GetDevices()
        for device_path in devices:
            device_obj = self.bus.get_object(NM, device_path)
            device_type_prop = get_prop(device_obj, NM_DEVICE, 'DeviceType')
            if device_type_prop != DEVICE_TYPE_WIFI:
                continue
            if not self.model.has_device(device_path):
                udi = get_prop(device_obj, NM_DEVICE, 'Udi')
                if udi:
                    vendor, model = get_vendor_and_model(udi)
                else:
                    vendor, model = ('', '')
                self.model.add_device(device_path, vendor, model)
            ap_list = device_obj.GetAccessPoints(dbus_interface=NM_DEVICE_WIFI)
            ssids = []
            for ap_path in ap_list:
                ap_obj = self.bus.get_object(NM, ap_path)
                ssid = get_prop(ap_obj, NM_AP, 'Ssid')
                if ssid:
                    ssid = decode_ssid(ssid)
                    strength = int(get_prop(ap_obj, NM_AP, 'Strength') or 0)
                    secure = (get_prop(ap_obj, NM_AP, 'WpaFlags') != 0 or
                              get_prop(ap_obj, NM_AP, 'RsnFlags') != 0)
                    if self.model.has_ap(device_path, ssid):
                        self.model.set_ap_strength(device_path, ssid, strength)
                    else:
                        self.model.add_ap(device_path, ssid, secure, strength)
                    ssids.append(ssid)
            self.model.remove_aps_not_in(device_path, ssids)
        self.model.remove_devices_not_in(devices)
        return False
