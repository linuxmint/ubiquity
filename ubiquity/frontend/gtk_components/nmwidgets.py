from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

from gi.repository import Gtk, GObject, GLib
from gi.repository import NM, NMA

from ubiquity.nm import decode_ssid, QueuedCaller, NetworkStore, NetworkManager


class GLibQueuedCaller(QueuedCaller):
    def __init__(self, *args):
        QueuedCaller.__init__(self, *args)
        self.timeout_id = 0

    def start(self):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
        self.timeout_id = GLib.timeout_add(self.timeout, self.callback)


class GtkNetworkStore(NetworkStore, Gtk.TreeStore):
    def __init__(self):
        NetworkStore.__init__(self)
        Gtk.TreeStore.__init__(self, str, object, object)

    def get_device_ids(self):
        it = self.get_iter_first()
        lst = []
        while it:
            lst.append(self[it][0])
            it = self.iter_next(it)
        return lst

    def add_device(self, devid, vendor, model):
        self.append(None, [devid, vendor, model])

    def has_device(self, devid):
        return self._it_for_device(devid) is not None

    def remove_devices_not_in(self, devids):
        self._remove_rows_not_in(None, devids)

    def add_ap(self, devid, ssid, secure, strength):
        dev_it = self._it_for_device(devid)
        assert dev_it
        self.append(dev_it, [ssid, secure, strength])

    def has_ap(self, devid, ssid):
        return self._it_for_ap(devid, ssid) is not None

    def set_ap_strength(self, devid, ssid, strength):
        it = self._it_for_ap(devid, ssid)
        assert it
        self[it][2] = strength

    def remove_aps_not_in(self, devid, ssids):
        dev_it = self._it_for_device(devid)
        if not dev_it:
            return
        self._remove_rows_not_in(dev_it, ssids)

    def _remove_rows_not_in(self, parent_it, ids):
        it = self.iter_children(parent_it)
        while it:
            if self[it][0] in ids:
                it = self.iter_next(it)
            else:
                if not self.remove(it):
                    return

    def _it_for_device(self, devid):
        it = self.get_iter_first()
        while it:
            if self[it][0] == devid:
                return it
            it = self.iter_next(it)
        return None

    def _it_for_ap(self, devid, ssid):
        dev_it = self._it_for_device(devid)
        if not dev_it:
            return None
        it = self.iter_children(dev_it)
        while it:
            if self[it][0] == ssid:
                return it
            it = self.iter_next(it)
        return None


