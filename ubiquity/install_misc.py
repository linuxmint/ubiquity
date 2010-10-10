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

from apt.progress.text import AcquireProgress
from apt.progress.base import InstallProgress
import traceback
import syslog
import fcntl
import sys
from apt.cache import Cache
from hashlib import md5

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

class DebconfAcquireProgress(AcquireProgress):
    """An object that reports apt's fetching progress using debconf."""

    def __init__(self, db, title, info_starting, info):
        AcquireProgress.__init__(self)
        self.db = db
        self.title = title
        self.info_starting = info_starting
        self.info = info
        self.old_capb = None
        self.eta = 0.0

    def start(self):
        if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
            self.db.progress('START', 0, 100, self.title)
        if self.info_starting is not None:
            self.db.progress('INFO', self.info_starting)
        self.old_capb = self.db.capb()
        capb_list = self.old_capb.split()
        capb_list.append('progresscancel')
        self.db.capb(' '.join(capb_list))

    # TODO cjwatson 2006-02-27: implement updateStatus

    def pulse(self,owner=None):
        AcquireProgress.pulse(self,owner)
        self.percent = (((self.current_bytes + self.current_items) * 100.0) /
                        float(self.total_bytes + self.total_items))
        if self.current_cps > 0:
            self.eta = ((self.total_bytes - self.current_bytes) /
                        float(self.current_cps))

        try:
            if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
                self.db.progress('SET', int(self.percent))
        except debconf.DebconfError:
            return False
        if self.eta != 0.0:
            time_str = "%d:%02d" % divmod(int(self.eta), 60)
            self.db.subst(self.info, 'TIME', time_str)
            try:
                self.db.progress('INFO', self.info)
            except debconf.DebconfError:
                return False
        return True

    def stop(self):
        if self.old_capb is not None:
            self.db.capb(self.old_capb)
            self.old_capb = None
            if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
                self.db.progress('STOP')

class DebconfInstallProgress(InstallProgress):
    """An object that reports apt's installation progress using debconf."""

    def __init__(self, db, title, info, error=None):
        InstallProgress.__init__(self)
        self.db = db
        self.title = title
        self.info = info
        self.error_template = error
        self.started = False
        # InstallProgress uses a non-blocking status fd; our run()
        # implementation doesn't need that, and in fact we spin unless the
        # fd is blocking.
        flags = fcntl.fcntl(self.status_stream.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(self.status_stream.fileno(), fcntl.F_SETFL,
                    flags & ~os.O_NONBLOCK)

    def startUpdate(self):
        if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
            self.db.progress('START', 0, 100, self.title)
        self.started = True

    def error(self, pkg, errormsg):
        if self.error_template is not None:
            self.db.subst(self.error_template, 'PACKAGE', pkg)
            self.db.subst(self.error_template, 'MESSAGE', errormsg)
            self.db.input('critical', self.error_template)
            self.db.go()

    def statusChange(self, dummypkg, percent, status):
        self.percent = percent
        self.status = status
        if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
            self.db.progress('SET', int(percent))
        self.db.subst(self.info, 'DESCRIPTION', status)
        self.db.progress('INFO', self.info)

    def run(self, pm):
        # Create a subprocess to deal with turning apt status messages into
        # debconf protocol messages.
        child_pid = self.fork()
        if child_pid == 0:
            # child
            self.write_stream.close()
            try:
                while self.update_interface():
                    pass
            except (KeyboardInterrupt, SystemExit):
                pass # we're going to exit anyway
            except:
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_WARNING, line)
            os._exit(0)

        self.status_stream.close()

        # Redirect stdin from /dev/null and stdout to stderr to avoid them
        # interfering with our debconf protocol stream.
        saved_stdin = os.dup(0)
        try:
            null = os.open('/dev/null', os.O_RDONLY)
            os.dup2(null, 0)
            os.close(null)
        except OSError:
            pass
        saved_stdout = os.dup(1)
        os.dup2(2, 1)

        # Make sure all packages are installed non-interactively. We
        # don't have enough passthrough magic here to deal with any
        # debconf questions they might ask.
        saved_environ_keys = ('DEBIAN_FRONTEND', 'DEBIAN_HAS_FRONTEND',
                              'DEBCONF_USE_CDEBCONF')
        saved_environ = {}
        for key in saved_environ_keys:
            if key in os.environ:
                saved_environ[key] = os.environ[key]
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
        if 'DEBIAN_HAS_FRONTEND' in os.environ:
            del os.environ['DEBIAN_HAS_FRONTEND']
        if 'DEBCONF_USE_CDEBCONF' in os.environ:
            # Probably not a good idea to use this in /target too ...
            del os.environ['DEBCONF_USE_CDEBCONF']

        res = pm.ResultFailed
        try:
            res = pm.do_install(self.write_stream.fileno())
        finally:
            # Reap the status-to-debconf subprocess.
            self.write_stream.close()
            while True:
                try:
                    (pid, status) = os.waitpid(child_pid, 0)
                    if pid != child_pid:
                        break
                    if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                        break
                except OSError:
                    break

            # Put back stdin and stdout.
            os.dup2(saved_stdin, 0)
            os.close(saved_stdin)
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)

            # Put back the environment.
            for key in saved_environ_keys:
                if key in saved_environ:
                    os.environ[key] = saved_environ[key]
                elif key in os.environ:
                    del os.environ[key]

        return res

    def finishUpdate(self):
        if self.started:
            if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
                self.db.progress('STOP')
            self.started = False

