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

NAME = 'myth-passwords'
AFTER = 'myth-drivers'
WEIGHT = 10

class PageGtk(PluginUI):
    def __init__(self, *args, **kwargs):
        if os.environ['UBIQUITY_FRONTEND'] == 'mythbuntu_ui':
            self.plugin_widgets = 'mythbuntu_stepPasswords'

class Page(Plugin):

    def prepare(self):
        #mythtv passwords
        passwords = self.frontend.get_mythtv_passwords()
        questions = []
        for this_password in passwords:
            answer = self.db.get('mythtv/' + this_password)
            if answer != '':
                self.frontend.set_password(this_password,answer)
            questions.append('^mythtv/' + this_password)

        #if we are a Master type, we'll skip this page
        if 'Master' in self.frontend.get_installtype() and 'UBIQUITY_AUTOMATIC' not in os.environ:
            os.environ['UBIQUITY_AUTOMATIC'] = "2"
            #regrab the passwords in case any of them actually were supposed preseeded
            passwords = self.frontend.get_mythtv_passwords()
            for this_password in passwords:
                self.preseed('mythtv/' + this_password, passwords[this_password])

        return (['/usr/share/ubiquity/ask-mythbuntu','passwords'], questions)

    def ok_handler(self):
        #mythtv passwords
        passwords = self.frontend.get_mythtv_passwords()
        for this_password in passwords:
            self.preseed('mythtv/' + this_password, passwords[this_password])

        Plugin.ok_handler(self)

    def cleanup(self):
        #Clear out our skipping if we did it only because of Master
        if 'UBIQUITY_AUTOMATIC' in os.environ and os.environ['UBIQUITY_AUTOMATIC'] == "2":
            del os.environ['UBIQUITY_AUTOMATIC']

        Plugin.cleanup(self)
