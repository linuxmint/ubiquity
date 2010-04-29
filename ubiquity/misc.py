#!/usr/bin/python
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

import os
import pwd
import re
import subprocess
import syslog
import shutil
import contextlib

from ubiquity import osextras
from ubiquity.parted_server import PartedServer

def is_swap(device):
    swap = False
    try:
        fp = open('/proc/swaps')
        for line in fp:
            if line.startswith(device + ' '):
                swap = True
    except:
        swap = False
    finally:
        if fp:
            fp.close()
    return swap

_dropped_privileges = 0

def drop_all_privileges():
    # gconf needs both the UID and effective UID set.
    global _dropped_privileges
    if 'SUDO_GID' in os.environ:
        gid = int(os.environ['SUDO_GID'])
        os.setregid(gid, gid)
    if 'SUDO_UID' in os.environ:
        uid = int(os.environ['SUDO_UID'])
        os.setreuid(uid, uid)
        os.environ['HOME'] = pwd.getpwuid(uid).pw_dir
    _dropped_privileges = None

def drop_privileges():
    global _dropped_privileges
    assert _dropped_privileges is not None
    if _dropped_privileges == 0:
        if 'SUDO_GID' in os.environ:
            gid = int(os.environ['SUDO_GID'])
            os.setegid(gid)
        if 'SUDO_UID' in os.environ:
            uid = int(os.environ['SUDO_UID'])
            os.seteuid(uid)
    _dropped_privileges += 1

def regain_privileges():
    global _dropped_privileges
    assert _dropped_privileges is not None
    _dropped_privileges -= 1
    if _dropped_privileges == 0:
        os.seteuid(0)
        os.setegid(0)

def drop_privileges_save():
    """Drop the real UID/GID as well, and hide them in saved IDs."""
    # At the moment, we only know how to handle this when effective
    # privileges were already dropped.
    assert _dropped_privileges is not None and _dropped_privileges > 0
    if 'SUDO_GID' in os.environ:
        gid = int(os.environ['SUDO_GID'])
        osextras.setresgid(gid, gid, 0)
    if 'SUDO_UID' in os.environ:
        uid = int(os.environ['SUDO_UID'])
        osextras.setresuid(uid, uid, 0)

def regain_privileges_save():
    """Recover our real UID/GID after calling drop_privileges_save."""
    assert _dropped_privileges is not None and _dropped_privileges > 0
    osextras.setresuid(0, -1, 0)
    osextras.setresgid(0, -1, 0)

@contextlib.contextmanager
def raised_privileges():
    """As regain_privileges/drop_privileges, but in context manager style."""
    regain_privileges()
    try:
        yield
    finally:
        drop_privileges()

def raise_privileges(func):
    """As raised_privileges, but as a function decorator."""
    from functools import wraps

    @wraps(func)
    def helper(*args, **kwargs):
        with raised_privileges():
            return func(*args, **kwargs)

    return helper

