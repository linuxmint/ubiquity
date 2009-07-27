# -*- coding: UTF-8 -*-

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

from ubiquity.filteredcommand import FilteredCommand
from ubiquity import gconftool

class AptSetup(FilteredCommand):
    def _gconf_http_proxy(self):
        if gconftool.get('/system/http_proxy/use_http_proxy') != 'true':
            return None

        host = gconftool.get('/system/http_proxy/host')
        if host == '':
            return None
        port = gconftool.get('/system/http_proxy/port')
        if port == '':
            port = '8080'

        auth = gconftool.get('/system/http_proxy/use_authentication')
        if auth == 'true':
            user = gconftool.get('/system/http_proxy/authentication_user')
            password = gconftool.get(
                '/system/http_proxy/authentication_password')
            return 'http://%s:%s@%s:%s/' % (host, port, user, password)
        else:
            return 'http://%s:%s/' % (host, port)

    def _gconf_no_proxy(self):
        return ','.join(gconftool.get_list('/system/http_proxy/ignore_hosts'))

    def prepare(self):
        env = {}

        try:
            chosen_http_proxy = self.db.get('mirror/http/proxy')
        except debconf.DebconfError:
            chosen_http_proxy = None

        if not chosen_http_proxy:
            http_proxy = self._gconf_http_proxy()
            if http_proxy is not None:
                self.preseed('mirror/http/proxy', http_proxy)
                no_proxy = self._gconf_no_proxy()
                if no_proxy:
                    env['no_proxy'] = no_proxy

        return (['/usr/share/ubiquity/apt-setup'], [], env)
