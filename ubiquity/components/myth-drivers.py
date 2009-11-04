# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2006, 2007, 2009 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
# Copyright (C) 2007 Mario Limonciello
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

from ubiquity.plugin import *
from mythbuntu_common.dictionaries import get_graphics_dictionary
import os

NAME = 'myth-drivers'
AFTER = 'myth-remote'
WEIGHT = 10

class PageGtk(PluginUI):
    def __init__(self, *args, **kwargs):
        if os.environ['UBIQUITY_FRONTEND'] == 'mythbuntu_ui' and \
           len(get_graphics_dictionary()) > 0:
            self.plugin_widgets = 'mythbuntu_stepDrivers'

class Page(Plugin):
    def prepare(self):
        #drivers
        drivers = self.frontend.get_drivers()
        questions = []
        for this_driver in drivers:
            answer = self.db.get('mythbuntu/' + this_driver)
            if answer != '':
                self.frontend.set_driver(this_driver,answer)
        questions.append('^mythbuntu/' + this_driver)
        return (['/usr/share/ubiquity/ask-mythbuntu','drivers'], questions)

    def ok_handler(self):
        drivers = self.frontend.get_drivers()

        for this_driver in drivers:
            if drivers[this_driver] is True or drivers[this_driver] is False:
                self.preseed_bool('mythbuntu/' + this_driver, drivers[this_driver])
            else:
                self.preseed('mythbuntu/' + this_driver, drivers[this_driver])
        Plugin.ok_handler(self)