class NetworkManagerTreeView(Gtk.TreeView):
    __gtype_name__ = 'NetworkManagerTreeView'

    def __init__(self, state_changed=None):
        Gtk.TreeView.__init__(self)
        self.configure_icons()
        model = GtkNetworkStore()
        model.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        # TODO eventually this will subclass GenericTreeModel.
        self.wifi_model = NetworkManager(model,
                                         GLibQueuedCaller,
                                         state_changed)

        self.nm_client = None
        self.nm_connection = None

        self.set_model(model)

        ssid_column = Gtk.TreeViewColumn('')
        cell_pixbuf = Gtk.CellRendererPixbuf()
        cell_text = Gtk.CellRendererText()
        ssid_column.pack_start(cell_pixbuf, False)
        ssid_column.pack_start(cell_text, True)
        ssid_column.set_cell_data_func(cell_text, self.data_func)
        ssid_column.set_cell_data_func(cell_pixbuf, self.pixbuf_func)
        self.connect('row-activated', self.row_activated)

        self.append_column(ssid_column)
        self.set_headers_visible(False)
        self.setup_row_expansion_handling(model)

    def setup_row_expansion_handling(self, model):
        """
        If the user collapses a row, save that state. If all the APs go away
        and then return, such as when the user toggles the wifi kill switch,
        the UI should keep the row collapsed if it already was, or expand it.
        """
        self.expand_all()
        self.rows_changed_id = None

        def queue_rows_changed(*args):
            if self.rows_changed_id:
                GLib.source_remove(self.rows_changed_id)
            self.rows_changed_id = GLib.idle_add(self.rows_changed)

        model.connect('row-inserted', queue_rows_changed)
        model.connect('row-deleted', queue_rows_changed)

        self.user_collapsed = {}

        def collapsed(self, iterator, path, collapse):
            udi = model[iterator][0]
            self.user_collapsed[udi] = collapse

        self.connect('row-collapsed', collapsed, True)
        self.connect('row-expanded', collapsed, False)

    def rows_changed(self, *args):
        model = self.get_model()
        i = model.get_iter_first()
        while i:
            udi = model[i][0]
            try:
                if not self.user_collapsed[udi]:
                    path = model.get_path(i)
                    self.expand_row(path, False)
            except KeyError:
                path = model.get_path(i)
                self.expand_row(path, False)
            i = model.iter_next(i)

    def row_activated(self, unused, path, column):
        self.connect_to_selection()

    def get_state(self):
        return self.wifi_model.get_state()

    def disconnect_from_ap(self):
        if self.nm_connection:
            if not self.nm_client:
                self.nm_client = NM.Client.new()

            self.nm_client.deactivate_connection(self.nm_connection)
            self.nm_connection = None
        else:
            self.wifi_model.disconnect_from_ap()

    def configure_icons(self):
        it = Gtk.IconTheme()
        default = Gtk.IconTheme.get_default()
        default = default.load_icon("image-missing", 22, 0)
        it.set_custom_theme('ubuntu-mono-light')
        self.icons = []
        for n in ['nm-signal-00',
                  'nm-signal-25',
                  'nm-signal-50',
                  'nm-signal-75',
                  'nm-signal-100',
                  'nm-signal-00-secure',
                  'nm-signal-25-secure',
                  'nm-signal-50-secure',
                  'nm-signal-75-secure',
                  'nm-signal-100-secure']:
            ico = it.lookup_icon(n, 22, 0)
            if ico:
                ico = ico.load_icon()
            else:
                ico = default
            self.icons.append(ico)

    def pixbuf_func(self, column, cell, model, iterator, data):
        if not model.iter_parent(iterator):
            cell.set_property('pixbuf', None)
            return
        strength = model[iterator][2]
        if strength < 30:
            icon = 0
        elif strength < 50:
            icon = 1
        elif strength < 70:
            icon = 2
        elif strength < 90:
            icon = 3
        else:
            icon = 4
        if model[iterator][1]:
            icon += 5
        cell.set_property('pixbuf', self.icons[icon])

    def data_func(self, column, cell, model, iterator, data):
        ssid = model[iterator][0]

        if not model.iter_parent(iterator):
            txt = '%s %s' % (model[iterator][1], model[iterator][2])
            cell.set_property('text', txt)
        else:
            cell.set_property('text', ssid)

    def is_row_an_ap(self):
        model, iterator = self.get_selection().get_selected()
        if iterator is None:
            return False
        return model.iter_parent(iterator) is not None

    def is_row_connected(self):
        model, iterator = self.get_selection().get_selected()
        if iterator is None:
            return False
        ssid = model[iterator][0]
        parent = model.iter_parent(iterator)
        if parent and self.wifi_model.is_connected(model[parent][0], ssid):
            return True
        else:
            return False

    def find_ap(self, device, ssid):
        for ap in device.get_access_points():
            ap_ssid = ap.get_ssid()
            if ap_ssid and decode_ssid(ap_ssid.get_data()) == ssid:
                return ap
        return None

    def connect_cb(self, client, result, user_data):
        self.nm_connection = client.add_and_activate_connection_finish(result)

    def connect_dialog_cb(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            connection, device, ap = dialog.get_connection()

            if not self.nm_client:
                self.nm_client = NM.Client.new()

            self.nm_client.add_and_activate_connection_async(
                connection, device, None, None, self.connect_cb, None
            )
        dialog.hide()

    def connect_to_selection(self):
        model, iterator = self.get_selection().get_selected()
        if iterator is None:
            return
        parent = model.iter_parent(iterator)
        if parent:
            try:
                devid = model[parent][0]
                ssid = model[iterator][0]
                if model[iterator][1]:
                    if not self.nm_client:
                        self.nm_client = NM.Client.new()

                    device = self.nm_client.get_device_by_path(devid)
                    ap = self.find_ap(device, ssid)

                    connection = NM.SimpleConnection()
                    connection.add_setting(NM.SettingConnection(
                        uuid=NM.utils_uuid_generate()
                    ))
                    connection.add_setting(NM.SettingWireless(
                        ssid=ap.get_property("ssid")
                    ))

                    dialog = NMA.WifiDialog.new(
                        self.nm_client,
                        connection,
                        device,
                        ap,
                        False
                    )
                    dialog.connect("response", self.connect_dialog_cb)
                    dialog.run()
                else:
                    self.wifi_model.connect_to_ap(devid, ssid)
            except Exception as e:
                dialog = Gtk.MessageDialog(
                    None, Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE,
                    "Failed to connect to wireless network"
                )
                dialog.format_secondary_text("{}".format(e))
                dialog.run()
                dialog.hide()


GObject.type_register(NetworkManagerTreeView)


class NetworkManagerWidget(Gtk.Box):
    __gtype_name__ = 'NetworkManagerWidget'
    __gsignals__ = {
        'connection': (
            GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,
            (GObject.TYPE_UINT,)),
        'selection_changed': (
            GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE, ())}

    def __init__(self):
        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(12)
        self.view = NetworkManagerTreeView(self.state_changed)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
        scrolled_window.add(self.view)
        self.pack_start(scrolled_window, True, True, 0)
        self.selection = self.view.get_selection()
        self.selection.connect('changed', self.changed)
        self.show_all()

    def get_state(self):
        return self.view.get_state()

    def is_row_an_ap(self):
        return self.view.is_row_an_ap()

    def is_row_connected(self):
        return self.view.is_row_connected()

    def select_usable_row(self):
        self.selection.select_path('0:0')

    def state_changed(self, state):
        self.emit('connection', state)

    def connect_to_ap(self, *args):
        self.view.connect_to_selection()

    def disconnect_from_ap(self):
        self.view.disconnect_from_ap()

    def changed(self, selection):
        iterator = selection.get_selected()[1]
        if not iterator:
            return
        self.emit('selection_changed')


GObject.type_register(NetworkManagerWidget)


if __name__ == '__main__':
    window = Gtk.Window()
    window.connect('destroy', Gtk.main_quit)
    window.set_size_request(300, 300)
    window.set_border_width(12)
    nm = NetworkManagerWidget()
    window.add(nm)
    window.show_all()
    Gtk.main()
