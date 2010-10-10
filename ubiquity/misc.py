#!/usr/bin/python
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

import os
import pwd
import grp
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

def set_groups_for_uid(uid):
    if uid == os.geteuid() or uid == os.getuid():
        return
    user = pwd.getpwuid(uid).pw_name
    try:
        os.setgroups([g.gr_gid for g in grp.getgrall() if user in g.gr_mem])
    except OSError:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)

def drop_all_privileges():
    # gconf needs both the UID and effective UID set.
    global _dropped_privileges
    uid = os.environ.get('SUDO_UID')
    gid = os.environ.get('SUDO_GID')
    if uid is not None:
        uid = int(uid)
        set_groups_for_uid(uid)
    if gid is not None:
        gid = int(gid)
        os.setregid(gid, gid)
    if uid is not None:
        uid = int(uid)
        os.setreuid(uid, uid)
        os.environ['HOME'] = pwd.getpwuid(uid).pw_dir
    _dropped_privileges = None

def drop_privileges():
    global _dropped_privileges
    assert _dropped_privileges is not None
    if _dropped_privileges == 0:
        uid = os.environ.get('SUDO_UID')
        gid = os.environ.get('SUDO_GID')
        if uid is not None:
            uid = int(uid)
            set_groups_for_uid(uid)
        if gid is not None:
            gid = int(gid)
            os.setegid(gid)
        if uid is not None:
            os.seteuid(uid)
    _dropped_privileges += 1

def regain_privileges():
    global _dropped_privileges
    assert _dropped_privileges is not None
    _dropped_privileges -= 1
    if _dropped_privileges == 0:
        os.seteuid(0)
        os.setegid(0)
        os.setgroups([])

def drop_privileges_save():
    """Drop the real UID/GID as well, and hide them in saved IDs."""
    # At the moment, we only know how to handle this when effective
    # privileges were already dropped.
    assert _dropped_privileges is not None and _dropped_privileges > 0
    uid = os.environ.get('SUDO_UID')
    gid = os.environ.get('SUDO_GID')
    if uid is not None:
        uid = int(uid)
        set_groups_for_uid(uid)
    if gid is not None:
        gid = int(gid)
        osextras.setresgid(gid, gid, 0)
    if uid is not None:
        osextras.setresuid(uid, uid, 0)

def regain_privileges_save():
    """Recover our real UID/GID after calling drop_privileges_save."""
    assert _dropped_privileges is not None and _dropped_privileges > 0
    osextras.setresuid(0, 0, 0)
    osextras.setresgid(0, 0, 0)
    os.setgroups([])

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
                if part[4] == 'free':
                    continue
                if os.path.exists(p.part_entry(part[1], 'format')):
                    # Don't bother looking for an OS type.
                    pass
                elif part[5] in oslist.keys():
                    ostype = oslist[part[5]]
                l.append([part[5], ostype])
    except:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    return l

def boot_device():
    boot = None
    root = None
    try:
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
    except Exception:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    if boot:
        return boot
    return root

def is_removable(device):
    if device is None:
        return None
    device = os.path.realpath(device)
    devpath = None
    is_partition = False
    removable_bus = False
    subp = subprocess.Popen(['udevadm', 'info', '-q', 'property',
                             '-n', device],
                            stdout=subprocess.PIPE)
    for line in subp.communicate()[0].splitlines():
        line = line.strip()
        if line.startswith('DEVPATH='):
            devpath = line[8:]
        elif line == 'DEVTYPE=partition':
            is_partition = True
        elif line == 'ID_BUS=usb' or line == 'ID_BUS=ieee1394':
            removable_bus = True

    if devpath is not None:
        if is_partition:
            devpath = os.path.dirname(devpath)
        is_removable = removable_bus
        try:
            if open('/sys%s/removable' % devpath).readline().strip() != '0':
                is_removable = True
        except IOError:
            pass
        if is_removable:
            try:
                subp = subprocess.Popen(['udevadm', 'info', '-q', 'name',
                                         '-p', devpath],
                                        stdout=subprocess.PIPE)
                return ('/dev/%s' %
                        subp.communicate()[0].splitlines()[0].strip())
            except Exception:
                pass

    return None

def mount_info(path):
    """Return the filesystem name, type, and ro/rw used for a given mountpoint."""
    fsname = ''
    fstype = ''
    writable = ''
    with contextlib.closing(open('/proc/mounts')) as fp:
        for line in fp:
            line = line.split()
            if line[1] == path:
                fsname = line[0]
                fstype = line[2]
                writable = line[3].split(',')[0]
    return fsname, fstype, writable

