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

from ubiquity.filteredcommand import FilteredCommand, UntrustedBase


class PluginUI(UntrustedBase):
    # We define an init even if empty so that arguments that we give but are
    # not used don't cause an error.
    def __init__(self, *args, **kwargs):
        pass


class Plugin(FilteredCommand):
    def prepare(self, unfiltered=False):
        # None causes dbfilter to just spin a main loop and wait for OK/Cancel
        return None


class InstallPlugin(Plugin):
    def install(self, *args, **kwargs):
        return self.run_command(auto_process=True)


# Use this as a decorator if you want to guard against a function being called
# when on a different page.  For instance, when it is called as part of the
# event loop.
def only_this_page(target):
    def wrapper(self, *args, **kwargs):
        if self.controller.dbfilter:
            return target(self, *args, **kwargs)
        else:
            # gobject removes timeouts if they return non-True.
            return True
    return wrapper
