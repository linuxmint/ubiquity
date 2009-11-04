# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2006, 2007, 2009 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
# Copyright (C) 2007 Mario Limonciello
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

import os
from ubiquity.plugin import *

NAME = 'myth-backend-setup'
AFTER = 'myth-summary'
WEIGHT = 10

class PageGtk(PluginUI):
    def __init__(self, *args, **kwargs):
        if os.environ['UBIQUITY_FRONTEND'] == 'mythbuntu_ui':
            self.plugin_optional_widgets = 'mythbuntu_stepBackendSetup'

    def plugin_get_current_page(self):
        return None
