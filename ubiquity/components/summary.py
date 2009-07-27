# -*- coding: UTF-8 -*-

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

from ubiquity.parted_server import PartedServer
from ubiquity.misc import *

from ubiquity.filteredcommand import FilteredCommand

def installing_from_disk():
    cdromfs = ''
    try:
        fp = open('/proc/mounts')
        for line in fp:
            line = line.split()
            if line[1] == '/cdrom':
                cdromfs = line[2]
                break
    finally:
        if fp:
            fp.close()
    if cdromfs == 'iso9660' or not cdromfs:
        return False
    else:
        return True

def find_grub_target():
    # This needs to be somewhat duplicated from grub-installer here because we
    # need to be able to show the user what device GRUB will be installed to
    # well before grub-installer is run.
    try:
        boot = ''
        root = ''
        regain_privileges()
        p = PartedServer()
        for disk in p.disks():
            p.select_disk(disk)
            for part in p.partitions():
                part = part[1]
                if p.has_part_entry(part, 'mountpoint'):
                    mp = p.readline_part_entry(part, 'mountpoint')
                    if mp == '/boot':
                        boot = disk.replace('=', '/')
                    elif mp == '/':
                        root = disk.replace('=', '/')
        drop_privileges()
        if boot:
            return boot
        elif root:
            return root
        return '(hd0)'
    except Exception, e:
        drop_privileges()
        import syslog
        syslog.syslog('Exception in find_grub_target: ' + str(e))
        return '(hd0)'

def grub_options():
    """ Generates a list of suitable targets for grub-installer
        @return empty list or a list of ['/dev/sda1','Linux Mint 5 Elyssa'] """
    regain_privileges()
    l = []
    oslist = {}
    subp = subprocess.Popen(['os-prober'], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    result = subp.communicate()[0].splitlines()
    for res in result:
        res = res.split(':')
        oslist[res[0]] = res[1]
    p = PartedServer()
    for disk in p.disks():
        p.select_disk(disk)
        dev = ''
        mod = ''
        size = ''
        try:
            fp = open(p.device_entry('model'))
            mod = fp.readline()
            fp.close()
            fp = open(p.device_entry('device'))
            dev = fp.readline()
            fp = open(p.device_entry('size'))
            size = fp.readline()
        finally:
            fp.close()
        if dev and mod:
            if size.isdigit():
                size = format_size(int(size))
                l.append([dev, '%s (%s)' % (mod, size)])
            else:
                l.append([dev, mod])
        for part in p.partitions():
            ostype = ''
            if part[4] == 'linux-swap':
                continue
            if os.path.exists(p.part_entry(part[1], 'format')):
                pass
            elif part[5] in oslist.keys():
                ostype = oslist[part[5]]
            l.append([part[5], ostype])
    drop_privileges()
    return l

def will_be_installed(pkg):
    try:
        manifest = open('/cdrom/casper/filesystem.manifest-desktop')
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

class Summary(FilteredCommand):
    def __init__(self, frontend):
        FilteredCommand.__init__(self, frontend)

    def prepare(self):
        return ('/usr/share/ubiquity/summary', ['^ubiquity/summary.*'])

    def run(self, priority, question):
        if question.endswith('/summary'):
            text = ''
            wrapper = textwrap.TextWrapper(width=76)
            for line in self.extended_description(question).split("\n"):
                text += wrapper.fill(line) + "\n"

            self.frontend.set_summary_text(text)

            try:
                install_bootloader = self.db.get('ubiquity/install_bootloader')
                self.frontend.set_grub(install_bootloader == 'true')
            except debconf.DebconfError:
                self.frontend.set_grub(None)

            if os.access('/usr/share/grub-installer/grub-installer', os.X_OK):
                # TODO cjwatson 2006-09-04: a bit inelegant, and possibly
                # Ubuntu-specific?
                if installing_from_disk():
                    self.frontend.set_summary_device(find_grub_target())
                else:
                    self.frontend.set_summary_device('(hd0)')
            else:
                self.frontend.set_summary_device(None)

            self.frontend.set_grub_combo(grub_options())

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
        return FilteredCommand.run(self, priority, question)
