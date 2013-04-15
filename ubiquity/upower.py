import os

import dbus

from ubiquity import misc


UPOWER = 'org.freedesktop.UPower'
UPOWER_PATH = '/org/freedesktop/UPower'


def setup_power_watch(prepare_power_source):
    bus = dbus.SystemBus()
    upower = bus.get_object(UPOWER, UPOWER_PATH)

    def power_state_changed():
        prepare_power_source.set_state(
            not misc.get_prop(upower, UPOWER_PATH, 'OnBattery'))

    bus.add_signal_receiver(power_state_changed, 'Changed', UPOWER, UPOWER)
    power_state_changed()


def has_battery():
    # UPower doesn't seem to have an interface for this.
    path = '/sys/class/power_supply'
    if not os.path.exists(path):
        return False
    for d in os.listdir(path):
        p = os.path.join(path, d, 'type')
        if os.path.exists(p):
            with open(p) as fp:
                if fp.read().startswith('Battery'):
                    return True
    return False
