# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2011 Canonical Ltd.
# Written by Stephane Graber <stgraber@ubuntu.com>.
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
import subprocess

from ubiquity import misc, osextras


# I think it's clearer to keep our 'set' method, and it doesn't cause a
# builtin-shadowing problem in practice unless you use 'from
# ubiquity.gsettings import set' (so don't do that).
__pychecker__ = 'no-shadowbuiltin'

_cached_gsettings_exists = None


def _gsettings_exists():
    global _cached_gsettings_exists
    if _cached_gsettings_exists is not None:
        return _cached_gsettings_exists

    _cached_gsettings_exists = osextras.find_on_path('gsettings')
    return _cached_gsettings_exists


def get(schema, key, user=None):
    if not _gsettings_exists():
        return

    if not user:
        user = os.getenv("SUDO_USER", os.getenv("USER", "root"))

    subp = subprocess.Popen(
        ['sudo', '-u', user, 'gsettings', 'get', schema, key],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        preexec_fn=misc.drop_all_privileges, universal_newlines=True)
    value = subp.communicate()[0].rstrip('\n')

    if not value:
        return

    # If it's a list, it should be accessed through get_list()
    if value.startswith('['):
        return value

    # Parse strings
    if value.startswith('\'') and value.endswith('\''):
        return value[1:-1]

    # Parse ints
    if value.isdigit():
        return int(value)

    # Parse booleans
    if value == 'false':
        return False
    if value == 'true':
        return True


def get_list(schema, key, user=None):
    if not _gsettings_exists():
        return

    value = get(schema, key, user)
    if not value or not value.startswith("[") or not value.endswith("]"):
        return

    try:
        # This only works reliably with int and strings
        elements = eval(value, None, None)
        return elements
    except:
        return


def set(schema, key, value, user=None):
    if not _gsettings_exists():
        return

    if not user:
        user = os.getenv("SUDO_USER", os.getenv("USER", "root"))

    # Convert booleans
    if isinstance(value, bool):
        value = "true" if value else "false"

    subprocess.call(
        ['sudo', '-u', user, 'gsettings', 'set', schema, key, str(value)],
        preexec_fn=misc.drop_all_privileges)


def set_list(schema, key, values, user=None):
    if not _gsettings_exists():
        return

    value = str(values)
    set(schema, key, value, user)


def unset(schema, key, user=None):
    if not _gsettings_exists():
        return

    if not user:
        user = os.getenv("SUDO_USER", os.getenv("USER", "root"))

    subprocess.call(
        ['sudo', '-u', user, 'gsettings', 'reset', schema, key],
        preexec_fn=misc.drop_all_privileges)