class InstallStepError(Exception):
    """Raised when an install step fails."""

    def __init__(self, message):
        Exception.__init__(self, message)

def excepthook(exctype, excvalue, exctb):
    """Crash handler. Dump the traceback to a file so that it can be
    read by the caller."""

    if (issubclass(exctype, KeyboardInterrupt) or
        issubclass(exctype, SystemExit)):
        return

    tbtext = ''.join(traceback.format_exception(exctype, excvalue, exctb))
    syslog.syslog(syslog.LOG_ERR, "Exception during installation:")
    for line in tbtext.split('\n'):
        syslog.syslog(syslog.LOG_ERR, line)
    tbfile = open('/var/lib/ubiquity/install.trace', 'w')
    print >>tbfile, tbtext
    tbfile.close()

    sys.exit(1)

def archdetect():
    archdetect = subprocess.Popen(['archdetect'], stdout=subprocess.PIPE)
    answer = archdetect.communicate()[0].strip()
    try:
        return answer.split('/', 1)
    except ValueError:
        return answer, ''

# TODO this can probably go away now.
def get_cache_pkg(cache, pkg):
    # work around broken has_key in python-apt 0.6.16
    try:
        return cache[pkg]
    except KeyError:
        return None

def broken_packages(cache):
    expect_count = cache._depcache.broken_count
    count = 0
    brokenpkgs = set()
    for pkg in cache.keys():
        try:
            if cache._depcache.is_inst_broken(cache._cache[pkg]):
                brokenpkgs.add(pkg)
                count += 1
        except KeyError:
            # Apparently sometimes the cache goes a bit bonkers ...
            continue
        if count >= expect_count:
            break
    return brokenpkgs

def mark_install(cache, pkg):
    cachedpkg = get_cache_pkg(cache, pkg)
    if cachedpkg is not None and not cachedpkg.is_installed:
        apt_error = False
        try:
            cachedpkg.mark_install()
        except SystemError:
            apt_error = True
        if cache._depcache.broken_count > 0 or apt_error:
            brokenpkgs = broken_packages(cache)
            while brokenpkgs:
                for brokenpkg in brokenpkgs:
                    get_cache_pkg(cache, brokenpkg).mark_keep()
                new_brokenpkgs = broken_packages(cache)
                if brokenpkgs == new_brokenpkgs:
                    break # we can do nothing more
                brokenpkgs = new_brokenpkgs
            assert cache._depcache.broken_count == 0

