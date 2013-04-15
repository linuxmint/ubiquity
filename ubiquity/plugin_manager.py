# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2009 Canonical Ltd.
# Written by Michael Terry <michael.terry@canonical.com>.
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Ubiquity is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ubiquity.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import fnmatch
import importlib
import os
import sys


PLUGIN_PATH = (os.environ.get('UBIQUITY_PLUGIN_PATH', False)
               or '/usr/lib/ubiquity/plugins')


def load_plugin(modname):
    sys.path.insert(0, PLUGIN_PATH)
    try:
        return importlib.import_module(modname)
    finally:
        del sys.path[0]


def load_plugins():
    modules = []
    modfiles = [x for x in os.listdir(PLUGIN_PATH)
                if fnmatch.fnmatch(x, '*.py')]
    for modfile in modfiles:
        modname = os.path.splitext(modfile)[0]
        try:
            modules.append(load_plugin(modname))
        except Exception as e:
            print('Could not import plugin %s: %s' % (modname, e),
                  file=sys.stderr)
    return modules


def get_mod_list(mod, name):
    if hasattr(mod, name):
        mod_list = getattr(mod, name)
        if not isinstance(mod_list, list):
            mod_list = [mod_list]
        return mod_list
    else:
        return []


def get_mod_string(mod, name):
    if hasattr(mod, name):
        mod_string = getattr(mod, name)
        return mod_string
    else:
        return ''


def get_mod_int(mod, name):
    if hasattr(mod, name):
        mod_int = getattr(mod, name)
        return mod_int
    else:
        return 0


def get_mod_bool(mod, name):
    if hasattr(mod, name):
        mod_bool = getattr(mod, name)
        return mod_bool
    else:
        return True


def get_mod_index(modlist, name):
    index = 0
    for mod in modlist:
        modname = get_mod_string(mod, 'NAME')
        if modname == name:
            return index
        index += 1
    return None


def get_mod_weight(mod):
    return get_mod_int(mod, 'WEIGHT')


def determine_mod_index(after, before, order):
    index = None
    for modname in after:
        if not modname:
            return 0
        else:
            index = get_mod_index(order, modname)
            if index is not None:
                return index + 1
    if index is None:
        for modname in before:
            if not modname:
                return len(order)
            else:
                index = get_mod_index(order, modname)
                if index is not None:
                    return index
    return None


# Strips one module from the 'mods' list and inserts it into 'order'
def one_pass(mods, order, hidden_list):
    mods_copy = [x for x in mods]
    for mod in mods_copy:
        name = get_mod_string(mod, 'NAME')
        if not name:
            mods.remove(mod)
            continue
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            oem = get_mod_bool(mod, 'OEM')
            if not oem:
                mods.remove(mod)
                continue
        after = get_mod_list(mod, 'AFTER')
        before = get_mod_list(mod, 'BEFORE')
        hidden = get_mod_list(mod, 'HIDDEN')
        if not after and not before and hidden:
            mods.remove(mod)
            hidden_list.extend(hidden)
            continue
        index = determine_mod_index(after, before, order)
        if index is not None:
            mods.remove(mod)
            order.insert(index, mod)
            hidden_list.extend(hidden)
            return True
    return False


def order_plugins(mods, order=None):
    if order is None:
        order = []
    hidden_list = []
    # First, sort mods by weight
    mods = sorted(mods, key=get_mod_weight)
    # Keep making passes until we can't place any more mods into order.
    while one_pass(mods, order, hidden_list):
        pass
    for hidden in hidden_list:
        index = get_mod_index(order, hidden)
        if index is not None:
            del order[index]
    return order
