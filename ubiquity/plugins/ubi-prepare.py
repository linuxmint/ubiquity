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

from __future__ import print_function

import os
import subprocess
import sys

from ubiquity import i18n, misc, osextras, plugin, upower


NAME = 'prepare'
AFTER = 'wireless'
WEIGHT = 11
OEM = False


# TODO: This cannot be a non-debconf plugin after all as OEMs may want to
# preseed the 'install updates' and 'install non-free software' options.  So?
# Just db_get them.  No need for any other overhead, surely.  Actually, you
# need the dbfilter for that get.

class PreparePageBase(plugin.PluginUI):
    plugin_title = 'ubiquity/text/prepare_heading_label'

    def plugin_set_online_state(self, state):
        self.prepare_network_connection.set_state(state)
        self.enable_download_updates(state)
        if not state:
            self.set_download_updates(False)

    def set_sufficient_space(self, state):
        if not state:
            # There's either no drives present, or not enough free space.
            # Either way, we cannot continue.
            self.controller.allow_go_forward(False)
        self.prepare_sufficient_space.set_state(state)

    def set_sufficient_space_text(self, space):
        self.prepare_sufficient_space.set_property('label', space)

    def plugin_translate(self, lang):
        power = self.controller.get_string('prepare_power_source', lang)
        ether = self.controller.get_string('prepare_network_connection', lang)
        self.prepare_power_source.set_property('label', power)
        self.prepare_network_connection.set_property('label', ether)


class PageGtk(PreparePageBase):
    restricted_package_name = 'ubuntu-restricted-addons'

    def __init__(self, controller, *args, **kwargs):
        if self.is_automatic:
            self.page = None
            return
        self.controller = controller
        from gi.repository import Gtk
        builder = Gtk.Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepPrepare.ui'))
        builder.connect_signals(self)
        self.page = builder.get_object('stepPrepare')
        self.prepare_download_updates = builder.get_object(
            'prepare_download_updates')
        self.prepare_nonfree_software = builder.get_object(
            'prepare_nonfree_software')
        self.prepare_sufficient_space = builder.get_object(
            'prepare_sufficient_space')
        self.prepare_foss_disclaimer = builder.get_object(
            'prepare_foss_disclaimer')
        self.prepare_foss_disclaimer_extra = builder.get_object(
            'prepare_foss_disclaimer_extra_label')
        self.prepare_power_source = builder.get_object('prepare_power_source')
        if upower.has_battery():
            upower.setup_power_watch(self.prepare_power_source)
        else:
            self.prepare_power_source.hide()
        self.prepare_network_connection = builder.get_object(
            'prepare_network_connection')
        self.plugin_widgets = self.page

    def enable_download_updates(self, val):
        self.prepare_download_updates.set_sensitive(val)

    def set_download_updates(self, val):
        self.prepare_download_updates.set_active(val)

    def get_download_updates(self):
        return self.prepare_download_updates.get_active()

    def set_allow_nonfree(self, allow):
        if not allow:
            self.prepare_nonfree_software.set_active(False)
            self.prepare_nonfree_software.set_property('visible', False)
            self.prepare_foss_disclaimer.set_property('visible', False)
            self.prepare_foss_disclaimer_extra.set_property('visible', False)

    def set_use_nonfree(self, val):
        if osextras.find_on_path('ubuntu-drivers'):
            self.prepare_nonfree_software.set_active(val)
        else:
            self.debug('Could not find ubuntu-drivers on the executable path.')
            self.set_allow_nonfree(False)

    def get_use_nonfree(self):
        return self.prepare_nonfree_software.get_active()

    def plugin_translate(self, lang):
        PreparePageBase.plugin_translate(self, lang)
        release = misc.get_release()
        from gi.repository import Gtk
        for widget in [self.prepare_foss_disclaimer]:
            text = i18n.get_string(Gtk.Buildable.get_name(widget), lang)
            text = text.replace('${RELEASE}', release.name)
            widget.set_label(text)


