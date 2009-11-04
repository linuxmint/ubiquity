# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2009 Canonical Ltd.
# Written by Michael Terry <michael.terry@canonical.com>.
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Ubiquity is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ubiquity.  If not, see <http://www.gnu.org/licenses/>.

import os
from ubiquity.plugin import *

NAME = 'intro'
AFTER = None
WEIGHT = 100

def get_intro():
    """Get some introductory text, if available."""
    if 'UBIQUITY_OEM_USER_CONFIG' in os.environ or \
       'UBIQUITY_AUTOMATIC' in os.environ:
        return None

    intro = None
    introFiles = ['/usr/share/ubiquity/intro.txt', '/usr/share/ubiquity/kubuntu-netbook-intro.txt']
    for file in introFiles:
        if os.path.isfile(file):
            intro = file
            break
    if intro is None:
        return None

    intro_file = open(intro)
    text = intro_file.read()
    intro_file.close()
    return text

class PageGtk(PluginUI):
    def __init__(self, *args, **kwargs):
        text = get_intro()
        if text:
            try:
                import gtk
                builder = gtk.Builder()
                builder.add_from_file('/usr/share/ubiquity/gtk/stepIntro.ui')
                builder.get_object('intro_label').set_markup(text.rstrip('\n'))
                self.plugin_widgets = builder.get_object('stepWelcome')
            except Exception, e:
                self.debug('Could not create intro page: %s', e)

class PageKde(PluginUI):
    plugin_breadcrumb = None

    def __init__(self, *args, **kwargs):
        text = get_intro()
        if text:
            try:
                from PyQt4 import uic
                self.plugin_widgets = uic.loadUi('/usr/share/ubiquity/qt/stepIntro.ui')
                self.plugin_widgets.introLabel.setText(text.replace('\n', '<br>'))
            except Exception, e:
                self.debug('Could not create intro page: %s', e)
