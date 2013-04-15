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
# - Evan Dandrea <ev@ubuntu.com>
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

import os
import re


def check_grub_device(device):
    """Check that the user entered a valid boot device.
        @return True if the device is valid, False if it is not."""
    regex = re.compile(r'^/dev/([a-zA-Z0-9]+|mapper/[a-zA-Z0-9_]+)$')
    if regex.search(device):
        if not os.path.exists(device):
            return False
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

    result = set()

    if len(name) < 1 or len(name) > 63:
        result.add(HOSTNAME_LENGTH)

    regex = re.compile(r'^[a-zA-Z0-9.-]+$')
    if not regex.search(name):
        result.add(HOSTNAME_BADCHAR)
    if name.startswith('-') or name.endswith('-'):
        result.add(HOSTNAME_BADHYPHEN)
    if '..' in name or name.startswith('.') or name.endswith('.'):
        result.add(HOSTNAME_BADDOTS)

    return sorted(result)


# Based on setPasswordStrength() in Mozilla Seamonkey, which is tri-licensed
# under MPL 1.1, GPL 2.0, and LGPL 2.1.

def password_strength(password):
    upper = lower = digit = symbol = 0
    for char in password:
        if char.isdigit():
            digit += 1
        elif char.islower():
            lower += 1
        elif char.isupper():
            upper += 1
        else:
            symbol += 1
    length = len(password)
    if length > 5:
        length = 5
    if digit > 3:
        digit = 3
    if upper > 3:
        upper = 3
    if symbol > 3:
        symbol = 3
    strength = (
        ((length * 0.1) - 0.2) +
        (digit * 0.1) +
        (symbol * 0.15) +
        (upper * 0.1))
    if strength > 1:
        strength = 1
    if strength < 0:
        strength = 0
    return strength


def human_password_strength(password):
    strength = password_strength(password)
    length = len(password)
    if length == 0:
        hint = ''
        color = ''
    elif length < 6:
        hint = 'too_short'
        color = 'darkred'
    elif strength < 0.5:
        hint = 'weak'
        color = 'darkred'
    elif strength < 0.75:
        hint = 'fair'
        color = 'darkorange'
    elif strength < 0.9:
        hint = 'good'
        color = 'darkgreen'
    else:
        hint = 'strong'
        color = 'darkgreen'
    return (hint, color)


# TODO dmitrij.ledkov 2012-07-23: factor-out further into generic
# page/pagegtk/pagekde sub-widget
def gtk_password_validate(controller,
                          password,
                          verified_password,
                          password_ok,
                          password_error_label,
                          password_strength,
                          allow_empty=False,
                          ):
    complete = True
    passw = password.get_text()
    vpassw = verified_password.get_text()
    if passw != vpassw:
        complete = False
        password_ok.hide()
        if passw and (len(vpassw) / float(len(passw)) > 0.8):
            # TODO Cache, use a custom string.
            txt = controller.get_string(
                'ubiquity/text/password_mismatch')
            txt = (
                '<small>'
                '<span foreground="darkred"><b>%s</b></span>'
                '</small>' % txt)
            password_error_label.set_markup(txt)
            password_error_label.show()
    else:
        password_error_label.hide()

    if allow_empty:
        password_strength.hide()
    elif not passw:
        password_strength.hide()
        complete = False
    else:
        (txt, color) = human_password_strength(passw)
        # TODO Cache
        txt = controller.get_string('ubiquity/text/password/' + txt)
        txt = '<small><span foreground="%s"><b>%s</b></span></small>' \
              % (color, txt)
        password_strength.set_markup(txt)
        password_strength.show()
        if passw == vpassw:
            password_ok.show()

    return complete
