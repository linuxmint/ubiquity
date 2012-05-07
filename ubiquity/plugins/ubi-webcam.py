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

import os
import sys

from ubiquity import plugin

NAME = 'webcam'
AFTER = 'usersetup'
WEIGHT = 10

class PageGtk(plugin.PluginUI):
    plugin_title = 'ubiquity/text/webcam_heading_label'
    def __init__(self, controller, *args, **kwargs):
        from gi.repository import Gtk, Gst
        Gst.init(sys.argv)
        from gi.repository import UbiquityWebcam
        from ubiquity import gtkwidgets
        if (not UbiquityWebcam.Webcam.available()
            or 'UBIQUITY_AUTOMATIC' in os.environ
            or controller.oem_config):
            self.page = None
            return
        self.controller = controller
        builder = Gtk.Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'],
            'stepWebcam.ui'))
        builder.connect_signals(self)
        self.page = builder.get_object('stepWebcam')
        self.plugin_widgets = self.page
        self.faceselector = gtkwidgets.FaceSelector(controller)
        self.page.add(self.faceselector)

    def plugin_get_current_page(self):
        self.page.show_all()
        self.faceselector.webcam_play()
        return self.page

    def plugin_on_back_clicked(self):
        self.faceselector.webcam_stop()
        return False

    def plugin_on_next_clicked(self):
        self.faceselector.webcam_stop()
        self.faceselector.save_to('/var/lib/ubiquity/webcam_photo.png')
        return False

    def plugin_translate(self, lang):
        self.faceselector.translate(lang)
