# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2010 Canonical Ltd.
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

from ubiquity.plugin import *
import os

NAME = 'wireless'
AFTER = 'prepare'
WEIGHT = 10

# TODO debconf question for the wireless network / page itself.  Preseed null
# to skip the page.
# TODO on run(), check for a wireless card, and then for APs.  If none, go to
# next page.
class PageGtk(PluginUI):
    plugin_title = 'ubiquity/text/wireless_heading_label'
    def __init__(self, controller, *args, **kwargs):
        from ubiquity.gtkwidgets import WirelessWidget
        self.controller = controller
        try:
            import gtk
            builder = gtk.Builder()
            self.controller.add_builder(builder)
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], 'stepWireless.ui'))
            builder.connect_signals(self)
            self.page = builder.get_object('stepWireless')
            self.wirelesswidget = builder.get_object('wirelesswidget')
        except Exception, e:
            self.debug('Could not create prepare page: %s', e)
            self.page = None
        self.plugin_widgets = self.page

    def set_ssid(self, ssid):
        self.wirelesswidget.scan()
        # TODO select ssid


class Page(Plugin):
    def prepare(self):
        return (['/usr/share/ubiquity/simple-plugins', 'wireless'], ['ubiquity/ssid'])

    def run(self, priority, question):
        try:
            # TODO if ubi-prepare sets online question, self.done = True
            #import dbus
            #bus = dbus.SystemBus()
            #o = bus.get_object(WM, WM_PATH)
            #self.interface = dbus.Interface(o, WM)
            #if not self.interface.HardwarePresent():
            #    self.done = True
            pass
        except Exception, e:
            print 'caught exception', e
            self.done = True
        # Support key type and key as well
        #ssid = self.db.get('ubiquity/ssid')
        #self.ui.set_ssid(ssid)

        return Plugin.run(self, priority, question)

    def ok_handler(self):
        #ssid = self.ui.get_ssid()
        #self.preseed('ubiquity/ssid', ssid)
        Plugin.ok_handler(self)