def udevadm_info(args):
    fullargs = ['udevadm', 'info', '-q', 'property']
    fullargs.extend(args)
    udevadm = {}
    subp = subprocess.Popen(fullargs, stdout=subprocess.PIPE)
    for line in subp.communicate()[0].splitlines():
        line = line.strip()
        if '=' not in line:
            continue
        name, value = line.split('=', 1)
        udevadm[name] = value
    return udevadm

def partition_to_disk(partition):
    """Convert a partition device to its disk device, if any."""
    udevadm_part = udevadm_info(['-n', partition])
    if ('DEVPATH' not in udevadm_part or
        udevadm_part.get('DEVTYPE') != 'partition'):
        return partition

    disk_syspath = '/sys%s' % udevadm_part['DEVPATH'].rsplit('/', 1)[0]
    udevadm_disk = udevadm_info(['-p', disk_syspath])
    return udevadm_disk.get('DEVNAME', partition)

@raise_privileges
def grub_default():
    """Return the default GRUB installation target."""

    # Much of this is intentionally duplicated from grub-installer, so that
    # we can show the user what device GRUB will be installed to before
    # grub-installer is run.  Pursuant to that, we intentionally run this in
    # the installer root as /target might not yet be available.

    bootremovable = is_removable(boot_device())
    if bootremovable is not None:
        return bootremovable

    subp = subprocess.Popen(['grub-mkdevicemap', '--no-floppy', '-m', '-'],
                            stdout=subprocess.PIPE)
    devices = subp.communicate()[0].splitlines()
    target = None
    if devices:
        try:
            target = os.path.realpath(devices[0].split('\t')[1])
        except (IndexError, OSError):
            pass
    # last resort
    if target is None:
        target = '(hd0)'

    cdsrc, cdfs, type = mount_info('/cdrom')
    cdsrc = partition_to_disk(cdsrc)
    try:
        # The target is usually under /dev/disk/by-id/, so string equality
        # is insufficient.
        same = os.path.samefile(cdsrc, target)
    except OSError:
        same = False
    if (same or target == '(hd0)') and cdfs and cdfs != 'iso9660':
        # Installing from removable media other than a CD.  Make sure that
        # we don't accidentally install GRUB to it.
        boot = boot_device()
        try:
            if boot:
                target = boot
            else:
                # Try the next disk along (which can't also be the CD source).
                target = os.path.realpath(devices[1].split('\t')[1])
            target = re.sub(r'(/dev/(cciss|ida)/c[0-9]d[0-9]|/dev/[a-z]+).*',
                            r'\1', target)
        except (IndexError, OSError):
            pass

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

from collections import namedtuple
def get_release():
    ReleaseInfo = namedtuple('ReleaseInfo', 'name, version')
    if get_release.release_info is None:
        #try:
        #    with open('/cdrom/.disk/info') as fp:
        #        line = fp.readline()
        #        if line:
        #            line = line.split()
        #            if line[2] == 'LTS':
        #                line[1] += ' LTS'
        #            get_release.release_info = ReleaseInfo(name=line[0], version=line[1])
        #except:
        #    syslog.syslog(syslog.LOG_ERR, 'Unable to determine the release.')

        #if not get_release.release_info:
        get_release.release_info = ReleaseInfo(name='Linux Mint', version='10')
    return get_release.release_info
get_release.release_info = None

def get_release_name():
    import warnings
    warnings.warn('get_release_name() is deprecated, '
                  'use get_release().name instead.',
                  category=DeprecationWarning)
    
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

@raise_privileges
def dmimodel():
    model = ''
    try:
        proc = subprocess.Popen(['dmidecode', '--string',
            'system-manufacturer'], stdout=subprocess.PIPE)
        manufacturer = proc.communicate()[0]
        if not manufacturer:
            return
        manufacturer = manufacturer.lower()
        if 'to be filled' in manufacturer:
            # Don't bother with products in development.
            return
        if 'bochs' in manufacturer or 'vmware' in manufacturer:
            model = 'virtual machine'
            # VirtualBox sets an appropriate system-product-name.
        else:
            if 'lenovo' in manufacturer or 'ibm' in manufacturer:
                key = 'system-version'
            else:
                key = 'system-product-name'
            proc = subprocess.Popen(['dmidecode', '--string', key],
                                    stdout=subprocess.PIPE)
            model = proc.communicate()[0]
        if 'apple' in manufacturer:
            # MacBook4,1 - strip the 4,1
            model = re.sub('[^a-zA-Z\s]', '', model)
        # Replace each gap of non-alphanumeric characters with a dash.
        # Ensure the resulting string does not begin or end with a dash.
        model = re.sub('[^a-zA-Z0-9]+', '-', model).rstrip('-').lstrip('-')
    except Exception:
        syslog.syslog(syslog.LOG_ERR, 'Unable to determine the model from DMI')
    return model

# vim:ai:et:sts=4:tw=80:sw=4:
