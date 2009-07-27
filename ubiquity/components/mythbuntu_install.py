# -*- coding: UTF-8 -*-

# Copyright (C) 2006, 2007 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
# Copyright (C) 2007 Mario Limonciello
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

import ubiquity.components.summary
class Summary(ubiquity.components.summary.Summary):
    """This class is used for populating the Mythbuntu summary page
       using a custom script"""
    def prepare(self):
        return ('/usr/share/ubiquity/mythbuntu_summary', ['^mythbuntu/summary.*'])

import ubiquity.components.install
class Install(ubiquity.components.install.Install):
    """This class calls out to the main ubiquity processing script. Control
       is handled off from the part of the UI asking questions by this class"""
    def prepare(self):
        prep = list(ubiquity.components.install.Install.prepare(self))
        prep[0] = ['/usr/share/ubiquity/mythbuntu_install.py']
        return prep
