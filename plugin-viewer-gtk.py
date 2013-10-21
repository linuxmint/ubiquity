#!/usr/bin/python3

import os
import sys

from gi.repository import Gtk
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

# we could use this as the base for the MockController as well
#   from ubiquity.frontend.base import Controller

# for testing online status
from ubiquity.misc import add_connection_watch

class MockController(object):

    def __init__(self, parent):
        self.parent = parent
        self.oem_user_config = None
        self.oem_config = None
        self.dbfilter = None
        self._allow_go_foward = True
        self._allow_go_backward = True

    def go_forward(self):
        self.parent.button_next.clicked()

    def get_string(self, s, lang):
        return "get_string: %s (lang=%s)" % (s, lang)

    def add_builder(self, builder):
        pass

    def allow_go_forward(self, v):
        self._allow_go_forward = v
        self.parent.button_next.set_sensitive(v)

    def allow_go_backward(self, v):
        self._allow_go_backward = v
        self.parent.button_back.set_sensitive(v)


if __name__ == "__main__":
    """ Run with:
    ./plugin-viewer-gtk.py ubi-ubuntuone
    """
    def _on_button_next_clicked(button):
        stop = page_gtk.plugin_on_next_clicked()
        if not stop:
            Gtk.main_quit()

    # setup env
    for envvar, path in (
            ("UBIQUITY_PLUGIN_PATH", "./ubiquity/plugins"),
            ("UBIQUITY_GLADE", "./gui/gtk")):
        if os.path.exists(path):
            os.environ[envvar] = path
    # ... and then import the plugin_manager
    from ubiquity.plugin_manager import load_plugin

    plugin_name = sys.argv[1]
    plugin_module = load_plugin(plugin_name)

    win = Gtk.Window()
    win.button_next = Gtk.Button("next")
    win.button_back = Gtk.Button("back")

    mock_controller = MockController(win)
    page_gtk = plugin_module.PageGtk(mock_controller)
    page_gtk.plugin_translate("en")

    # this user password is for the Ubuntu SSO plugin, to test keyring
    # creation.
    page_gtk._user_password = "test keyring password"

    win.button_next.connect(
        "clicked", _on_button_next_clicked)
    win.button_back.connect(
        "clicked", lambda b: page_gtk.plugin_on_back_clicked())

    add_connection_watch(page_gtk.plugin_set_online_state)

    # fake debconf interface:
    page_gtk.db = {'netcfg/get_hostname': 'test hostname'}

    button_box = Gtk.ButtonBox(spacing=12)
    button_box.set_layout(Gtk.ButtonBoxStyle.END)
    button_box.pack_start(win.button_back, True, True, 6)
    button_box.pack_start(win.button_next, True, True, 6)

    box = Gtk.VBox()
    box.pack_start(page_gtk.page, True, True, 6)
    box.pack_start(button_box, True, True, 6)

    win.add(box)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    Gtk.main()
