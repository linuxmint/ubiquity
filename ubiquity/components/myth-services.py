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
import os

NAME = 'myth-services'
AFTER = 'myth-installtype'
WEIGHT = 10

class PageGtk(PluginUI):
    def __init__(self, *args, **kwargs):
        if os.environ['UBIQUITY_FRONTEND'] == 'mythbuntu_ui':
            self.plugin_widgets = 'mythbuntu_stepServices'

class Page(Plugin):
#we are seeding the status of each service

    def prepare(self):
        services = self.frontend.get_services()
        questions = []
        for this_service in services:
            answer = self.db.get('mythbuntu/' + this_service)
            if answer != '':
                self.frontend.set_service(this_service,answer)
            questions.append('^mythbuntu/' + this_service)
        return (['/usr/share/ubiquity/ask-mythbuntu','services'], questions)

    def ok_handler(self):
        services = self.frontend.get_services()
        for this_service in services:
            answer = services[this_service]
            if answer is True or answer is False:
                self.preseed_bool('mythbuntu/' + this_service, answer)
            else:
                self.preseed('mythbuntu/' + this_service, answer)
        Plugin.ok_handler(self)
