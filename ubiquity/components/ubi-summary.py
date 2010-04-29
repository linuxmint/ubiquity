# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006, 2007, 2008 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
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
import textwrap
import subprocess

import debconf

from ubiquity.plugin import *
from ubiquity.misc import *
from ubiquity.casper import get_casper

from ubiquity import validation

NAME = 'summary'
AFTER = 'usersetup'
WEIGHT = 10
# Not useful in oem-config.
OEM = False

class PageBase(PluginUI):
    def __init__(self):
        self.grub_en = None
        self.summary_device = None
        self.popcon = None
        self.http_proxy_host = None
        self.http_proxy_port = 8080

    def set_summary_text(self):
        pass

class PageGtk(PageBase):
    plugin_is_install = True
    plugin_widgets = 'stepReady'

    def __init__(self, controller, *args, **kwargs):
        PageBase.__init__(self)
        self.controller = controller

        import gtk
        builder = gtk.Builder()
        controller.add_builder(builder)
        builder.add_from_file('/usr/share/ubiquity/gtk/stepReady.ui')
        builder.connect_signals(self)
        self.page = builder.get_object('stepReady')
        self.ready_text = builder.get_object('ready_text')
        self.grub_device_entry = builder.get_object('grub_device_entry')
        self.advanced_okbutton = builder.get_object('advanced_okbutton')
        self.bootloader_vbox = builder.get_object('bootloader_vbox')
        self.grub_enable = builder.get_object('grub_enable')
        self.grub_device_label = builder.get_object('grub_device_label')
        self.grub_device_entry = builder.get_object('grub_device_entry')
        self.popcon_vbox = builder.get_object('popcon_vbox')
        self.popcon_checkbutton = builder.get_object('popcon_checkbutton')
        self.proxy_host_entry = builder.get_object('proxy_host_entry')
        self.proxy_port_spinbutton = builder.get_object('proxy_port_spinbutton')
        self.advanced_dialog = builder.get_object('advanced_dialog')
        self.plugin_widgets = self.page

        self.grub_device_entry.connect('changed', self.grub_verify_loop,
            self.advanced_okbutton)

        # The default instantiation of GtkComboBoxEntry creates a
        # GtkCellRenderer, so reuse it.
        self.grub_device_entry.set_model(self.controller.grub_options)
        self.grub_device_entry.set_text_column(0)
        renderer = gtk.CellRendererText()
        self.grub_device_entry.pack_start(renderer, True)
        self.grub_device_entry.add_attribute(renderer, 'text', 1)

    def set_summary_text(self, text):
        import gtk
        for child in self.ready_text.get_children():
            self.ready_text.remove(child)

        ready_buffer = gtk.TextBuffer()
        ready_buffer.set_text(text)
        self.ready_text.set_buffer(ready_buffer)

    def grub_verify_loop(self, widget, okbutton):
        if widget is not None:
            if validation.check_grub_device(widget.child.get_text()):
                okbutton.set_sensitive(True)
            else:
                okbutton.set_sensitive(False)

    def on_advanced_button_clicked(self, unused_button):
        import gtk
        display = False
        grub_en = self.controller.get_grub()
        summary_device = self.controller.get_summary_device()

        if grub_en is not None:
            display = True
            self.bootloader_vbox.show()
            self.grub_enable.set_active(grub_en)
        else:
            self.bootloader_vbox.hide()
            summary_device = None

        if summary_device is not None:
            display = True
            self.grub_device_label.show()
            self.grub_device_entry.show()
            self.grub_device_entry.child.set_text(summary_device)
            self.grub_device_entry.set_sensitive(grub_en)
            self.grub_device_label.set_sensitive(grub_en)
        else:
            self.grub_device_label.hide()
            self.grub_device_entry.hide()

        if self.popcon is not None:
            display = True
            self.popcon_vbox.show()
            self.popcon_checkbutton.set_active(self.popcon)
        else:
            self.popcon_vbox.hide()

        display = True
        if self.http_proxy_host:
            self.proxy_host_entry.set_text(self.http_proxy_host)
            self.proxy_port_spinbutton.set_sensitive(True)
        else:
            self.proxy_port_spinbutton.set_sensitive(False)
        self.proxy_port_spinbutton.set_value(self.http_proxy_port)

        # never happens at the moment because the HTTP proxy question is
        # always valid
        if not display:
            return

        response = self.advanced_dialog.run()
        self.advanced_dialog.hide()
        if response == gtk.RESPONSE_OK:
            if summary_device is not None:
                self.controller.set_summary_device(self.grub_device_entry.child.get_text())
            self.controller.set_popcon(self.popcon_checkbutton.get_active())
            self.controller.set_grub(self.grub_enable.get_active())
            self.controller.set_proxy_host(self.proxy_host_entry.get_text())
            self.controller.set_proxy_port(self.proxy_port_spinbutton.get_value_as_int())
        return True

    def toggle_grub(self, widget):
        if (widget is not None and widget.get_name() == 'grub_enable'):
            self.grub_device_entry.set_sensitive(widget.get_active())
            self.grub_device_label.set_sensitive(widget.get_active())

    def on_proxy_host_changed(self, widget):
        if widget is not None and widget.get_name() == 'proxy_host_entry':
            text = self.proxy_host_entry.get_text()
            self.proxy_port_spinbutton.set_sensitive(text != '')


class PageKde(PageBase):
    plugin_is_install = True
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_summary'

    def __init__(self, controller, *args, **kwargs):
        PageBase.__init__(self)

        self.controller = controller

        from PyQt4 import uic
        from PyQt4.QtGui import QDialog

        self.plugin_widgets = uic.loadUi('/usr/share/ubiquity/qt/stepSummary.ui')
        self.advanceddialog = QDialog(self.plugin_widgets)
        uic.loadUi("/usr/share/ubiquity/qt/advanceddialog.ui", self.advanceddialog)

        self.advanceddialog.grub_enable.stateChanged.connect(self.toggle_grub)
        self.advanceddialog.proxy_host_entry.textChanged.connect(self.enable_proxy_spinbutton)

        self.plugin_widgets.advanced_button.clicked.connect(self.on_advanced_button_clicked)
        self.w = self.plugin_widgets

    def set_summary_text (self, text):
        text = text.replace("\n", "<br>")
        self.plugin_widgets.ready_text.setText(text)

    def set_grub_combo(self, options):
        ''' options gives us a possible list of install locations for the boot loader '''
        self.advanceddialog.grub_device_entry.clear()
        ''' options is from summary.py grub_options() '''
        for opt in options:
           self.advanceddialog.grub_device_entry.addItem(opt[0])

    def enable_proxy_spinbutton(self):
        self.advanceddialog.proxy_port_spinbutton.setEnabled(self.advanceddialog.proxy_host_entry.text() != '')

    def toggle_grub(self):
        grub_en = self.advanceddialog.grub_enable.isChecked()
        self.advanceddialog.grub_device_entry.setEnabled(grub_en)
        self.advanceddialog.grub_device_label.setEnabled(grub_en)

    def on_advanced_button_clicked(self):

        display = False
        grub_en = self.controller.get_grub()
        summary_device = self.controller.get_summary_device()
        self.advanceddialog.grub_device_entry.clear()

        if grub_en:
            self.advanceddialog.grub_enable.show()
            self.advanceddialog.grub_enable.setChecked(grub_en)
        else:
            self.advanceddialog.grub_enable.hide()
            summary_device = None

        if summary_device:
            display = True
            self.advanceddialog.bootloader_group_label.show()
            self.advanceddialog.grub_device_label.show()
            self.advanceddialog.grub_device_entry.show()

            # if the combo box does not yet have the target install device, add it
            # select current device
            summary_device = self.controller.get_summary_device()
            
            # by default select the summary device
            self.advanceddialog.grub_device_entry.addItem(summary_device)
            index = self.advanceddialog.grub_device_entry.count() - 1
            self.advanceddialog.grub_device_entry.setCurrentIndex(index)

            self.advanceddialog.grub_device_entry.setEnabled(grub_en)
            self.advanceddialog.grub_device_label.setEnabled(grub_en)
            
            for o in grub_options():
                if o[0] == summary_device:
                    continue
                self.advanceddialog.grub_device_entry.addItem(o[0])
        else:
            self.advanceddialog.bootloader_group_label.hide()
            self.advanceddialog.grub_device_label.hide()
            self.advanceddialog.grub_device_entry.hide()

        if self.popcon:
            display = True
            self.advanceddialog.popcon_group_label.show()
            self.advanceddialog.popcon_checkbutton.show()
            self.advanceddialog.popcon_checkbutton.setChecked(self.popcon)
        else:
            self.advanceddialog.popcon_group_label.hide()
            self.advanceddialog.popcon_checkbutton.hide()

        display = True
        if self.http_proxy_host:
            self.advanceddialog.proxy_port_spinbutton.setEnabled(True)
            self.advanceddialog.proxy_host_entry.setText(unicode(self.http_proxy_host))
        else:
            self.advanceddialog.proxy_port_spinbutton.setEnabled(False)
        self.advanceddialog.proxy_port_spinbutton.setValue(self.http_proxy_port)

        if not display:
            return

        response = self.advanceddialog.exec_()
        from PyQt4.QtGui import QDialog
        if response == QDialog.Accepted:
            if summary_device is not None:
                self.controller.set_summary_device(
                    unicode(self.advanceddialog.grub_device_entry.currentText()))
            self.controller.set_popcon(self.advanceddialog.popcon_checkbutton.isChecked())
            self.controller.set_grub(self.advanceddialog.grub_enable.isChecked())
            self.controller.set_proxy_host(unicode(self.advanceddialog.proxy_host_entry.text()))
            self.controller.set_proxy_port(self.advanceddialog.proxy_port_spinbutton.value())

def will_be_installed(pkg):
    try:
        casper_path = os.path.join(
            '/cdrom', get_casper('LIVE_MEDIA_PATH', 'casper').lstrip('/'))
        manifest = open(os.path.join(casper_path,
                                     'filesystem.manifest-desktop'))
        try:
            for line in manifest:
                if line.strip() == '' or line.startswith('#'):
                    continue
                if line.split()[0] == pkg:
                    return True
        finally:
            manifest.close()
    except IOError:
        return True

class Page(Plugin):
    def prepare(self):
        return ('/usr/share/ubiquity/summary', ['^ubiquity/summary.*'])

    def run(self, priority, question):
        if question.endswith('/summary'):
            text = ''
            wrapper = textwrap.TextWrapper(width=76)
            for line in self.extended_description(question).split("\n"):
                text += wrapper.fill(line) + "\n"

            self.ui.set_summary_text(text)

            try:
                install_bootloader = self.db.get('ubiquity/install_bootloader')
                self.frontend.set_grub(install_bootloader == 'true')
            except debconf.DebconfError:
                self.frontend.set_grub(None)

            if os.access('/usr/share/grub-installer/grub-installer', os.X_OK):
                self.frontend.set_summary_device(grub_default())
            else:
                self.frontend.set_summary_device(None)

            if will_be_installed('popularity-contest'):
                try:
                    participate = self.db.get('popularity-contest/participate')
                    self.frontend.set_popcon(participate == 'true')
                except debconf.DebconfError:
                    self.frontend.set_popcon(None)
            else:
                self.frontend.set_popcon(None)

            # This component exists only to gather some information and then
            # get out of the way.
            #return True
        return Plugin.run(self, priority, question)
