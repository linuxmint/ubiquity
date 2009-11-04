# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# «validation» - miscellaneous validation of user-entered data
#
# Copyright (C) 2005 Junta de Andalucía
# Copyright (C) 2005, 2006, 2007, 2008 Canonical Ltd.
#
# Authors:
#
# - Antonio Olmo Titos <aolmo#emergya._info>
# - Javier Carranza <javier.carranza#interactors._coop>
# - Juan Jesús Ojeda Croissier <juanje#interactors._coop>
# - Colin Watson <cjwatson@ubuntu.com>
# - Evan Dandrea <evand@ubuntu.com>
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or at your option)
# any later version.
#
# Ubiquity is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with Ubiquity; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

# Validation library.
# Created by Antonio Olmo <aolmo#emergya._info> on 26 jul 2005.

def check_grub_device(device):
    """Check that the user entered a valid boot device.
        @return True if the device is valid, False if it is not."""
    import re
    regex = re.compile(r'^/dev/([a-zA-Z0-9]+|mapper/[a-zA-Z0-9_]+)$')
    if regex.search(device):
        return True
    # (device[,part-num])
    regex = re.compile(r'^\((hd|fd)[0-9]+(,[0-9]+)*\)$')
    if regex.search(device):
        return True
    else:
        return False

HOSTNAME_LENGTH = 1
HOSTNAME_BADCHAR = 2
HOSTNAME_BADHYPHEN = 3
HOSTNAME_BADDOTS = 4

def check_hostname(name):

    """ Check the correctness of a proposed host name.

        @return empty list (valid) or list of:
            - C{HOSTNAME_LENGTH} wrong length.
            - C{HOSTNAME_BADCHAR} contains invalid characters.
            - C{HOSTNAME_BADHYPHEN} starts or ends with a hyphen.
            - C{HOSTNAME_BADDOTS} contains consecutive/initial/final dots."""

    import re
    result = set()

    if len (name) < 1 or len (name) > 63:
        result.add(HOSTNAME_LENGTH)

    regex = re.compile(r'^[a-zA-Z0-9.-]+$')
    if not regex.search(name):
        result.add(HOSTNAME_BADCHAR)
    if name.startswith('-') or name.endswith('-'):
        result.add(HOSTNAME_BADHYPHEN)
    if '..' in name or name.startswith('.') or name.endswith('.'):
        result.add(HOSTNAME_BADDOTS)

    return sorted(result)