@raise_privileges
def grub_options():
    """ Generates a list of suitable targets for grub-installer
        @return empty list or a list of ['/dev/sda1','Ubuntu Hardy 8.04'] """
    l = []
    try:
        oslist = {}
        subp = subprocess.Popen(['os-prober'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        result = subp.communicate()[0].splitlines()
        for res in result:
            res = res.split(':')
            oslist[res[0]] = res[1]
        p = PartedServer()
        for disk in p.disks():
            p.select_disk(disk)
            dev = ''
            mod = ''
            size = ''
            try:
                fp = open(p.device_entry('model'))
                mod = fp.readline()
                fp.close()
                fp = open(p.device_entry('device'))
                dev = fp.readline()
                fp.close()
                fp = open(p.device_entry('size'))
                size = fp.readline()
                fp.close()
            finally:
                if fp:
                    fp.close()
            if dev and mod:
                if size.isdigit():
                    size = format_size(int(size))
                    l.append([dev, '%s (%s)' % (mod, size)])
                else:
                    l.append([dev, mod])
            for part in p.partitions():
                ostype = ''
                if part[4] == 'linux-swap':
                    continue
                if os.path.exists(p.part_entry(part[1], 'format')):
                    pass
                elif part[5] in oslist.keys():
                    ostype = oslist[part[5]]
                l.append([part[5], ostype])
    except:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    return l

@raise_privileges
def grub_default():
    """Return the default GRUB installation target."""

    # Much of this is intentionally duplicated from grub-installer, so that
    # we can show the user what device GRUB will be installed to before
    # grub-installer is run.  Pursuant to that, we intentionally run this in
    # the installer root as /target might not yet be available.

    subp = subprocess.Popen(['grub-mkdevicemap', '--no-floppy', '-m', '-'],
                            stdout=subprocess.PIPE)
    devices = subp.communicate()[0].splitlines()
    target = None
    if devices:
        try:
            target = devices[0].split('\t')[1]
        except IndexError:
            pass
    # last resort
    if target is None:
        target = '(hd0)'

    cdsrc = ''
    cdfs = ''
    with contextlib.closing(open('/proc/mounts')) as fp:
        for line in fp:
            line = line.split()
            if line[1] == '/cdrom':
                cdsrc = line[0]
                cdfs = line[2]
                break
    if (cdsrc == target or target == '(hd0)') and cdfs and cdfs != 'iso9660':
        # Installing from removable media other than a CD.  Make sure that
        # we don't accidentally install GRUB to it.
        try:
            boot = ''
            root = ''
            p = PartedServer()
            for disk in p.disks():
                p.select_disk(disk)
                for part in p.partitions():
                    part = part[1]
                    if p.has_part_entry(part, 'mountpoint'):
                        mp = p.readline_part_entry(part, 'mountpoint')
                        if mp == '/boot':
                            boot = disk.replace('=', '/')
                        elif mp == '/':
                            root = disk.replace('=', '/')
            if boot or root:
                if boot:
                    target = boot
                else:
                    target = root
                return re.sub(r'(/dev/(cciss|ida)/c[0-9]d[0-9]|/dev/[a-z]+).*',
                              r'\1', target)
        except Exception:
            import traceback
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_ERR, line)

    return target

@raise_privileges
def find_in_os_prober(device):
    '''Look for the device name in the output of os-prober.
       Returns the friendly name of the device, or the empty string on error.'''
    try:
        if not find_in_os_prober.called:
            find_in_os_prober.called = True
            subp = subprocess.Popen(['os-prober'], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            result = subp.communicate()[0].splitlines()
            for res in result:
                res = res.split(':')
                find_in_os_prober.oslist[res[0]] = res[1]
        if device in find_in_os_prober.oslist:
            ret = find_in_os_prober.oslist[device]
        elif is_swap(device):
            ret = 'swap'
        else:
            syslog.syslog('Device %s not found in os-prober output' % str(device))
            ret = ''
        return unicode(ret, 'utf-8', 'replace')
    except (KeyboardInterrupt, SystemExit):
        pass
    except:
        import traceback
        syslog.syslog(syslog.LOG_ERR, "Error in find_in_os_prober:")
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    return unicode('')
find_in_os_prober.oslist = {}
find_in_os_prober.called = False

@raise_privileges
def remove_os_prober_cache():
    osextras.unlink_force('/var/lib/ubiquity/os-prober-cache')
    shutil.rmtree('/var/lib/ubiquity/linux-boot-prober-cache',
                  ignore_errors=True)

def get_release_name():
    if not get_release_name.release_name:
        fp = None
        try:
            fp = open('/cdrom/.disk/info')
            line = fp.readline()
            if line:
                line = line.split()
                if line[2] == 'LTS':
                    get_release_name.release_name = ' '.join(line[:3])
                else:
                    get_release_name.release_name = ' '.join(line[:2])
        except:
            syslog.syslog(syslog.LOG_ERR,
                "Unable to determine the distribution name from /cdrom/.disk/info")
        finally:
            if fp:
                fp.close()
        if not get_release_name.release_name:
            get_release_name.release_name = 'Ubuntu'
    return get_release_name.release_name
get_release_name.release_name = ''

@raise_privileges
def get_install_medium():
    if not get_install_medium.medium:
        try:
            if os.access('/cdrom', os.W_OK):
                get_install_medium.medium = 'USB'
            else:
                get_install_medium.medium = 'CD'
        except:
            syslog.syslog(syslog.LOG_ERR,
                "Unable to determine install medium.")
            get_install_medium.medium = 'CD'
    return get_install_medium.medium
get_install_medium.medium = ''

def execute(*args):
    """runs args* in shell mode. Output status is taken."""

    log_args = ['log-output', '-t', 'ubiquity']
    log_args.extend(args)

    try:
        status = subprocess.call(log_args)
    except IOError, e:
        syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
        syslog.syslog(syslog.LOG_ERR,
                      "OS error(%s): %s" % (e.errno, e.strerror))
        return False
    else:
        if status != 0:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            return False
        syslog.syslog(' '.join(log_args))
        return True

@raise_privileges
def execute_root(*args):
    return execute(*args)

def format_size(size):
    """Format a partition size."""
    if size < 1000:
        unit = 'B'
        factor = 1
    elif size < 1000 * 1000:
        unit = 'kB'
        factor = 1000
    elif size < 1000 * 1000 * 1000:
        unit = 'MB'
        factor = 1000 * 1000
    elif size < 1000 * 1000 * 1000 * 1000:
        unit = 'GB'
        factor = 1000 * 1000 * 1000
    else:
        unit = 'TB'
        factor = 1000 * 1000 * 1000 * 1000
    return '%.1f %s' % (float(size) / factor, unit)

def debconf_escape(text):
    escaped = text.replace('\\', '\\\\').replace('\n', '\\n')
    return re.sub(r'(\s)', r'\\\1', escaped)

def create_bool(text):
    if text == 'true':
        return True
    elif text == 'false':
        return False
    else:
        return text

# vim:ai:et:sts=4:tw=80:sw=4:
