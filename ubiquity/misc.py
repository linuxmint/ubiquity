#!/usr/bin/python
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

import os
import pwd
import re
import subprocess
import syslog

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

def find_in_os_prober(device):
    '''Look for the device name in the output of os-prober.
       Returns the friendly name of the device, or the empty string on error.'''
    regain_privileges()
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
    finally:
        drop_privileges()
    return ''
find_in_os_prober.oslist = {}
find_in_os_prober.called = False

def get_release_name():
    if not get_release_name.release_name:
        fp = None
        try:
            fp = open('/cdrom/.disk/info')
            line = fp.readline()
            if line:
                get_release_name.release_name = ' '.join(line.split()[:2])
        except:
            syslog.syslog(syslog.LOG_ERR,
                "Unable to determine the distribution name from /cdrom/.disk/info")
        finally:
            if fp:
                fp.close()
        if not get_release_name.release_name:
            release_name = 'Ubuntu'
    return get_release_name.release_name
get_release_name.release_name = ''

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

def execute_root(*args):
    regain_privileges()
    execute(*args)
    drop_privileges()

def format_size(size):
    """Format a partition size."""
    if size < 1024:
        unit = 'B'
        factor = 1
    elif size < 1024 * 1024:
        unit = 'kB'
        factor = 1024
    elif size < 1024 * 1024 * 1024:
        unit = 'MB'
        factor = 1024 * 1024
    elif size < 1024 * 1024 * 1024 * 1024:
        unit = 'GB'
        factor = 1024 * 1024 * 1024
    else:
        unit = 'TB'
        factor = 1024 * 1024 * 1024 * 1024
    return '%.1f %s' % (float(size) / factor, unit)

def drop_all_privileges():
    # gconf needs both the UID and effective UID set.
    if 'SUDO_GID' in os.environ:
        gid = int(os.environ['SUDO_GID'])
        os.setregid(gid, gid)
    if 'SUDO_UID' in os.environ:
        uid = int(os.environ['SUDO_UID'])
        os.setreuid(uid, uid)
        os.environ['HOME'] = pwd.getpwuid(uid).pw_dir

def drop_privileges():
    if 'SUDO_GID' in os.environ:
        gid = int(os.environ['SUDO_GID'])
        os.setegid(gid)
    if 'SUDO_UID' in os.environ:
        uid = int(os.environ['SUDO_UID'])
        os.seteuid(uid)

def regain_privileges():
    os.seteuid(0)
    os.setegid(0)

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
