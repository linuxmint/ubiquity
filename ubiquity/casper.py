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

# Functions to parse /etc/casper.conf.

import errno

_casper_config = None


def get_casper(key, default=None):
    global _casper_config
    if _casper_config is None:
        _casper_config = {}
        try:
            with open('/etc/casper.conf', 'r') as fp:
                for line in fp:
                    if line.startswith('#'):
                        continue
                    if line.startswith('export '):
                        line = line[6:]
                    line = line.strip()
                    bits = line.split('=', 1)
                    if len(bits) > 1:
                        _casper_config[bits[0]] = bits[1].strip('"')
        except IOError as e:
            if e.errno != errno.ENOENT:
                import syslog
                syslog.syslog('Unable to read /etc/casper.conf.')

    return _casper_config.get(key, default)
