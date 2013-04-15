# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2008 Canonical Ltd.
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

# This is a Python reimplementation of im-switch's Xsession script:
#   Copyright (C) 2005 Kenshi Muto <kmuto@debian.org>
#    Modified for Debian package.
#   Copyright (C) 1999 - 2004 Red Hat, Inc. All rights reserved. This
#   copyrighted material is made available to anyone wishing to use, modify,
#   copy, or redistribute it subject to the terms and conditions of the
#   GNU General Public License version 2.
# We reimplement it because that lets us monitor which processes are being
# launched, and kill them off again when switching languages.

import os
import shlex
import signal
import subprocess

from ubiquity import misc


def get_language():
    if 'LC_ALL' in os.environ:
        lang = os.environ['LC_ALL']
    elif 'LC_CTYPE' in os.environ:
        lang = os.environ['LC_CTYPE']
    elif 'LANG' in os.environ:
        lang = os.environ['LANG']
    else:
        lang = ''
    lang = lang.split('@')[0]
    lang = lang.split('.')[0]
    if not lang:
        lang = 'all_ALL'
    return lang


def read_config_file(f):
    if not os.path.isfile(f) or not os.access(f, os.R_OK):
        return None
    cfg = subprocess.Popen(
        '''\
. %s
echo "XIM: $XIM"
echo "XIM_PROGRAM: $XIM_PROGRAM"
echo "XIM_ARGS: $XIM_ARGS"
echo "XIM_PROGRAM_XTRA: $XIM_PROGRAM_XTRA"
echo "XMODIFIERS: $XMODIFIERS"
echo "GTK_IM_MODULE: $GTK_IM_MODULE"
echo "QT_IM_MODULE: $QT_IM_MODULE"''' % f,
        stdout=subprocess.PIPE, shell=True, universal_newlines=True)
    cfg_lines = cfg.communicate()[0].splitlines()
    cfg_dict = {}
    for line in cfg_lines:
        bits = line.split(': ', 1)
        if len(bits) != 2:
            continue
        cfg_dict[bits[0]] = bits[1]
    return cfg_dict


def read_config():
    lang = get_language()
    files = []
    # im-switch also reads all_ALL and default, as per the commented-out
    # lines. We avoid these since that would involve starting up scim even
    # for English, which is going a bit far.
    if 'HOME' in os.environ:
        files.append('%s/.xinput.d/%s' % (os.environ['HOME'], lang))
        #files.append('%s/.xinput.d/all_ALL' % os.environ['HOME'])
    files.append('/etc/X11/xinit/xinput.d/%s' % lang)
    #files.append('/etc/X11/xinit/xinput.d/all_ALL')
    #files.append('/etc/X11/xinit/xinput.d/default')

    for f in files:
        cfg_dict = read_config_file(f)
        if cfg_dict is not None:
            return cfg_dict
    return {}


def subprocess_setup():
    misc.drop_all_privileges()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    os.setsid()


_im_subps = []


# Entry point
def start_im():
    global _im_subps

    if 'DISPLAY' not in os.environ or os.environ['DISPLAY'] == '':
        return

    kill_im()

    cfg = read_config()

    def cfg_has(var):
        return (var in cfg and cfg[var])

    if not cfg_has('XMODIFIERS') and cfg_has('XIM'):
        cfg['XMODIFIERS'] = '@im=%s' % cfg['XIM']

    for var in ('GTK_IM_MODULE', 'QT_IM_MODULE', 'XMODIFIERS'):
        if cfg_has(var):
            os.environ[var] = cfg[var]
        elif var in os.environ:
            del os.environ[var]

    # Inform GTK about the change if necessary; requires
    # http://bugzilla.gnome.org/show_bug.cgi?id=502446.
    if (cfg_has('GTK_IM_MODULE') and
            'UBIQUITY_FRONTEND' in os.environ and
            os.environ['UBIQUITY_FRONTEND'] == 'gtk_ui'):
        from gi.repository import Gtk
        settings = Gtk.Settings.get_default()
        try:
            settings.set_string_property(
                'gtk-im-module', cfg['GTK_IM_MODULE'], '')
        except TypeError:
            pass

    _im_subps = []
    if cfg_has('XIM_PROGRAM') and os.access(cfg['XIM_PROGRAM'], os.X_OK):
        if cfg_has('XIM_ARGS'):
            program = os.path.basename(cfg['XIM_PROGRAM'])
            if program in ('scim', 'skim') and '-d' in cfg['XIM_ARGS']:
                import re
                cfg['XIM_ARGS'] = re.sub(r'-d', '', cfg['XIM_ARGS'])
            args = ' %s' % cfg['XIM_ARGS']
        else:
            args = ''
        args = shlex.split(args)
        args.insert(0, cfg['XIM_PROGRAM'])
        _im_subps.append(subprocess.Popen(args, preexec_fn=subprocess_setup))

    if cfg_has('XIM_PROGRAM_XTRA'):
        _im_subps.append(subprocess.Popen([cfg['XIM_PROGRAM_XTRA']],
                                          preexec_fn=subprocess_setup))


def kill_im():
    global _im_subps

    for subp in _im_subps:
        os.killpg(subp.pid, signal.SIGTERM)
    for subp in _im_subps:
        subp.wait()
    _im_subps = []