class PageKde(PreparePageBase):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_prepare'
    restricted_package_name = 'kubuntu-restricted-addons'

    def __init__(self, controller, *args, **kwargs):
        from ubiquity.qtwidgets import StateBox
        if self.is_automatic:
            self.page = None
            return
        self.controller = controller
        try:
            from PyQt4 import uic
            self.page = uic.loadUi('/usr/share/ubiquity/qt/stepPrepare.ui')
            self.prepare_download_updates = self.page.prepare_download_updates
            self.prepare_nonfree_software = self.page.prepare_nonfree_software
            self.prepare_foss_disclaimer = self.page.prepare_foss_disclaimer
            self.prepare_sufficient_space = StateBox(self.page)
            self.page.vbox1.addWidget(self.prepare_sufficient_space)
            # TODO we should set these up and tear them down while on this
            # page.
            try:
                self.prepare_power_source = StateBox(self.page)
                if upower.has_battery():
                    upower.setup_power_watch(self.prepare_power_source)
                    self.page.vbox1.addWidget(self.prepare_power_source)
                else:
                    self.prepare_power_source.hide()
            except Exception as e:
                # TODO use an inconsistent state?
                print('unable to set up power source watch:', e)
            try:
                self.prepare_network_connection = StateBox(self.page)
                self.page.vbox1.addWidget(self.prepare_network_connection)
            except Exception as e:
                print('unable to set up network connection watch:', e)
        except Exception as e:
            print("Could not create prepare page:", str(e), file=sys.stderr)
            self.debug('Could not create prepare page: %s', e)
            self.page = None
        self.plugin_widgets = self.page

    def enable_download_updates(self, val):
        self.prepare_download_updates.setEnabled(val)

    def set_download_updates(self, val):
        self.prepare_download_updates.setChecked(val)

    def get_download_updates(self):
        from PyQt4.QtCore import Qt
        return self.prepare_download_updates.checkState() == Qt.Checked

    def set_allow_nonfree(self, allow):
        if not allow:
            self.prepare_nonfree_software.setChecked(False)
            self.prepare_nonfree_software.setVisible(False)
            self.prepare_foss_disclaimer.setVisible(False)

    def set_use_nonfree(self, val):
        if osextras.find_on_path('ubuntu-drivers'):
            self.prepare_nonfree_software.setChecked(val)
        else:
            self.debug('Could not find ubuntu-drivers on the executable path.')
            self.set_allow_nonfree(False)

    def get_use_nonfree(self):
        from PyQt4.QtCore import Qt
        return self.prepare_nonfree_software.checkState() == Qt.Checked

    def plugin_translate(self, lang):
        PreparePageBase.plugin_translate(self, lang)
        # gtk does the ${RELEASE} replace for the title in gtk_ui but we do
        # it per plugin because our title widget is per plugin
        release = misc.get_release()
        widgets = (
            self.page.prepare_heading_label,
            self.page.prepare_best_results,
            self.page.prepare_foss_disclaimer,
        )
        for widget in widgets:
            text = widget.text()
            text = text.replace('${RELEASE}', release.name)
            text = text.replace('Ubuntu', 'Kubuntu')
            widget.setText(text)


class Page(plugin.Plugin):
    def prepare(self):
        if (self.db.get('apt-setup/restricted') == 'false' or
                self.db.get('apt-setup/multiverse') == 'false'):
            self.ui.set_allow_nonfree(False)
        else:
            use_nonfree = self.db.get('ubiquity/use_nonfree') == 'true'
            self.ui.set_use_nonfree(use_nonfree)

        download_updates = self.db.get('ubiquity/download_updates') == 'true'
        self.ui.set_download_updates(download_updates)
        self.setup_sufficient_space()
        command = ['/usr/share/ubiquity/simple-plugins', 'prepare']
        questions = ['ubiquity/use_nonfree']
        return command, questions

    def setup_sufficient_space(self):
        # TODO move into prepare.
        size = misc.install_size()
        self.db.subst(
            'ubiquity/text/prepare_sufficient_space', 'SIZE',
            misc.format_size(size))
        space = self.description('ubiquity/text/prepare_sufficient_space')
        self.ui.set_sufficient_space(self.big_enough(size))
        self.ui.set_sufficient_space_text(space)

    def big_enough(self, size):
        with misc.raised_privileges():
            proc = subprocess.Popen(
                ['parted_devices'],
                stdout=subprocess.PIPE, universal_newlines=True)
            devices = proc.communicate()[0].rstrip('\n').split('\n')
            ret = False
            for device in devices:
                if device and int(device.split('\t')[1]) > size:
                    ret = True
                    break
        return ret

    def ok_handler(self):
        download_updates = self.ui.get_download_updates()
        use_nonfree = self.ui.get_use_nonfree()
        self.preseed_bool('ubiquity/use_nonfree', use_nonfree)
        self.preseed_bool('ubiquity/download_updates', download_updates)
        if use_nonfree:
            with misc.raised_privileges():
                # Install ubuntu-restricted-addons.
                self.preseed_bool('apt-setup/universe', True)
                self.preseed_bool('apt-setup/multiverse', True)
                if self.db.fget('ubiquity/nonfree_package', 'seen') != 'true':
                    self.preseed(
                        'ubiquity/nonfree_package',
                        self.ui.restricted_package_name)
        plugin.Plugin.ok_handler(self)
