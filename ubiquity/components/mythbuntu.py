# -*- coding: UTF-8 -*-

# Written by Mario Limonciello <superm1@ubuntu.com>.
# Copyright (C) 2007-2008 Mario Limonciello
# Copyright (C) 2007 Jared Greenwald
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

from ubiquity.misc import create_bool
from ubiquity.filteredcommand import FilteredCommand
import os

class MythbuntuInstallType(FilteredCommand):
#we are seeding one of the possible install types

    def __init__(self,frontend,db=None):
        self.questions = ['install_type']
        FilteredCommand.__init__(self,frontend,db)

    def prepare(self):
        questions = []
        for question in self.questions:
            answer = self.db.get('mythbuntu/' + question)
            if answer != '':
                self.frontend.set_installtype(answer)
            questions.append('^mythbuntu/' + question)
        return (['/usr/share/ubiquity/ask-mythbuntu','type'], questions)

    def ok_handler(self):
        self.preseed('mythbuntu/' + self.questions[0],self.frontend.get_installtype())
        FilteredCommand.ok_handler(self)

class MythbuntuServices(FilteredCommand):
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
        FilteredCommand.ok_handler(self)

class MythbuntuPasswords(FilteredCommand):

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

        FilteredCommand.ok_handler(self)

    def cleanup(self):
        #Clear out our skipping if we did it only because of Master
        if 'UBIQUITY_AUTOMATIC' in os.environ and os.environ['UBIQUITY_AUTOMATIC'] == "2":
            del os.environ['UBIQUITY_AUTOMATIC']

        FilteredCommand.cleanup(self)

class MythbuntuRemote(FilteredCommand):

    def __init__(self,frontend,db=None):
        self.top = ['remote', 'transmitter']
        FilteredCommand.__init__(self,frontend,db)

    def prepare(self):
        questions = []
        for question in self.top:
            answer = self.db.get('lirc/' + question)
            if answer != '':
                self.frontend.set_lirc(question,answer)
            questions.append('^lirc/' + question)
        return (['/usr/share/ubiquity/ask-mythbuntu','ir'], questions)

    def ok_handler(self):
        for question in self.top:
            device = self.frontend.get_lirc(question)
            self.preseed('lirc/' + question,device[question])
        FilteredCommand.ok_handler(self)

class MythbuntuDrivers(FilteredCommand):
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
        FilteredCommand.ok_handler(self)