def expand_dependencies_simple(cache, keep, to_remove, recommends=True):
    """Return the list of packages in to_remove that clearly cannot be removed
    if we want to keep the set of packages in keep. Except in the case of
    Recommends, this is not required for correctness (we could just let apt
    figure it out), but it allows us to ask apt fewer separate questions, and
    so is faster."""

    keys = ['Pre-Depends', 'Depends']
    if recommends:
        keys.append('Recommends')

    to_scan = set(keep)
    to_scan_next = set()
    expanded = set(keep)
    while to_scan:
        for pkg in to_scan:
            cachedpkg = get_cache_pkg(cache, pkg)
            if cachedpkg is None:
                continue
            ver = cachedpkg._pkg.current_ver
            if ver is None:
                continue
            for key in keys:
                if key in ver.depends_list:
                    for dep_or in ver.depends_list[key]:
                        # Keep the first element of a disjunction that's
                        # installed; this mirrors what 'apt-get install' would
                        # do if you were installing the package from scratch.
                        # This doesn't handle versioned dependencies, but
                        # that's largely OK since apt will spot those later;
                        # the only case I can think of where this might have
                        # trouble is "Recommends: foo (>= 2) | bar".
                        for dep in dep_or:
                            depname = dep.target_pkg.name
                            cacheddep = get_cache_pkg(cache, depname)
                            if cacheddep is None:
                                continue
                            if cacheddep._pkg.current_ver is not None:
                                break
                        else:
                            continue
                        if depname in expanded or depname not in to_remove:
                            continue
                        expanded.add(depname)
                        to_scan_next.add(depname)
        to_scan = to_scan_next
        to_scan_next = set()

    return expanded

def locale_to_language_pack(locale):
    lang = locale.split('.')[0]
    if lang == 'zh_CN':
        return 'zh-hans'
    elif lang == 'zh_TW':
        return 'zh-hant'
    else:
        lang = locale.split('_')[0]
        return lang

def get_remove_list(cache, to_remove, recursive=False):
    to_remove = set(to_remove)
    all_removed = set()
    while True:
        removed = set()
        for pkg in to_remove:
            cachedpkg = get_cache_pkg(cache, pkg)
            if cachedpkg is not None and cachedpkg.is_installed:
                apt_error = False
                try:
                    cachedpkg.mark_delete(autoFix=False, purge=True)
                except SystemError:
                    apt_error = True
                if apt_error:
                    cachedpkg.mark_keep()
                elif cache._depcache.broken_count > 0:
                    # If we're recursively removing packages, or if all
                    # of the broken packages are in the set of packages
                    # to remove anyway, then go ahead and try to remove
                    # them too.
                    brokenpkgs = broken_packages(cache)
                    broken_removed = set()
                    while brokenpkgs and (recursive or
                                          brokenpkgs <= to_remove):
                        broken_removed_inner = set()
                        for pkg2 in brokenpkgs:
                            cachedpkg2 = get_cache_pkg(cache, pkg2)
                            if cachedpkg2 is not None:
                                broken_removed_inner.add(pkg2)
                                try:
                                    cachedpkg2.mark_delete(autoFix=False,
                                                          purge=True)
                                except SystemError:
                                    apt_error = True
                                    break
                        broken_removed |= broken_removed_inner
                        if apt_error or not broken_removed_inner:
                            break
                        brokenpkgs = broken_packages(cache)
                    if apt_error or cache._depcache.broken_count > 0:
                        # That didn't work. Revert all the removals we
                        # just tried.
                        for pkg2 in broken_removed:
                            get_cache_pkg(cache, pkg2).mark_keep()
                        cachedpkg.mark_keep()
                    else:
                        removed.add(pkg)
                        removed |= broken_removed
                else:
                    removed.add(pkg)
                assert cache._depcache.broken_count == 0
        if not removed:
            break
        to_remove -= removed
        all_removed |= removed
    return all_removed

def copy_file(db, sourcepath, targetpath, md5_check):
    sourcefh = None
    targetfh = None
    try:
        while 1:
            sourcefh = open(sourcepath, 'rb')
            targetfh = open(targetpath, 'wb')
            if md5_check:
                sourcehash = md5()
            while 1:
                buf = sourcefh.read(16 * 1024)
                if not buf:
                    break
                targetfh.write(buf)
                if md5_check:
                    sourcehash.update(buf)

            if not md5_check:
                break
            targetfh.close()
            targetfh = open(targetpath, 'rb')
            if md5_check:
                targethash = md5()
            while 1:
                buf = targetfh.read(16 * 1024)
                if not buf:
                    break
                targethash.update(buf)
            if targethash.digest() != sourcehash.digest():
                if targetfh:
                    targetfh.close()
                if sourcefh:
                    sourcefh.close()
                error_template = 'ubiquity/install/copying_error/md5'
                db.subst(error_template, 'FILE', targetpath)
                db.input('critical', error_template)
                db.go()
                response = db.get(error_template)
                if response == 'skip':
                    break
                elif response == 'abort':
                    syslog.syslog(syslog.LOG_ERR,
                        'MD5 failure on %s' % targetpath)
                    sys.exit(3)
                elif response == 'retry':
                    pass
            else:
                break
    finally:
        if targetfh:
            targetfh.close()
        if sourcefh:
            sourcefh.close()

