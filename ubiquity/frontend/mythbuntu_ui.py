# -*- coding: utf-8 -*-
#
# «mythbuntu-ui» - Mythbuntu user interface
#
# Copyright (C) 2005 Junta de Andalucía
# Copyright (C) 2005, 2006, 2007, 2008 Canonical Ltd.
# Copyright (C) 2007-2009, Mario Limonciello, for Mythbuntu
# Copyright (C) 2007, Jared Greenwald, for Mythbuntu
#
# Authors:
#
# - Original gtk-ui.py that this is based upon:
#   - Javier Carranza <javier.carranza#interactors._coop>
#   - Juan Jesús Ojeda Croissier <juanje#interactors._coop>
#   - Antonio Olmo Titos <aolmo#emergya._info>
#   - Gumer Coronel Pérez <gcoronel#emergya._info>
#   - Colin Watson <cjwatson@ubuntu.com>
#   - Evan Dandrea <evand@ubuntu.com>
#   - Mario Limonciello <superm1@ubuntu.com>
#
# - This Document:
#   - Mario Limonciello <superm1@mythbuntu.org>
#   - Jared Greenwald <greenwaldjared@gmail.com>
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or at your option)
# any later version.
#
# Ubiquity is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with Ubiquity; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import sys
import os
import re
import string
import subprocess
import syslog
import signal

import gtk

#Mythbuntu common functionality
from mythbuntu_common.lirc import LircHandler
from mythbuntu_common.mysql import MySQLHandler
from mythbuntu_common.dictionaries import *

#Mythbuntu ubiquity imports
from ubiquity.components import mythbuntu, mythbuntu_install

#Ubiquity imports
from ubiquity.misc import *
import ubiquity.frontend.gtk_ui as ParentFrontend
ParentFrontend.install = mythbuntu_install
ParentFrontend.summary = mythbuntu_install

VIDEOPAGE="mythbuntu_stepDrivers"

MYTHPAGES = [
    "mythbuntu_stepCustomInstallType",
    "mythbuntu_stepServices",
    "tab_remote_control",
    VIDEOPAGE,
    "mythbuntu_stepPasswords",
    "mythbuntu_stepBackendSetup"
]

class Wizard(ParentFrontend.Wizard):

#Overriden Methods
    def __init__(self, distro):
        #Remove migration assistant
        if 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
            del os.environ['UBIQUITY_MIGRATION_ASSISTANT']
        place=ParentFrontend.BREADCRUMB_STEPS["stepReady"]

        #Max steps
        ParentFrontend.BREADCRUMB_MAX_STEP = place + len(MYTHPAGES)

        #update location of summary page
        ParentFrontend.BREADCRUMB_STEPS["stepReady"]=place+len(MYTHPAGES)-1

        #Add in final page
        final_page=MYTHPAGES.pop()
        ParentFrontend.BREADCRUMB_STEPS[final_page]=place+len(MYTHPAGES)+1
        ParentFrontend.SUBPAGES.append(final_page)

        #Add in individual mythpages pages
        for string in MYTHPAGES:
            ParentFrontend.BREADCRUMB_STEPS[string]=place
            ParentFrontend.SUBPAGES.insert(len(ParentFrontend.SUBPAGES)-2,string)
            place+=1

        ParentFrontend.Wizard.__init__(self,distro)

    def customize_installer(self):
        """Initial UI setup."""
        #Default to auto login, but don't make it mandatory
        #This requires disabling encrypted FS
        self.set_auto_login(True)
        self.login_encrypt.set_sensitive(False)

        #Remove their summary page.  ours is better
        self.pages.pop()

        #Insert all of our pages
        for page in [mythbuntu.MythbuntuInstallType, mythbuntu.MythbuntuServices,
            mythbuntu.MythbuntuRemote, mythbuntu.MythbuntuDrivers,
            mythbuntu.MythbuntuPasswords, mythbuntu_install.Summary]:
            self.pages.append(page)

        #Prepopulate some dynamic pages
        self.populate_lirc()
        self.populate_video()
        self.populate_mysql()
        self.backup=False

        ParentFrontend.Wizard.customize_installer(self)

    def run_success_cmd(self):
        """Runs mythbuntu post post install GUI step"""
        if not 'UBIQUITY_AUTOMATIC' in os.environ and self.get_installtype() != "Frontend":
            self.live_installer.show()
            self.installing = False
            self.steps.next_page()
            self.back.hide()
            self.quit.hide()
            self.next.set_label("Finish")
            gtk.main()
            self.live_installer.hide()
        ParentFrontend.Wizard.run_success_cmd(self)

    def set_page(self, n):
        if n == 'MythbuntuRemote':
            cur = self.tab_remote_control
        elif n == 'MythbuntuDrivers':
            cur = self.mythbuntu_stepDrivers
        elif n == 'MythbuntuInstallType':
            cur = self.mythbuntu_stepCustomInstallType
        elif n == 'MythbuntuPasswords':
            cur = self.mythbuntu_stepPasswords
            if "Master" not in self.get_installtype():
                self.allow_go_forward(False)
        elif n == 'MythbuntuServices':
            cur = self.mythbuntu_stepServices
            self.vnc_option_hbox.set_sensitive(len(self.get_password()) >= 6)
        else:
            ParentFrontend.Wizard.set_page(self,n)
            return
        self.run_automation_error_cmd()
        self.backup = False
        self.live_installer.show()
        self.set_current_page(self.steps.page_num(cur))

####################
#Helper Functions  #
####################
#Called for initialization and calculation on a page

    def populate_lirc(self):
            """Fills the lirc pages with the appropriate data"""
            self.remote_count = 0
            self.transmitter_count = 0
            self.lirc=LircHandler()
            for item in self.lirc.get_possible_devices("remote"):
                if "Custom" not in item and "Blaster" not in item:
                    self.remote_list.append_text(item)
                    self.remote_count = self.remote_count + 1
            for item in self.lirc.get_possible_devices("transmitter"):
                if "Custom" not in item:
                    self.transmitter_list.append_text(item)
                    self.transmitter_count = self.transmitter_count + 1
            self.remote_list.set_active(0)
            self.transmitter_list.set_active(0)

    def populate_video(self):
        """Finds the currently active video driver"""
        dictionary=get_graphics_dictionary()
        if len(dictionary) > 0:
            for driver in dictionary:
                self.video_driver.append_text(driver)
            self.video_driver.append_text("Open Source Driver")
            self.video_driver.set_active(len(dictionary))
            self.tvoutstandard.set_active(0)
            self.tvouttype.set_active(0)
        else:
            for step in ParentFrontend.BREADCRUMB_STEPS:
                if (ParentFrontend.BREADCRUMB_STEPS[step] >
                    ParentFrontend.BREADCRUMB_STEPS[VIDEOPAGE]):
                    ParentFrontend.BREADCRUMB_STEPS[step] -= 1
            ParentFrontend.BREADCRUMB_MAX_STEP -= 1
            self.steps.remove_page(self.steps.page_num(self.mythbuntu_stepDrivers))
            self.pages.remove(mythbuntu.MythbuntuDrivers)

    def populate_mysql(self):
        """Puts a new random mysql password into the UI for each run
           This ensures that passwords don't ever get cached"""
        self.mysql=MySQLHandler()
        new_pass_caller = subprocess.Popen(['pwgen','-s','8'],stdout=subprocess.PIPE)
        self.mysql_password.set_text(string.split(new_pass_caller.communicate()[0])[0])

    def do_mythtv_setup(self,widget):
        """Spawn MythTV-Setup binary."""
        self.live_installer.hide()
        self.refresh()
        execute_root("/usr/share/ubiquity/mythbuntu-setup")
        self.live_installer.show()

    def do_connection_test(self,widget):
        """Tests to make sure that the backend is accessible"""
        config={}
        config["user"]=self.mysql_user.get_text()
        config["password"]=self.mysql_password.get_text()
        config["server"]=self.mysql_server.get_text()
        config["database"]=self.mysql_database.get_text()
        self.mysql.update_config(config)
        result=self.mysql.do_connection_test()
        self.allow_go_forward(True)
        self.connection_results_label.show()
        self.connection_results.set_text(result)

