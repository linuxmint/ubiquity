#!/usr/bin/python
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005, 2006, 2007, 2008, 2009 Canonical Ltd.
# Copyright (C) 2010 Mario Limonciello
#
# Functions useful for the final install.py script and for ubiquity
# plugins to use
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

import subprocess
import os
import debconf
from ubiquity import misc
from ubiquity import osextras
import re
import shutil

def debconf_disconnect():
    """Disconnect from debconf. This is only to be used as a subprocess
    preexec_fn helper."""
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    if 'DEBIAN_HAS_FRONTEND' in os.environ:
        del os.environ['DEBIAN_HAS_FRONTEND']
    if 'DEBCONF_USE_CDEBCONF' in os.environ:
        # Probably not a good idea to use this in /target too ...
        del os.environ['DEBCONF_USE_CDEBCONF']

def reconfigure_preexec():
    debconf_disconnect()
    os.environ['XAUTHORITY'] = '/root/.Xauthority'

def reconfigure(target, package):
    """executes a dpkg-reconfigure into installed system to each
    package which provided by args."""
    subprocess.call(['log-output', '-t', 'ubiquity', 'chroot', target,
                     'dpkg-reconfigure', '-fnoninteractive', package],
                    preexec_fn=reconfigure_preexec, close_fds=True)

def chrex(target, *args):
    """executes commands on chroot system (provided by *args)."""
    return misc.execute('chroot', target, *args)

def set_debconf(target, question, value, db=None):
    try:
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ and db:
            dccomm = None
            dc = db
        else:
            dccomm = subprocess.Popen(['log-output', '-t', 'ubiquity',
                                       '--pass-stdout',
                                       'chroot', target,
                                       'debconf-communicate',
                                       '-fnoninteractive', 'ubiquity'],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, close_fds=True)
            dc = debconf.Debconf(read=dccomm.stdout, write=dccomm.stdin)
        dc.set(question, value)
        dc.fset(question, 'seen', 'true')
    finally:
        if dccomm:
            dccomm.stdin.close()
            dccomm.wait()

def get_all_interfaces():
    """Get all non-local network interfaces."""
    ifs = []
    ifs_file = open('/proc/net/dev')
    # eat header
    ifs_file.readline()
    ifs_file.readline()

    for line in ifs_file:
        name = re.match('(.*?(?::\d+)?):', line.strip()).group(1)
        if name == 'lo':
            continue
        ifs.append(name)

    ifs_file.close()
    return ifs

def chroot_setup(target, x11=False):
    """Set up /target for safe package management operations."""
    if target == '/':
        return

    policy_rc_d = os.path.join(target, 'usr/sbin/policy-rc.d')
    f = open(policy_rc_d, 'w')
    print >>f, """\
#!/bin/sh
exit 101"""
    f.close()
    os.chmod(policy_rc_d, 0755)

    start_stop_daemon = os.path.join(target, 'sbin/start-stop-daemon')
    if os.path.exists(start_stop_daemon):
        os.rename(start_stop_daemon, '%s.REAL' % start_stop_daemon)
    f = open(start_stop_daemon, 'w')
    print >>f, """\
#!/bin/sh
echo 1>&2
echo 'Warning: Fake start-stop-daemon called, doing nothing.' 1>&2
exit 0"""
    f.close()
    os.chmod(start_stop_daemon, 0755)

    initctl = os.path.join(target, 'sbin/initctl')
    if os.path.exists(initctl):
        os.rename(initctl, '%s.REAL' % initctl)
        f = open(initctl, 'w')
        print >>f, """\
#!/bin/sh
echo 1>&2
echo 'Warning: Fake initctl called, doing nothing.' 1>&2
exit 0"""
        f.close()
        os.chmod(initctl, 0755)

    if not os.path.exists(os.path.join(target, 'proc/cmdline')):
        chrex(target, 'mount', '-t', 'proc', 'proc', '/proc')
    if not os.path.exists(os.path.join(target, 'sys/devices')):
        chrex(target, 'mount', '-t', 'sysfs', 'sysfs', '/sys')
    misc.execute('mount', '--bind', '/dev', os.path.join(target, 'dev'))

    if x11 and 'DISPLAY' in os.environ:
        if 'SUDO_USER' in os.environ:
            xauthority = os.path.expanduser('~%s/.Xauthority' %
                                            os.environ['SUDO_USER'])
        else:
            xauthority = os.path.expanduser('~/.Xauthority')
        if os.path.exists(xauthority):
            shutil.copy(xauthority,
                        os.path.join(target, 'root/.Xauthority'))

        if not os.path.isdir(os.path.join(target, 'tmp/.X11-unix')):
            os.mkdir(os.path.join(target, 'tmp/.X11-unix'))
        misc.execute('mount', '--bind', '/tmp/.X11-unix',
                     os.path.join(target, 'tmp/.X11-unix'))

def chroot_cleanup(target, x11=False):
    """Undo the work done by chroot_setup."""
    if target == '/':
        return

    if x11 and 'DISPLAY' in os.environ:
        misc.execute('umount', os.path.join(target, 'tmp/.X11-unix'))
        try:
            os.rmdir(os.path.join(target, 'tmp/.X11-unix'))
        except OSError:
            pass
        osextras.unlink_force(os.path.join(target,
                                           'root/.Xauthority'))

    chrex(target, 'umount', '/sys')
    chrex(target, 'umount', '/proc')
    misc.execute('umount', os.path.join(target, 'dev'))

    initctl = os.path.join(target, 'sbin/initctl')
    if os.path.exists('%s.REAL' % initctl):
        os.rename('%s.REAL' % initctl, initctl)

    start_stop_daemon = os.path.join(target, 'sbin/start-stop-daemon')
    if os.path.exists('%s.REAL' % start_stop_daemon):
        os.rename('%s.REAL' % start_stop_daemon, start_stop_daemon)
    else:
        osextras.unlink_force(start_stop_daemon)

    policy_rc_d = os.path.join(target, 'usr/sbin/policy-rc.d')
    osextras.unlink_force(policy_rc_d)

def record_installed(pkgs):
    """Record which packages we've explicitly installed so that we don't
    try to remove them later."""

    record_file = "/var/lib/ubiquity/apt-installed"
    if not os.path.exists(os.path.dirname(record_file)):
        os.makedirs(os.path.dirname(record_file))
    record = open(record_file, "a")

    for pkg in pkgs:
        print >>record, pkg

    record.close()

def query_recorded_installed():
    apt_installed = set()
    if os.path.exists("/var/lib/ubiquity/apt-installed"):
        record_file = open("/var/lib/ubiquity/apt-installed")
        for line in record_file:
            apt_installed.add(line.strip())
        record_file.close()
    return apt_installed

def record_removed(pkgs, recursive=False):
    """Record which packages we've like removed later"""

    record_file = "/var/lib/ubiquity/apt-removed"
    if not os.path.exists(os.path.dirname(record_file)):
        os.makedirs(os.path.dirname(record_file))
    record = open(record_file, "a")

    for pkg in pkgs:
        print >>record, pkg, str(recursive).lower()

    record.close()

def query_recorded_removed():
    apt_removed = set()
    apt_removed_recursive = set()
    if os.path.exists("/var/lib/ubiquity/apt-removed"):
        record_file = open("/var/lib/ubiquity/apt-removed")
        for line in record_file:
            if misc.create_bool(line.split()[1]):
                apt_removed_recursive.add(line.split()[0])
            else:
                apt_removed.add(line.split()[0])
        record_file.close()
    return (apt_removed, apt_removed_recursive)

# vim:ai:et:sts=4:tw=80:sw=4:
