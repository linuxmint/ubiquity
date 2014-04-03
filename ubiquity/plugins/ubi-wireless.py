# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2013 Canonical Ltd.
# Written by Evan Dandrea <evan.dandrea@canonical.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os

from ubiquity import plugin


NAME = 'wireless'
#after prepare for default install, but language for oem install
AFTER = 'language'
WEIGHT = 12


class WirelessPageBase(plugin.PluginUI):
    def __init__(self):
        plugin.PluginUI.__init__(self)
        self.skip = False

    def plugin_set_online_state(self, online):
        self.skip = online

    def plugin_skip_page(self):
        # Set from the command line with --wireless
        if 'UBIQUITY_WIRELESS' in os.environ:
            return False

        from ubiquity import nm

        if nm.wireless_hardware_present():
            return self.skip
        else:
            return True


class PageGtk(WirelessPageBase):
    plugin_title = 'ubiquity/text/wireless_heading_label'

    def __init__(self, controller, *args, **kwargs):
        WirelessPageBase.__init__(self)
        import dbus
        from gi.repository import Gtk

        from ubiquity import misc
        # NOTE: Import 'nmwidgets' even though it's not used in this function
        # as importing it as the side effect of registering
        # NetworkManagerWidget which we DO use in the Wireless step UI.
        from ubiquity.frontend.gtk_components import nmwidgets

        if self.is_automatic:
            self.page = None
            return
        # Check whether we can talk to NM at all (e.g. debugging ubiquity
        # over ssh with X forwarding).
        try:
            misc.has_connection()
        except dbus.DBusException:
            self.page = None
            return
        self.controller = controller
        builder = Gtk.Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepWireless.ui'))
        builder.connect_signals(self)
        self.page = builder.get_object('stepWireless')
        self.nmwidget = builder.get_object('nmwidget')
        self.nmwidget.connect('connection', self.state_changed)
        self.nmwidget.connect('selection_changed', self.selection_changed)
        self.nmwidget.connect('pw_validated', self.pw_validated)
        self.no_wireless = builder.get_object('no_wireless')
        self.use_wireless = builder.get_object('use_wireless')
        self.use_wireless.connect('toggled', self.wireless_toggled)
        self.plugin_widgets = self.page
        self.have_selection = False
        self.state = self.nmwidget.get_state()
        self.next_normal = True
        self.back_normal = True
        self.connect_text = None
        self.stop_text = None
        self.skip = False

    def plugin_translate(self, lang):
        get_s = self.controller.get_string
        label_text = get_s('ubiquity/text/wireless_password_label')
        display_text = get_s('ubiquity/text/wireless_display_password')
        self.nmwidget.translate(label_text, display_text)

        self.connect_text = get_s('ubiquity/text/connect', lang)
        self.stop_text = get_s('ubiquity/text/stop', lang)
        frontend = self.controller._wizard
        if not self.next_normal:
            frontend.next.set_label(self.connect_text)
        if not self.back_normal:
            frontend.back.set_label(self.stop_text)

    def selection_changed(self, unused):
        from ubiquity import nm

        self.have_selection = True
        self.use_wireless.set_active(True)
        assert self.state is not None
        frontend = self.controller._wizard
        if self.state == nm.NM_STATE_CONNECTING:
            frontend.translate_widget(frontend.next)
            self.next_normal = True
        else:
            if (not self.nmwidget.is_row_an_ap() or
                    self.nmwidget.is_row_connected()):
                frontend.translate_widget(frontend.next)
                self.next_normal = True
            else:
                frontend.next.set_label(self.connect_text)
                self.next_normal = False

    def wireless_toggled(self, unused):
        frontend = self.controller._wizard
        if self.use_wireless.get_active():
            if not self.have_selection:
                self.nmwidget.select_usable_row()
            self.state_changed(None, self.state)
        else:
            frontend.connecting_spinner.hide()
            frontend.connecting_spinner.stop()
            frontend.connecting_label.hide()
            frontend.translate_widget(frontend.next)
            self.nmwidget.hbox.set_sensitive(False)
            self.next_normal = True
            self.controller.allow_go_forward(True)

    def plugin_on_back_clicked(self):
        frontend = self.controller._wizard
        if frontend.back.get_label() == self.stop_text:
            self.nmwidget.disconnect_from_ap()
            return True
        else:
            frontend.connecting_spinner.hide()
            frontend.connecting_spinner.stop()
            frontend.connecting_label.hide()
            self.no_wireless.set_active(True)
            return False

    def plugin_on_next_clicked(self):
        frontend = self.controller._wizard
        if frontend.next.get_label() == self.connect_text:
            self.nmwidget.connect_to_ap()
            return True
        else:
            frontend.connecting_spinner.hide()
            frontend.connecting_spinner.stop()
            frontend.connecting_label.hide()
            return False

    def state_changed(self, unused, state):
        from ubiquity import nm

        self.state = state
        frontend = self.controller._wizard
        if not self.use_wireless.get_active():
            return
        if state != nm.NM_STATE_CONNECTING:
            frontend.connecting_spinner.hide()
            frontend.connecting_spinner.stop()
            frontend.connecting_label.hide()
            self.controller.allow_go_forward(True)

            frontend.translate_widget(frontend.back)
            self.back_normal = True
            frontend.back.set_sensitive(True)
        else:
            frontend.connecting_spinner.show()
            frontend.connecting_spinner.start()
            frontend.connecting_label.show()

            self.next_normal = True

            frontend.back.set_label(self.stop_text)
            self.back_normal = False
            frontend.back.set_sensitive(True)
        self.selection_changed(None)

    def pw_validated(self, unused, validated):
        self.controller.allow_go_forward(validated)


class PageKde(WirelessPageBase):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_wireless'

    def __init__(self, controller, *args, **kwargs):
        WirelessPageBase.__init__(self)
        import dbus
        from ubiquity import misc

        if self.is_automatic:
            self.page = None
            return
        # Check whether we can talk to NM at all (e.g. debugging ubiquity
        # over ssh with X forwarding).
        try:
            misc.has_connection()
        except dbus.DBusException:
            self.page = None
            return
        self.controller = controller
        self._setup_page()
        self.plugin_widgets = self.page

    def _setup_page(self):
        from PyQt4 import uic, QtGui
        from ubiquity.frontend.kde_components import nmwidgets
        self.nmwidget = nmwidgets.NetworkManagerWidget()
        self.nmwidget.state_changed.connect(self._update_ui)

        self.page = uic.loadUi('/usr/share/ubiquity/qt/stepWireless.ui')
        layout = QtGui.QHBoxLayout(self.page.nmwidget_container)
        layout.setMargin(0)
        layout.addWidget(self.nmwidget)

        self.page.use_wireless.toggled.connect(self._update_ui)

    def plugin_translate(self, lang):
        dct = dict()
        for text in self.nmwidget.get_translation_keys():
            dct[text] = self.controller.get_string('ubiquity/text/' + text)

        self.nmwidget.translate(dct)

    def _update_ui(self):
        from ubiquity import nm
        if self.page.use_wireless.isChecked():
            forward = self.nmwidget.get_state() == nm.NM_STATE_CONNECTED_GLOBAL
        else:
            forward = True
        self.controller.allow_go_forward(forward)
