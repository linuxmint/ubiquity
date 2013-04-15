# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2009 Canonical Ltd.
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

from ubiquity import plugin


NAME = 'network'
AFTER = 'usersetup'
WEIGHT = 12


class NetworkUnfilteredOnly(Exception):
    pass


class PageDebconf(plugin.PluginUI):
    plugin_title = 'ubiquity/text/network_heading_label'


# Only supports unfiltered mode.
class Page(plugin.Plugin):
    def prepare(self, unfiltered=False):
        if not unfiltered:
            raise NetworkUnfilteredOnly(
                "network component only usable with debconf frontend")
        return ['/usr/share/ubiquity/netcfg-wrapper']