#####################
#Preseeding Functions#
#####################
#Used to preset the status of an element in the GUI

    def set_installtype(self,type):
        """Preseeds the type of custom install"""
        if type == "Set Top Box":
            self.stb.set_active(True)
        elif type == "Frontend":
            self.fe.set_active(True)
        elif type == "Slave Backend":
            self.slave_be.set_active(True)
        elif type == "Master Backend":
            self.master_be.set_active(True)
        elif type == "Slave Backend/Frontend":
            self.slave_be_fe.set_active(True)
        else:
            self.master_be_fe.set_active(True)

    def set_service(self,name,value):
        """Preseeds the status of a service"""
        lists = [get_services_dictionary(self)]
        self._preseed_list(lists,name,value)

    def set_driver(self,name,value):
        """Preseeds the status of a driver"""
        lists = [{'video_driver': self.video_driver,
                  'tvout': self.tvouttype,
                  'tvstandard': self.tvoutstandard}]
        self._preseed_list(lists,name,value)

    def set_password(self,name,value):
        """Preseeds a password"""
        lists = [{'mysql_mythtv_user':self.mysql_user,
                  'mysql_mythtv_password':self.mysql_password,
                  'mysql_mythtv_dbname':self.mysql_database,
                  'mysql_host':self.mysql_server}]
        self._preseed_list(lists,name,value)

    def set_lirc(self,question,answer):
        """Preseeds a lirc configuration item"""
        if question == "remote":
            for i in range(0,self.remote_count):
                self.remote_list.set_active(i)
                found=False
                if self.remote_list.get_active_text() == answer:
                    found = True
                    break
                if not found:
                    self.remote_list.set_active(0)
        if question == "transmitter":
            for i in range(0,self.transmitter_count):
                self.transmitter_list.set_active(i)
                found=False
                if self.transmitter_list.get_active_text() == answer:
                    found = True
                    break
                if not found:
                    self.transmitter_list.set_active(0)

    def _preseed_list(self,lists,names,value):
        """Helper function for preseeding dictionary based lists"""
        new_value = create_bool(value)
        for list in lists:
            for item in list:
                for name in string.split(names):
                    if item == name:
                        #be careful what type of item we are deealing with
                        if type(list[item]) == gtk.CheckButton:
                            list[item].set_active(new_value)
                        elif type(list[item]) == gtk.Entry:
                            list[item].set_text(new_value)
                        elif type(list[item]) == gtk.ComboBox:
                            for iteration in range(len(list[item]),0):
                                list[item].set_active(iteration)
                                if list[item].get_active_text() == new_value:
                                    break
                        else:
                            list[item].set_active_text(new_value)

##################
#Status Reading  #
##################
#Functions for reading the status of Frontend elements

    def get_installtype(self):
        """Returns the current custom installation type"""
        if self.master_be_fe.get_active():
            return "Master Backend/Frontend"
        elif self.slave_be_fe.get_active():
            return "Slave Backend/Frontend"
        elif self.master_be.get_active():
            return "Master Backend"
        elif self.slave_be.get_active():
            return "Slave Backend"
        elif self.fe.get_active():
            return "Frontend"
        elif self.stb.get_active():
            return "Set Top Box"

    def _build_static_list(self,lists):
        """Creates a flat list"""
        total_list= {}
        for list in lists:
            for item in list:
                if type(list[item]) == str:
                    total_list[item]=list[item]
                elif type(list[item]) == gtk.CheckButton:
                    total_list[item]=list[item].get_active()
                elif type(list[item]) == gtk.Entry:
                    total_list[item]=list[item].get_text()
                else:
                    total_list[item]=list[item].get_active_text()
        return total_list

    def get_services(self):
        """Returns the status of all installable services"""
        return self._build_static_list([get_services_dictionary(self)])

    def get_drivers(self):
        video_drivers=get_graphics_dictionary()
        active_video_driver=self.video_driver.get_active_text()
        for item in video_drivers:
            if (active_video_driver == item):
                active_video_driver=video_drivers[item]
                break
        return self._build_static_list([{'video_driver': active_video_driver,
                                         'tvout': self.tvouttype,
                                         'tvstandard': self.tvoutstandard}])

    def get_mythtv_passwords(self):
        return self._build_static_list([{'mysql_mythtv_user':self.mysql_user,
                                         'mysql_mythtv_password':self.mysql_password,
                                         'mysql_mythtv_dbname':self.mysql_database,
                                         'mysql_host':self.mysql_server}])

    def get_lirc(self,type):
        item = {"modules":"","device":"","driver":"","lircd_conf":""}
        if type == "remote":
            item["remote"]=self.remote_list.get_active_text()
        elif type == "transmitter":
            item["transmitter"]=self.transmitter_list.get_active_text()
        return item

##################
#Toggle functions#
##################
#Called when a widget changes and other GUI elements need to react

    def toggle_tv_out (self,widget):
        """Called when the tv-out type is toggled"""
        if (self.tvouttype.get_active() == 0):
            self.tvoutstandard.set_active(0)
        elif ((self.tvouttype.get_active() == 1 or self.tvouttype.get_active() == 2) and (self.tvoutstandard.get_active() == 0 or self.tvoutstandard.get_active() >= 11 )):
            self.tvoutstandard.set_active(10)
        elif self.tvouttype.get_active() == 3:
            self.tvoutstandard.set_active(11)

    def toggle_tv_standard(self,widget):
        """Called when the tv standard is toggled"""
        if (self.tvoutstandard.get_active() >= 11):
            self.tvouttype.set_active(3)
        elif (self.tvoutstandard.get_active() < 11 and self.tvoutstandard.get_active() > 0 and self.tvouttype.get_active() == 0):
            self.tvouttype.set_active(1)
        elif (self.tvoutstandard.get_active() < 11 and self.tvouttype.get_active() ==3):
            self.tvouttype.set_active(1)
        elif (self.tvoutstandard.get_active() == 0):
            self.tvouttype.set_active(0)

    def video_changed (self,widget):
        """Called whenever the modify video driver option is toggled or its kids"""
        drivers=get_graphics_dictionary()
        if (widget is not None and widget.get_name() == 'video_driver'):
            type = widget.get_active()
            if (type < len(drivers)):
                self.tvout_vbox.set_sensitive(True)
            else:
                self.tvout_vbox.set_sensitive(False)
                self.tvoutstandard.set_active(0)
                self.tvouttype.set_active(0)

    def toggle_customtype (self,widget):
        """Called whenever a custom type is toggled"""

        if "Master" in self.get_installtype():
            self.mysql_option_hbox.show()
        else:
            self.enablemysql.set_active(False)
            self.mysql_option_hbox.hide()

        if "Backend" in self.get_installtype():
            self.samba_option_hbox.show()
            self.nfs_option_hbox.show()
        else:
            self.enablesamba.set_active(False)
            self.enablenfs.set_active(False)
            self.samba_option_hbox.hide()
            self.nfs_option_hbox.hide()

    def toggle_ir(self,widget):
        """Called whenever a request to enable/disable remote is called"""
        if widget is not None:
            #turn on/off IR remote
            if widget.get_name() == 'remotecontrol':
                self.remote_hbox.set_sensitive(widget.get_active())
                self.generate_lircrc_checkbox.set_sensitive(widget.get_active())
                if widget.get_active() and self.remote_list.get_active() == 0:
                        self.remote_list.set_active(1)
                else:
                    self.remote_list.set_active(0)
            #turn on/off IR transmitter
            elif widget.get_name() == "transmittercontrol":
                self.transmitter_hbox.set_sensitive(widget.get_active())
                if widget.get_active():
                    if self.transmitter_list.get_active() == 0:
                        self.transmitter_list.set_active(1)
                else:
                    self.transmitter_list.set_active(0)
            #if our selected remote itself changed
            elif widget.get_name() == 'remote_list':
                self.generate_lircrc_checkbox.set_active(True)
                if self.remote_list.get_active() == 0:
                    self.remotecontrol.set_active(False)
                    self.generate_lircrc_checkbox.set_active(False)
            #if our selected transmitter itself changed
            elif widget.get_name() == 'transmitter_list':
                if self.transmitter_list.get_active() == 0:
                    self.transmittercontrol.set_active(False)
