# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006, 2008 Canonical Ltd.
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

import debconf

from ubiquity import gsettings
from ubiquity.filteredcommand import FilteredCommand


class AptSetup(FilteredCommand):
    def _gsettings_http_proxy(self):
        if gsettings.get('org.gnome.system.proxy', 'mode') in ('none', None):
            return None

        host = gsettings.get('org.gnome.system.proxy.http', 'host')
        if host == '':
            return None
        port = str(gsettings.get('org.gnome.system.proxy.http', 'port'))
        if port == '':
            port = '8080'

        if not host.startswith("http://"):
            host = "http://%s" % host

        auth = gsettings.get(
            'org.gnome.system.proxy.http', 'use-authentication')
        if auth:
            user = gsettings.get(
                'org.gnome.system.proxy.http', 'authentication-user')
            password = gsettings.get(
                'org.gnome.system.proxy.http', 'authentication-password')
            return '%s:%s@%s:%s/' % (host, port, user, password)
        else:
            return '%s:%s/' % (host, port)

    def _gsettings_no_proxy(self):
        ignore_list = gsettings.get_list(
            'org.gnome.system.proxy', 'ignore-hosts')
        if ignore_list:
            return ','.join(gsettings.get_list(
                'org.gnome.system.proxy', 'ignore-hosts'))

    def prepare(self):
        env = {}

        try:
            chosen_http_proxy = self.db.get('mirror/http/proxy')
        except debconf.DebconfError:
            chosen_http_proxy = None

        if not chosen_http_proxy:
            http_proxy = self._gsettings_http_proxy()
            if http_proxy is not None:
                self.preseed('mirror/http/proxy', http_proxy)
                no_proxy = self._gsettings_no_proxy()
                if no_proxy:
                    env['no_proxy'] = no_proxy

        return (['/usr/share/ubiquity/apt-setup'], ['PROGRESS'], env)
