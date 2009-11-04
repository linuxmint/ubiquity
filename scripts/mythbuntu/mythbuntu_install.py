#!/usr/bin/python
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005 Javier Carranza and others for Guadalinex
# Copyright (C) 2005, 2006, 2007, 2008, 2009 Canonical Ltd.
# Copyright (C) 2007-2009 Mario Limonciello
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

import sys
import os
import errno
import re
import syslog
import debconf
import shutil
import XKit.xutils

import string

sys.path.insert(0, '/usr/lib/ubiquity')

from install import Install as ParentInstall
from install import InstallStepError
from ubiquity.components import mythbuntu_install

from mythbuntu_common.lirc import LircHandler
from mythbuntu_common.vnc import VNCHandler

class Install(ParentInstall):

    def __init__(self):
        """Initializes the Mythbuntu installer extra objects"""

        #Configure Parent cclass First so we can override things
        ParentInstall.__init__(self)

        self.lirc=LircHandler()
        self.vnc=VNCHandler()
        self.type = self.db.get('mythbuntu/install_type')

        #This forces install_langpacks to do Nothing
        self.langpacks={}

    def configure_user(self):
        """Configures by the regular user configuration stuff
        followed by mythbuntu specific user addons"""

        #Before beginning, set the initial root sql pass to the user pass
        self.passwd=self.db.get('passwd/user-password')
        self.set_debconf('mythtv/mysql_admin_password',self.passwd)
        self.set_debconf('mysql-server/root_password',self.passwd)
        self.set_debconf('mysql-server/root_password_again',self.passwd)

        #Regular ubuntu user configuration
        ParentInstall.configure_user(self)

        #We'll be needing the username, uid, gid
        self.user = self.db.get('passwd/username')
        self.uid = self.gid = ''
        try:
            self.uid = self.db.get('passwd/user-uid')
        except debconf.DebconfError:
            pass
        try:
            self.gid = self.db.get('passwd/user-gid')
        except debconf.DebconfError:
            pass
        if self.uid == '':
            self.uid = 1000
        else:
            self.uid = int(self.uid)
        if self.gid == '':
            self.gid = 1000
        else:
            self.gid = int(self.gid)

        #Create a .mythtv directory
        home_mythtv_dir = self.target + '/home/' + self.user + '/.mythtv'
        if not os.path.isdir(home_mythtv_dir):
            #in case someone made a symlink or file for the directory
            if os.path.islink(home_mythtv_dir) or os.path.exists(home_mythtv_dir):
                os.remove(home_mythtv_dir)
            os.mkdir(home_mythtv_dir)
            os.chown(home_mythtv_dir,self.uid,self.gid)

        #Remove mysql.txt from home directory if it's there, then make one
        sql_txt= home_mythtv_dir + '/mysql.txt'
        if os.path.islink(sql_txt) or os.path.exists(sql_txt):
            os.remove(sql_txt)
        try:
            os.symlink('/etc/mythtv/mysql.txt',sql_txt)
        except OSError:
            #on a live disk there is a chance this was a broken link
            #depending on what the user did in the livefs
            pass

        #mythtv.desktop autostart
        if 'Frontend' in self.type:
            config_dir = self.target + '/home/' + self.user + '/.config'
            autostart_dir =  config_dir + '/autostart'
            autostart_link = autostart_dir + '/mythtv.desktop'
            if not os.path.isdir(config_dir):
                os.makedirs(config_dir)
                os.chown(config_dir,self.uid,self.gid)
            if not os.path.isdir(autostart_dir):
                os.makedirs(autostart_dir)
                os.chown(autostart_dir,self.uid,self.gid)
            elif os.path.islink(autostart_link) or os.path.exists(autostart_link):
                os.remove(autostart_link)
            try:
                os.symlink('/usr/share/applications/mythtv.desktop',autostart_link)
            except OSError:
                #on a live disk, this will appear a broken link, but it works
                pass

        #group membership
        self.chrex('adduser', self.user, 'mythtv')
        self.chrex('adduser', self.user, 'video')

    def configure_ma(self):
        """Overrides module assistant configuration method.  Mythbuntu doesn't
           use module assistant, but we can instead run MySQL and mythweb config
           here"""
        self.db.progress('INFO', 'ubiquity/install/mythbuntu')

        #Copy a few debconf questions that were answered in the installer
        for question in ('mythtv/mysql_mythtv_user','mythtv/mysql_mythtv_password',\
                         'mythtv/mysql_mythtv_dbname','mythtv/mysql_host'):
            answer=self.db.get(question)
            self.set_debconf(question,answer)

        #Setup mysql.txt nicely
        os.remove(self.target + '/etc/mythtv/mysql.txt')
        self.reconfigure('mythtv-common')

        #only reconfigure database if appropriate
        if 'Master' in self.type:
            #Prepare
            self.chrex('mount', '-t', 'proc', 'proc', '/proc')

            #Setup database
            self.reconfigure('mysql-server-5.1')
            self.reconfigure('mythtv-database')

            #Cleanup
            self.chrex('invoke-rc.d','mysql','stop')
            self.chrex('umount', '/proc')

            #Mythweb
            self.set_debconf('mythweb/enable', 'true')
            self.set_debconf('mythweb/username', self.user)
            self.set_debconf('mythweb/password', self.passwd)
            self.reconfigure('mythweb')

    def install_extras(self):
        """Overrides main install_extras function to add in Mythbuntu
           drivers and services, and then call the parent function"""
        video_driver = self.db.get('mythbuntu/video_driver')
        vnc = self.db.get('mythbuntu/x11vnc')
        nfs = self.db.get('mythbuntu/nfs-kernel-server')
        to_install = []
        to_remove = set()
        if video_driver != "Open Source Driver":
            to_install.append(video_driver)
        if vnc == 'true':
            to_install.append('x11vnc')
        if nfs == 'true':
            to_install.append('nfs-kernel-server')
            to_install.append('portmap')

        #Remove any conflicts before installing new items
        if to_remove != []:
            self.do_remove(to_remove)
        #Mark new items
        self.record_installed(to_install)

        #Actually install extras
        ParentInstall.install_extras(self)

        #Run depmod if we might be using a DKMS enabled driver
        if video_driver != "Open Source Driver":
            self.chrex('/sbin/depmod','-a')

    def configure_hardware(self):
        """Overrides parent function to add in hooks for configuring
           drivers and services"""

        #Drivers
        self.db.progress('INFO', 'ubiquity/install/drivers')
        video_driver = self.db.get('mythbuntu/video_driver')
        out = self.db.get('mythbuntu/tvout')
        standard = self.db.get('mythbuntu/tvstandard')
        if 'nvidia' in video_driver:
            self.enable_nvidia(out,standard)
        elif 'fglrx' in video_driver:
            self.enable_amd(out,standard)

        #Services
        self.db.progress('INFO', 'ubiquity/install/services')
        if self.db.get('mythbuntu/samba') == 'true':
            shutil.copy('/usr/share/mythbuntu/examples/smb.conf.dist',self.target + '/etc/samba/smb.conf')
        if self.db.get('mythbuntu/nfs-kernel-server') == 'true':
            shutil.copy('/usr/share/mythbuntu/examples/exports.dist',self.target + '/etc/exports')
        if self.db.get('mythbuntu/openssh-server') == 'true':
            for file in ['ssh_host_dsa_key','ssh_host_dsa_key.pub','ssh_host_rsa_key','ssh_host_rsa_key.pub']:
                os.remove(self.target + '/etc/ssh/' + file)
            self.reconfigure('openssh-server')
        if self.db.get('mythbuntu/mysql-server') == 'true':
            f=open(self.target + '/etc/mysql/conf.d/mythtv.cnf','w')
            print >>f, """\
[mysqld]
bind-address=0.0.0.0"""
            f.close()
        if self.db.get('mythbuntu/x11vnc') == 'true':
            self.vnc.create_password(self.passwd)
            directory = self.target + '/home/' + self.user + '/.vnc'
            if not os.path.exists(directory):
                os.mkdir(directory)
            shutil.move('/root/.vnc/passwd', directory + '/passwd')
            os.system('chown ' + str(self.uid) + ':' + str(self.gid) + ' -R ' + directory)

        #Remotes & Transmitters
        self.db.progress('INFO', 'ubiquity/install/ir')
        self.configure_ir()

        #Regular parent hardware configure f/n
        self.db.progress('INFO', 'ubiquity/install/hardware')
        ParentInstall.configure_hardware(self)

    def configure_ir(self):
        """Configures the remote & transmitter per user choices"""
        #configure lircd for remote and transmitter
        ir_device={"modules":"","driver":"","device":"","lircd_conf":"","remote":"","transmitter":""}
        self.chroot_setup()
        self.chrex('dpkg-divert', '--package', 'ubiquity', '--rename',
                   '--quiet', '--add', '/sbin/udevd')
        try:
            os.symlink('/bin/true', '/target/sbin/udevd')
        except OSError:
            pass

        try:
            ir_device["remote"] = self.db.get('lirc/remote')
            self.set_debconf('lirc/remote',ir_device["remote"])
            ir_device["modules"] = ""
            ir_device["driver"] = ""
            ir_device["device"] = ""
            ir_device["lircd_conf"] = ""
            self.lirc.set_device(ir_device,"remote")
        except debconf.DebconfError:
            pass

        try:
            ir_device["transmitter"] = self.db.get('lirc/transmitter')
            self.set_debconf('lirc/transmitter',ir_device["transmitter"])
            ir_device["modules"] = ""
            ir_device["driver"] = ""
            ir_device["device"] = ""
            ir_device["lircd_conf"] = ""
            self.lirc.set_device(ir_device,"transmitter")
        except debconf.DebconfError:
            pass

        self.lirc.write_hardware_conf(self.target + '/etc/lirc/hardware.conf')

        try:
            self.reconfigure('lirc')
        finally:
            try:
                os.unlink('/target/sbin/udevd')
            except OSError:
                pass
            self.chrex('dpkg-divert', '--package', 'ubiquity', '--rename',
                       '--quiet', '--remove', '/sbin/udevd')
        self.chroot_cleanup()

        #configure lircrc
        home = '/target/home/' + self.db.get('passwd/username')
        os.putenv('HOME',home)
        self.lirc.create_lircrc(self.target + "/etc/lirc/lircd.conf",False)
        os.system('chown ' + str(self.uid) + ':' + str(self.gid) + ' -R ' + home + '/.lirc*')

    def enable_amd(self,type,format):
        if type == 'Composite Video Output':
            self.chrex('/usr/bin/aticonfig','--tvs VIDEO', '--tvf ' + format)
        elif type == 'S-Video Video Output':
            self.chrex('/usr/bin/aticonfig','--tvs VIDEO', '--tvf ' + format)
        elif type == 'Component Video Output':
            self.chrex('/usr/bin/aticonfig','--tvs YUV', '--tvf ' + format)
        else:
            self.chrex('/usr/bin/aticonfig')

    def enable_nvidia(self,type,format):
        """Enables an NVIDIA graphics driver using XKit"""
        xorg_conf=XKit.xutils.XUtils()

        extra_conf_options={'NoLogo': '1',
                           'DPI': '100x100',
                           'UseEvents': '1'}

        if type == 'Composite Video Output':
            extra_conf_options["ConnectedMonitor"]="TV"
            extra_conf_options["TVOutFormat"]="COMPOSITE"
            extra_conf_options["TVStandard"]=format
        elif type == 'S-Video Video Output':
            extra_conf_options["ConnectedMonitor"]="TV"
            extra_conf_options["TVOutFormat"]="SVIDEO"
            extra_conf_options["TVStandard"]=format
        elif type == 'Component Video Output':
            extra_conf_options["ConnectedMonitor"]="TV"
            extra_conf_options["TVOutFormat"]="COMPONENT"
            extra_conf_options["TVStandard"]=format

        #Set up device section
        relevant_devices = []
        if len(xorg_conf.globaldict['Device']) == 0:
            device = xorg_conf.makeSection('Device', identifier='Default Device')
            relevant_devices.append(device)
            xorg_conf.setDriver('Device', 'nvidia', device)
        else:
            devices = xorg_conf.getDevicesInUse()
            if len(devices) > 0:
                relevant_devices = devices
            else:
                relevant_devices = xorg_conf.globaldict['Device'].keys()
            for device in relevant_devices:
                xorg_conf.setDriver('Device', 'nvidia', device)

        for device_section in relevant_devices:
            for k, v in extra_conf_options.iteritems():
                xorg_conf.addOption('Device', k, v, optiontype='Option', position=device_section)

        #Set up screen section
        if len(xorg_conf.globaldict['Screen']) == 0:
            screen = xorg_conf.makeSection('Screen', identifier='Default Screen')

        xorg_conf.addOption('Screen', 'DefaultDepth', '24', position=0, prefix='')

        xorg_conf.writeFile(self.target + "/etc/X11/xorg.conf")

    def remove_extras(self):
        """Try to remove packages that are installed on the live CD but not on
        the installed system."""
        #First remove normal live-desktop packages
        ParentInstall.remove_extras(self)

        #now take care of mythbuntu specifics
        packages=set()
        ## system role
        if 'Backend' not in self.type:
            packages.add('libnet-upnp-perl') #causes mythtv-backend to be removed
            packages.add('php5-common')      #causes mythweb to be removed
            packages.add('libaprutil1')      #causes apache2 to be removed
        if 'Slave' in self.type or self.type == 'Frontend':
            packages.add('ntp')              #causes mythtv-backend-master to go
            packages.add('mythtv-database')
            packages.add('mysql-server-core-5.1')
        if 'Frontend' not in self.type:
            packages.add('mythtv-frontend')
        ## services that are installed by default
        for service in ['samba','openssh-server']:
            if self.db.get('mythbuntu/' + service) == "false":
                packages.add(service)

        if len(packages) >= 0:
            #recursively remove to make sure we get plugins and services that
            #aren't necessary anymore
            self.do_remove(packages,True)

if __name__ == '__main__':
    if not os.path.exists('/var/lib/ubiquity'):
        os.makedirs('/var/lib/ubiquity')
    if os.path.exists('/var/lib/ubiquity/install.trace'):
        os.unlink('/var/lib/ubiquity/install.trace')

    install = Install()
    sys.excepthook = install.excepthook
    install.run()
    sys.exit(0)