class InstallBase:
    def warn_broken_packages(self, pkgs, err):
        pkgs = ', '.join(pkgs)
        syslog.syslog('broken packages after installation: %s' % pkgs)
        self.db.subst('ubiquity/install/broken_install', 'ERROR', err)
        self.db.subst('ubiquity/install/broken_install', 'PACKAGES', pkgs)
        self.db.input('critical', 'ubiquity/install/broken_install')
        self.db.go()

    def progress_region(self, start, end):
        if os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui':
            self.db.progress('REGION', start, end)

    def next_region(self, size=1):
        self.db.progress('SET', self.count)
        self.progress_region(self.count, self.count + size)
        self.prev_count = self.count
        self.count += size

    def nested_progress_start(self):
        if os.environ['UBIQUITY_FRONTEND'] == 'debconf_ui':
            self.db.progress('STOP')

    def nested_progress_end(self):
        if os.environ['UBIQUITY_FRONTEND'] == 'debconf_ui':
            self.db.progress('START', self.start, self.end,
                             'ubiquity/install/title')
            self.db.progress('SET', self.prev_count)

    def do_install(self, to_install, langpacks=False):
        self.nested_progress_start()

        if langpacks:
            self.db.progress('START', 0, 10, 'ubiquity/langpacks/title')
        else:
            self.db.progress('START', 0, 10, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/find_installables')

        self.progress_region(0, 1)
        fetchprogress = DebconfAcquireProgress(
            self.db, 'ubiquity/install/title',
            'ubiquity/install/apt_indices_starting',
            'ubiquity/install/apt_indices')
        cache = Cache()

        if cache._depcache.broken_count > 0:
            syslog.syslog(
                'not installing additional packages, since there are broken '
                'packages: %s' % ', '.join(broken_packages(cache)))
            self.db.progress('STOP')
            self.nested_progress_end()
            return

        for pkg in to_install:
            mark_install(cache, pkg)

        self.db.progress('SET', 1)
        self.progress_region(1, 10)
        if langpacks:
            fetchprogress = DebconfAcquireProgress(
                self.db, 'ubiquity/langpacks/title', None,
                'ubiquity/langpacks/packages')
            installprogress = DebconfInstallProgress(
                self.db, 'ubiquity/langpacks/title',
                'ubiquity/install/apt_info')
        else:
            fetchprogress = DebconfAcquireProgress(
                self.db, 'ubiquity/install/title', None,
                'ubiquity/install/fetch_remove')
            installprogress = DebconfInstallProgress(
                self.db, 'ubiquity/install/title',
                'ubiquity/install/apt_info',
                'ubiquity/install/apt_error_install')
        chroot_setup(self.target)
        commit_error = None
        try:
            try:
                if not cache.commit(fetchprogress, installprogress):
                    fetchprogress.stop()
                    installprogress.finishUpdate()
                    self.db.progress('STOP')
                    self.nested_progress_end()
                    return
            except IOError:
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                fetchprogress.stop()
                installprogress.finishUpdate()
                self.db.progress('STOP')
                self.nested_progress_end()
                return
            except SystemError, e:
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                commit_error = str(e)
        finally:
            chroot_cleanup(self.target)
        self.db.progress('SET', 10)

        cache.open(None)
        if commit_error or cache._depcache.broken_count > 0:
            if commit_error is None:
                commit_error = ''
            brokenpkgs = broken_packages(cache)
            self.warn_broken_packages(brokenpkgs, commit_error)

        self.db.progress('STOP')

        self.nested_progress_end()

    def select_language_packs(self, save=False):
        try:
            keep_packages = self.db.get('ubiquity/keep-installed')
            keep_packages = keep_packages.replace(',', '').split()
            syslog.syslog('keeping packages due to preseeding: %s' %
                          ' '.join(keep_packages))
            record_installed(keep_packages)
        except debconf.DebconfError:
            pass

        langpacks = []
        all_langpacks = False
        try:
            langpack_db = self.db.get('pkgsel/language-packs')
            if langpack_db == 'ALL':
                apt_out = subprocess.Popen(
                    ['apt-cache', '-n', 'search', '^language-pack-[^-][^-]*$'],
                    stdout=subprocess.PIPE).communicate()[0].rstrip().split('\n')
                langpacks = map(lambda x: x.split('-')[2].strip(), apt_out)
                all_langpacks = True
            else:
                langpacks = langpack_db.replace(',', '').split()
        except debconf.DebconfError:
            pass
        if not langpacks:
            try:
                langpack_db = self.db.get('localechooser/supported-locales')
                langpack_set = set()
                for locale in langpack_db.replace(',', '').split():
                    langpack_set.add(locale_to_language_pack(locale))
                langpacks = sorted(langpack_set)
            except debconf.DebconfError:
                pass
        if not langpacks:
            langpack_db = self.db.get('debian-installer/locale')
            langpacks = [locale_to_language_pack(langpack_db)]

        if len(langpacks) == 1 and langpacks[0] in ('C', 'en'):
            # Touch
            with file('/var/lib/ubiquity/no-install-langpacks', 'a'):
                os.utime('/var/lib/ubiquity/no-install-langpacks', None)

        syslog.syslog('keeping language packs for: %s' % ' '.join(langpacks))

        try:
            lppatterns = self.db.get('pkgsel/language-pack-patterns').split()
        except debconf.DebconfError:
            return

        cache = Cache()

        to_install = []
        checker = osextras.find_on_path('check-language-support')
        for lp in langpacks:
            # Basic language packs, required to get localisation working at
            # all. We install these almost unconditionally; if you want to
            # get rid of even these, you can preseed pkgsel/language-packs
            # to the empty string.
            to_install.append('language-pack-%s' % lp)
            # Other language packs, typically selected by preseeding.
            for pattern in lppatterns:
                to_install.append(pattern.replace('$LL', lp))
            # More extensive language support packages.
            # If pkgsel/language-packs is ALL, then speed things up by
            # calling check-language-support just once.
            if not all_langpacks and checker:
                check_lang = subprocess.Popen(
                    ['check-language-support', '-l', lp, '--show-installed'],
                    stdout=subprocess.PIPE)
                to_install.extend(check_lang.communicate()[0].strip().split())
            else:
                to_install.append('language-support-%s' % lp)
            if checker:
                # Keep language-support-$LL installed if it happens to be in
                # the live filesystem, since there's no point spending time
                # removing it; but don't install it if it isn't in the live
                # filesystem.
                toplevel = 'language-support-%s' % lp
                toplevel_pkg = get_cache_pkg(cache, toplevel)
                if toplevel_pkg and toplevel_pkg.is_installed:
                    to_install.append(toplevel)
        if all_langpacks and osextras.find_on_path('check-language-support'):
            check_lang = subprocess.Popen(
                ['check-language-support', '-a', '--show-installed'],
                stdout=subprocess.PIPE)
            to_install.extend(check_lang.communicate()[0].strip().split())

        # Filter the list of language packs to include only language packs
        # that exist in the live filesystem's apt cache, so that we can tell
        # the difference between "no such language pack" and "language pack
        # not retrievable given apt configuration in /target" later on.
        to_install = [lp for lp in to_install
                         if get_cache_pkg(cache, lp) is not None]

        install_new = True
        try:
            install_new_key = \
                self.db.get('pkgsel/install-language-support') == 'true'
            if install_new_key != '' and not misc.create_bool(install_new_key):
                install_new = False
        except debconf.DebconfError:
            pass

        if not install_new:
            # Keep packages that are on the live filesystem, but don't install
            # new ones.
            # TODO cjwatson 2010-03-18: To match pkgsel's semantics, we ought to
            # be willing to install packages from the package pool on the CD as
            # well.
            to_install = [lp for lp in to_install
                             if get_cache_pkg(cache, lp).is_installed]

        del cache

        record_installed(to_install)
        if install_new:
            if save:
                langpacks_file = '/var/lib/ubiquity/langpacks'
                if not os.path.exists(os.path.dirname(langpacks_file)):
                    os.makedirs(os.path.dirname(langpacks_file))
                with open(langpacks_file, 'w') as langpacks:
                    for pkg in to_install:
                        print >>langpacks, pkg
                return []
            else:
                return to_install

# vim:ai:et:sts=4:tw=80:sw=4:
