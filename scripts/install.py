#!/usr/bin/python
# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005 Javier Carranza and others for Guadalinex
# Copyright (C) 2005, 2006, 2007, 2008, 2009 Canonical Ltd.
# Copyright (C) 2007 Mario Limonciello
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

import sys
import os
import platform
import errno
import stat
import re
import textwrap
import shutil
import subprocess
import time
import struct
import socket
import fcntl
import traceback
import syslog
import gzip
import debconf
import warnings
warnings.filterwarnings("ignore", "apt API not stable yet", FutureWarning)
import apt_pkg
from apt.cache import Cache
from apt.progress import FetchProgress, InstallProgress
from hashlib import md5

sys.path.insert(0, '/usr/lib/ubiquity')

from ubiquity import misc
from ubiquity import install_misc
from ubiquity import osextras
from ubiquity import plugin_manager
from ubiquity.casper import get_casper
from ubiquity.components import apt_setup, hw_detect, check_kernels

class DebconfFetchProgress(FetchProgress):
    """An object that reports apt's fetching progress using debconf."""

    def __init__(self, db, title, info_starting, info):
        FetchProgress.__init__(self)
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

    def pulse(self):
        FetchProgress.pulse(self)
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
                while self.updateInterface():
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
            res = pm.DoInstall(self.write_stream.fileno())
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

class Install:

    def __init__(self):
        """Initial attributes."""

        if os.path.isdir('/rofs'):
            self.source = '/rofs'
        elif os.path.isdir('/UNIONFS'):
            # Klaus Knopper says this may not actually work very well
            # because it'll copy the WHOLE WORLD (~12GB).
            self.source = '/UNIONFS'
        else:
            self.source = '/var/lib/ubiquity/source'
        self.target = '/target'
        self.casper_path = os.path.join(
            '/cdrom', get_casper('LIVE_MEDIA_PATH', 'casper').lstrip('/'))
        self.kernel_version = platform.release()
        self.db = debconf.Debconf()
        self.languages = []
        self.langpacks = []
        self.blacklist = {}

        # Load plugins
        modules = plugin_manager.load_plugins()
        modules = plugin_manager.order_plugins(modules)
        self.plugins = [x for x in modules if hasattr(x, 'Install')]

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            self.source = None
            self.target = '/'
            return

        assert os.path.ismount(self.target), 'Failed to mount the target.'

        self.select_language_packs()
        self.select_ecryptfs()
        use_restricted = True
        try:
            if self.db.get('apt-setup/restricted') == 'false':
                use_restricted = False
        except debconf.DebconfError:
            pass
        if not use_restricted:
            self.restricted_cache = Cache()
        if self.db.get('ubiquity/install/generate-blacklist') == 'true':
            self.db.progress('START', 0, 100, 'ubiquity/install/title')
            self.db.progress('INFO', 'ubiquity/install/blacklist')
            self.generate_blacklist()

        apt_pkg.InitConfig()
        apt_pkg.Config.Set("Dir", self.target)
        apt_pkg.Config.Set("Dir::State::status",
                           os.path.join(self.target, 'var/lib/dpkg/status'))
        apt_pkg.Config.Set("APT::GPGV::TrustedKeyring",
                           os.path.join(self.target, 'etc/apt/trusted.gpg'))
        apt_pkg.Config.Set("Acquire::gpgv::Options::",
                           "--ignore-time-conflict")
        apt_pkg.Config.Set("DPkg::Options::", "--root=%s" % self.target)
        # We don't want apt-listchanges or dpkg-preconfigure, so just clear
        # out the list of pre-installation hooks.
        apt_pkg.Config.Clear("DPkg::Pre-Install-Pkgs")
        apt_pkg.InitSystem()

    def excepthook(self, exctype, excvalue, exctb):
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

    def run(self):
        """Run the install stage: copy everything to the target system, then
        configure it as necessary."""

        # Give one extra progress point for each plugin, on the assumption that
        # they don't run long.
        self.start = 0
        self.end = 22 + len(self.plugins)
        if self.target != '/':
            self.end += 74
        self.prev_count = 0
        self.count = 1

        self.db.progress('START', self.start, self.end, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/mounting_source')

        try:
            if self.source == '/var/lib/ubiquity/source':
                self.mount_source()

            if self.target != '/':
                self.next_region(size=74)
                try:
                    self.copy_all()
                except EnvironmentError, e:
                    if e.errno in (errno.ENOENT, errno.EIO, errno.EFAULT,
                                   errno.ENOTDIR, errno.EROFS):
                        if e.filename is None:
                            error_template = 'cd_hd_fault'
                        elif e.filename.startswith(self.target):
                            error_template = 'hd_fault'
                        else:
                            error_template = 'cd_fault'
                        error_template = ('ubiquity/install/copying_error/%s' %
                                          error_template)
                        self.db.subst(error_template, 'ERROR', str(e))
                        self.db.input('critical', error_template)
                        self.db.go()
                        # Exit code 3 signals to the frontend that we have
                        # handled this error.
                        sys.exit(3)
                    elif e.errno == errno.ENOSPC:
                        error_template = 'ubiquity/install/copying_error/no_space'
                        self.db.subst(error_template, 'ERROR', str(e))
                        self.db.input('critical', error_template)
                        self.db.go()
                        sys.exit(3)
                    else:
                        raise

            self.next_region()
            self.db.progress('INFO', 'ubiquity/install/network')
            self.configure_network()

            self.next_region()
            self.db.progress('INFO', 'ubiquity/install/apt')
            #self.configure_apt()

            self.configure_plugins()

            self.next_region()
            self.run_target_config_hooks()

            self.next_region(size=5)
            # Ignore failures from language pack installation.
            try:
                self.install_language_packs()
            except InstallStepError:
                pass
            except IOError:
                pass
            except SystemError:
                pass

            self.next_region()
            self.remove_unusable_kernels()

            self.next_region(size=4)
            self.db.progress('INFO', 'ubiquity/install/hardware')
            self.configure_hardware()

            # Tell apt-install to install packages directly from now on.
            apt_install_direct = open('/var/lib/ubiquity/apt-install-direct',
                                      'w')
            apt_install_direct.close()

            self.next_region()
            self.db.progress('INFO', 'ubiquity/install/bootloader')
            self.configure_bootloader()

            self.next_region()
            self.db.progress('INFO', 'ubiquity/install/installing')

            if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
                self.install_oem_extras()
            else:
                self.install_extras()

            self.next_region(size=4)
            self.db.progress('INFO', 'ubiquity/install/removing')
            if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
                try:
                    if misc.create_bool(self.db.get('oem-config/remove_extras')):
                        self.remove_oem_extras()
                except debconf.DebconfError:
                    pass
            else:
                self.remove_extras()

            try:
                self.copy_network_config()
            except:
                syslog.syslog(syslog.LOG_WARNING,
                    'Could not copy the network configuration:')
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_WARNING, line)
                self.db.input('critical', 'ubiquity/install/broken_network_copy')
                self.db.go()
            try:
                self.recache_apparmor()
            except:
                syslog.syslog(syslog.LOG_WARNING,
                    'Could not create an Apparmor cache:')
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_WARNING, line)
            try:
                self.copy_wallpaper_cache()
            except:
                syslog.syslog(syslog.LOG_WARNING,
                    'Could not copy wallpaper cache:')
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_WARNING, line)
            self.copy_dcd()

            self.db.progress('SET', self.count)
            self.db.progress('INFO', 'ubiquity/install/log_files')
            self.copy_logs()

            self.db.progress('SET', self.end)
        finally:
            self.cleanup()
            try:
                self.db.progress('STOP')
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                pass


    def copy_file(self, sourcepath, targetpath, md5_check):
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
                    self.db.subst(error_template, 'FILE', targetpath)
                    self.db.input('critical', error_template)
                    self.db.go()
                    response = self.db.get(error_template)
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

    def find_cd_kernel(self):
        """Find the boot kernel on the CD, if possible."""

        release_bits = os.uname()[2].split('-')
        if len(release_bits) >= 3:
            subarch = release_bits[2]
        else:
            subarch = None

        for prefix in ('vmlinux', 'vmlinuz'):
            kernel = os.path.join(self.casper_path, prefix)
            if os.path.exists(kernel):
                return kernel

            if subarch:
                kernel = os.path.join(self.casper_path, subarch, prefix)
                if os.path.exists(kernel):
                    return kernel

                kernel = os.path.join(self.casper_path,
                                      '%s-%s' % (prefix, subarch))
                if os.path.exists(kernel):
                    return kernel

        return None


    def archdetect(self):
        archdetect = subprocess.Popen(['archdetect'], stdout=subprocess.PIPE)
        answer = archdetect.communicate()[0].strip()
        try:
            return answer.split('/', 1)
        except ValueError:
            return answer, ''


    def generate_blacklist(self):
        manifest_desktop = os.path.join(self.casper_path,
                                        'filesystem.manifest-desktop')
        manifest = os.path.join(self.casper_path, 'filesystem.manifest')
        if (os.path.exists(manifest_desktop) and
            os.path.exists(manifest)):
            desktop_packages = set()
            manifest_file = open(manifest_desktop)
            for line in manifest_file:
                if line.strip() != '' and not line.startswith('#'):
                    desktop_packages.add(line.split()[0])
            manifest_file.close()
            live_packages = set()
            manifest_file = open(manifest)
            for line in manifest_file:
                if line.strip() != '' and not line.startswith('#'):
                    live_packages.add(line.split()[0])
            manifest_file.close()
            difference = live_packages - desktop_packages
        else:
            difference = set()

        cache = Cache()

        use_restricted = True
        try:
            if self.db.get('apt-setup/restricted') == 'false':
                use_restricted = False
        except debconf.DebconfError:
            pass
        if not use_restricted:
            for pkg in cache.keys():
                if (cache[pkg].isInstalled and
                    cache[pkg].section.startswith('restricted/')):
                    difference.add(pkg)

        # Keep packages we explicitly installed.
        keep = install_misc.query_recorded_installed()
        arch, subarch = self.archdetect()

        # Less than ideal.  Since we cannot know which bootloader we'll need
        # at file copy time, we should figure out why grub still fails when
        # apt-install-direct is present during configure_bootloader (code
        # removed).
        if arch in ('amd64', 'i386', 'lpia'):
            keep.add('grub')
            keep.add('grub-pc')
        elif (arch == 'armel' and
              subarch in ('dove', 'imx51', 'iop32x', 'ixp4xx', 'orion5x', 'omap')):
            keep.add('flash-kernel')
            if subarch == 'dove':
                keep.add('uboot-mkimage')
            elif subarch == 'imx51':
                keep.add('redboot-tools')
            elif subarch == 'omap':
                keep.add('uboot-envtools')
                keep.add('uboot-mkimage')
        elif arch == 'powerpc' and subarch != 'ps3':
            keep.add('yaboot')
            keep.add('hfsutils')

        #Even adding ubiquity as a depends to oem-config-{gtk,kde}
        #doesn't appear to force ubiquity and libdebian-installer4
        #to copy all of their files, so this does the trick.
        try:
            if self.db.get('oem-config/enable') == 'true':
                keep.add('ubiquity')
        except (debconf.DebconfError, IOError):
            pass

        difference -= self.expand_dependencies_simple(cache, keep, difference)

        # Consider only packages that don't have a prerm, and which can
        # therefore have their files removed without any preliminary work.
        difference = set(filter(
            lambda x: not os.path.exists('/var/lib/dpkg/info/%s.prerm' % x),
            difference))

        confirmed_remove = set()
        for pkg in sorted(difference):
            if pkg in confirmed_remove:
                continue
            would_remove = self.get_remove_list(cache, [pkg], recursive=True)
            if would_remove <= difference:
                confirmed_remove |= would_remove
                # Leave these marked for removal in the apt cache to speed
                # up further calculations.
            else:
                for removedpkg in would_remove:
                    cachedpkg = self.get_cache_pkg(cache, removedpkg)
                    cachedpkg.markKeep()
        difference = confirmed_remove

        if len(difference) == 0:
            del cache
            self.blacklist = {}
            return

        cmd = ['dpkg', '-L']
        cmd.extend(difference)
        subp = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res = subp.communicate()[0].splitlines()
        u = {}
        for x in res:
            u[x] = 1
        self.blacklist = u

    def copy_all(self):
        """Core copy process. This is the most important step of this
        stage. It clones live filesystem into a local partition in the
        selected hard disk."""

        self.db.progress('START', 0, 100, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/copying')

        fs_size = os.path.join(self.casper_path, 'filesystem.size')
        assert os.path.exists(fs_size), "Missing filesystem.size."
        with open(fs_size) as total_size_fp:
            total_size = int(total_size_fp.readline())

        # Progress bar handling:
        # We sample progress every half-second (assuming time.time() gives
        # us sufficiently good granularity) and use the average of progress
        # over the last minute or so to decide how much time remains. We
        # don't bother displaying any progress for the first ten seconds in
        # order to allow things to settle down, and we only update the "time
        # remaining" indicator at most every two seconds after that.

        copy_progress = 0
        copied_size, counter = 0, 0
        directory_times = []
        time_start = time.time()
        times = [(time_start, copied_size)]
        long_enough = False
        time_last_update = time_start
        debug = 'UBIQUITY_DEBUG' in os.environ
        if self.db.get('ubiquity/install/md5_check') == 'false':
            md5_check = False
        else:
            md5_check = True

        # Increase kernel flush times during bulk data copying to make it
        # more likely that small files are packed contiguously, which should
        # speed up initial boot times.
        dirty_writeback_centisecs = None
        dirty_expire_centisecs = None
        if os.path.exists('/proc/sys/vm/dirty_writeback_centisecs'):
            with open('/proc/sys/vm/dirty_writeback_centisecs') as dwc:
                dirty_writeback_centisecs = int(dwc.readline())
            with open('/proc/sys/vm/dirty_writeback_centisecs', 'w') as dwc:
                print >>dwc, '3000\n'
        if os.path.exists('/proc/sys/vm/dirty_expire_centisecs'):
            with open('/proc/sys/vm/dirty_expire_centisecs') as dec:
                dirty_expire_centisecs = int(dec.readline())
            with open('/proc/sys/vm/dirty_expire_centisecs', 'w') as dec:
                print >>dec, '6000\n'

        old_umask = os.umask(0)
        for dirpath, dirnames, filenames in os.walk(self.source):
            sp = dirpath[len(self.source) + 1:]
            for name in dirnames + filenames:
                relpath = os.path.join(sp, name)
                # /etc/fstab was legitimately created by partman, and
                # shouldn't be copied again.
                if relpath == "etc/fstab":
                    continue
                sourcepath = os.path.join(self.source, relpath)
                targetpath = os.path.join(self.target, relpath)
                st = os.lstat(sourcepath)
                mode = stat.S_IMODE(st.st_mode)
                if stat.S_ISLNK(st.st_mode):
                    if os.path.lexists(targetpath):
                        os.unlink(targetpath)
                    linkto = os.readlink(sourcepath)
                    os.symlink(linkto, targetpath)
                elif stat.S_ISDIR(st.st_mode):
                    if not os.path.isdir(targetpath):
                        os.mkdir(targetpath, mode)
                elif stat.S_ISCHR(st.st_mode):
                    os.mknod(targetpath, stat.S_IFCHR | mode, st.st_rdev)
                elif stat.S_ISBLK(st.st_mode):
                    os.mknod(targetpath, stat.S_IFBLK | mode, st.st_rdev)
                elif stat.S_ISFIFO(st.st_mode):
                    os.mknod(targetpath, stat.S_IFIFO | mode)
                elif stat.S_ISSOCK(st.st_mode):
                    os.mknod(targetpath, stat.S_IFSOCK | mode)
                elif stat.S_ISREG(st.st_mode):
                    if '/%s' % relpath in self.blacklist:
                        if debug:
                            syslog.syslog('Not copying %s' % relpath)
                        continue
                    osextras.unlink_force(targetpath)
                    self.copy_file(sourcepath, targetpath, md5_check)

                copied_size += st.st_size
                os.lchown(targetpath, st.st_uid, st.st_gid)
                if not stat.S_ISLNK(st.st_mode):
                    os.chmod(targetpath, mode)
                if stat.S_ISDIR(st.st_mode):
                    directory_times.append((targetpath, st.st_atime, st.st_mtime))
                # os.utime() sets timestamp of target, not link
                elif not stat.S_ISLNK(st.st_mode):
                    os.utime(targetpath, (st.st_atime, st.st_mtime))

                if int((copied_size * 90) / total_size) != copy_progress:
                    copy_progress = int((copied_size * 90) / total_size)
                    self.db.progress('SET', 10 + copy_progress)

                time_now = time.time()
                if (time_now - times[-1][0]) >= 0.5:
                    times.append((time_now, copied_size))
                    if not long_enough and time_now - times[0][0] >= 10:
                        long_enough = True
                    if long_enough and time_now - time_last_update >= 2:
                        time_last_update = time_now
                        while (time_now - times[0][0] > 60 and
                               time_now - times[1][0] >= 60):
                            times.pop(0)
                        speed = ((times[-1][1] - times[0][1]) /
                                 (times[-1][0] - times[0][0]))
                        if speed != 0:
                            time_remaining = int((total_size - copied_size) / speed)
                            if time_remaining < 60:
                                self.db.progress(
                                    'INFO', 'ubiquity/install/copying_minute')

        # Apply timestamps to all directories now that the items within them
        # have been copied.
        for dirtime in directory_times:
            (directory, atime, mtime) = dirtime
            try:
                os.utime(directory, (atime, mtime))
            except OSError:
                # I have no idea why I've been getting lots of bug reports
                # about this failing, but I really don't care. Ignore it.
                pass

        # Revert to previous kernel flush times.
        if dirty_writeback_centisecs is not None:
            with open('/proc/sys/vm/dirty_writeback_centisecs', 'w') as dwc:
                print >>dwc, dirty_writeback_centisecs
        if dirty_expire_centisecs is not None:
            with open('/proc/sys/vm/dirty_expire_centisecs', 'w') as dec:
                print >>dec, dirty_expire_centisecs

        # Try some possible locations for the kernel we used to boot. This
        # lets us save a couple of megabytes of CD space.
        bootdir = os.path.join(self.target, 'boot')
        kernel = self.find_cd_kernel()
        if kernel:
            prefix = os.path.basename(kernel).split('-', 1)[0]
            release = os.uname()[2]
            target_kernel = os.path.join(bootdir, '%s-%s' % (prefix, release))
            osextras.unlink_force(target_kernel)
            self.copy_file(kernel, target_kernel, md5_check)
            os.lchown(target_kernel, 0, 0)
            os.chmod(target_kernel, 0644)
            st = os.lstat(kernel)
            os.utime(target_kernel, (st.st_atime, st.st_mtime))

        os.umask(old_umask)

        self.db.progress('SET', 100)
        self.db.progress('STOP')


    def copy_dcd(self):
        """Copy the Distribution Channel Descriptor (DCD) file into the
        installed system."""

        dcd = '/cdrom/.disk/ubuntu_dist_channel'
        if os.path.exists(dcd):
            shutil.copy(dcd,
                os.path.join(self.target, 'var/lib/ubuntu_dist_channel'))

    def copy_logs(self):
        """copy log files into installed system."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

        target_dir = os.path.join(self.target, 'var/log/installer')
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        for log_file in ('/var/log/syslog', '/var/log/partman',
                         '/var/log/installer/version', '/var/log/casper.log',
                         '/var/log/installer/debug'):
            target_log_file = os.path.join(target_dir,
                                           os.path.basename(log_file))
            if os.path.isfile(log_file):
                if not misc.execute('cp', '-a', log_file, target_log_file):
                    syslog.syslog(syslog.LOG_ERR,
                                  'Failed to copy installation log file')
                os.chmod(target_log_file, stat.S_IRUSR | stat.S_IWUSR)
        media_info = '/cdrom/.disk/info'
        if os.path.isfile(media_info):
            try:
                target_media_info = \
                    os.path.join(self.target, 'var/log/installer/media-info')
                shutil.copy(media_info, target_media_info)
                os.chmod(target_media_info,
                         stat.S_IRUSR | stat.S_IWUSR |
                         stat.S_IRGRP | stat.S_IROTH)
            except (IOError, OSError):
                pass

        try:
            status = open(os.path.join(self.target, 'var/lib/dpkg/status'))
            status_gz = gzip.open(os.path.join(target_dir,
                                               'initial-status.gz'), 'w')
            while True:
                data = status.read(65536)
                if not data:
                    break
                status_gz.write(data)
            status_gz.close()
            status.close()
        except IOError:
            pass
        try:
            if self.db.get('oem-config/enable') == 'true':
                oem_id = self.db.get('oem-config/id')
                oem_id_file = open(
                    os.path.join(self.target, 'var/log/installer/oem-id'), 'w')
                print >>oem_id_file, oem_id
                oem_id_file.close()
        except (debconf.DebconfError, IOError):
            pass


    def mount_one_image(self, fsfile, mountpoint=None):
        if os.path.splitext(fsfile)[1] == '.cloop':
            blockdev_prefix = 'cloop'
        elif os.path.splitext(fsfile)[1] == '.squashfs':
            blockdev_prefix = 'loop'

        if blockdev_prefix == '':
            raise InstallStepError("No source device found for %s" % fsfile)

        dev = ''
        sysloops = filter(lambda x: x.startswith(blockdev_prefix),
                          os.listdir('/sys/block'))
        sysloops.sort()
        for sysloop in sysloops:
            try:
                sysloopf = open(os.path.join('/sys/block', sysloop, 'size'))
                sysloopsize = sysloopf.readline().strip()
                sysloopf.close()
                if sysloopsize == '0':
                    devnull = open('/dev/null')
                    if osextras.find_on_path('udevadm'):
                        udevinfo_cmd = ['udevadm', 'info']
                    else:
                        udevinfo_cmd = ['udevinfo']
                    udevinfo_cmd.extend(
                        ['-q', 'name', '-p', os.path.join('/block', sysloop)])
                    udevinfo = subprocess.Popen(
                        udevinfo_cmd, stdout=subprocess.PIPE, stderr=devnull)
                    devbase = udevinfo.communicate()[0]
                    devnull.close()
                    if udevinfo.returncode != 0:
                        devbase = sysloop
                    dev = '/dev/%s' % devbase
                    break
            except:
                continue

        if dev == '':
            raise InstallStepError("No loop device available for %s" % fsfile)

        misc.execute('losetup', dev, fsfile)
        if mountpoint is None:
            mountpoint = '/var/lib/ubiquity/%s' % sysloop
        if not os.path.isdir(mountpoint):
            os.mkdir(mountpoint)
        if not misc.execute('mount', dev, mountpoint):
            misc.execute('losetup', '-d', dev)
            misc.execute('mount', '-o', 'loop', fsfile, mountpoint)
            dev = 'unused'

        return (dev, mountpoint)

    def mount_source(self):
        """mounting loop system from cloop or squashfs system."""

        self.devs = []
        self.mountpoints = []

        if not os.path.isdir(self.source):
            syslog.syslog('mkdir %s' % self.source)
            os.mkdir(self.source)

        fs_preseed = self.db.get('ubiquity/install/filesystem-images')

        if fs_preseed == '':
            # Simple autodetection on unionfs systems
            mounts = open('/proc/mounts')
            for line in mounts:
                (device, fstype) = line.split()[1:3]
                if fstype == 'squashfs' and os.path.exists(device):
                    misc.execute('mount', '--bind', device, self.source)
                    self.mountpoints.append(self.source)
                    mounts.close()
                    return
            mounts.close()

            # Manual detection on non-unionfs systems
            fsfiles = [os.path.join(self.casper_path, 'filesystem.cloop'),
                       os.path.join(self.casper_path, 'filesystem.squashfs'),
                       '/cdrom/META/META.squashfs',
                       '/live/image/live/filesystem.squashfs']

            for fsfile in fsfiles:
                if fsfile != '' and os.path.isfile(fsfile):
                    dev, mountpoint = self.mount_one_image(fsfile, self.source)
                    self.devs.append(dev)
                    self.mountpoints.append(mountpoint)

        elif len(fs_preseed.split()) == 1:
            # Just one preseeded image.
            if not os.path.isfile(fs_preseed):
                raise InstallStepError(
                    "Preseeded filesystem image %s not found" % fs_preseed)

                dev, mountpoint = self.mount_one_image(fsfile, self.source)
                self.devs.append(dev)
                self.mountpoints.append(mountpoint)
        else:
            # OK, so we need to mount multiple images and unionfs them
            # together.
            for fsfile in fs_preseed.split():
                if not os.path.isfile(fsfile):
                    raise InstallStepError(
                        "Preseeded filesystem image %s not found" % fsfile)

                dev, mountpoint = self.mount_one_image(fsfile)
                self.devs.append(dev)
                self.mountpoints.append(mountpoint)

            assert self.devs
            assert self.mountpoints

            misc.execute('mount', '-t', 'unionfs', '-o',
                         'dirs=' + ':'.join(map(lambda x: '%s=ro' % x,
                                                self.mountpoints)),
                         'unionfs', self.source)
            self.mountpoints.append(self.source)

    def umount_source(self):
        """umounting loop system from cloop or squashfs system."""

        devs = self.devs
        devs.reverse()
        mountpoints = self.mountpoints
        mountpoints.reverse()

        for mountpoint in mountpoints:
            if not misc.execute('umount', mountpoint):
                raise InstallStepError("Failed to unmount %s" % mountpoint)
        for dev in devs:
            if (dev != '' and dev != 'unused' and
                not misc.execute('losetup', '-d', dev)):
                raise InstallStepError(
                    "Failed to detach loopback device %s" % dev)

    def run_target_config_hooks(self):
        """Run hook scripts from /usr/lib/ubiquity/target-config. This allows
        casper to hook into us and repeat bits of its configuration in the
        target system."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return # These were already run once during install

        hookdir = '/usr/lib/ubiquity/target-config'

        if os.path.isdir(hookdir):
            # Exclude hooks containing '.', so that *.dpkg-* et al are avoided.
            hooks = filter(lambda entry: '.' not in entry, os.listdir(hookdir))
            self.db.progress('START', 0, len(hooks), 'ubiquity/install/title')
            self.db.progress('INFO', 'ubiquity/install/target_hooks')
            for hookentry in hooks:
                hook = os.path.join(hookdir, hookentry)
                if not os.access(hook, os.X_OK):
                    self.db.progress('STEP', 1)
                    continue
                # Errors are ignored at present, although this may change.
                subprocess.call(['log-output', '-t', 'ubiquity',
                                 '--pass-stdout', hook])
                self.db.progress('STEP', 1)
            self.db.progress('STOP')


    def configure_plugins(self):
        """Apply plugin settings to installed system."""
        class Progress:
            def __init__(self, db):
                self._db = db
            def info(self, title):
                self._db.progress('INFO', title)
            def get(self, question):
                return self._db.get(question)
            def substitute(self, template, substr, data):
                self._db.subst(template, substr, data)

        for plugin in self.plugins:
            if plugin.NAME == 'migrationassistant' and \
                'UBIQUITY_MIGRATION_ASSISTANT' not in os.environ:
                    continue
            self.next_region()
            # set a generic info message in case plugin doesn't provide one
            self.db.progress('INFO', 'ubiquity/install/title')
            inst = plugin.Install(None, db=self.db)
            ret = inst.install(self.target, Progress(self.db))
            if ret:
                if plugin.NAME == 'migrationassistant':
                    self.db.input('critical', 'ubiquity/install/broken_migration')
                    self.db.go()
                else:
                    raise InstallStepError("Plugin %s failed with code %s" % (plugin.NAME, ret))

    def configure_apt(self):
        """Configure /etc/apt/sources.list."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return # apt will already be setup as the OEM wants

        # TODO cjwatson 2007-07-06: Much of the following is
        # cloned-and-hacked from base-installer/debian/postinst. Perhaps we
        # should come up with a way to avoid this.

        # Make apt trust CDs. This is not on by default (we think).
        # This will be left in place on the installed system.
        apt_conf_tc = open(os.path.join(
            self.target, 'etc/apt/apt.conf.d/00trustcdrom'), 'w')
        print >>apt_conf_tc, 'APT::Authentication::TrustCDROM "true";'
        apt_conf_tc.close()

        # Avoid clock skew causing gpg verification issues.
        # This file will be left in place until the end of the install.
        apt_conf_itc = open(os.path.join(
            self.target, 'etc/apt/apt.conf.d/00IgnoreTimeConflict'), 'w')
        print >>apt_conf_itc, \
            'Acquire::gpgv::Options { "--ignore-time-conflict"; };'
        apt_conf_itc.close()

        try:
            if self.db.get('debian-installer/allow_unauthenticated') == 'true':
                apt_conf_au = open(
                    os.path.join(self.target,
                                 'etc/apt/apt.conf.d/00AllowUnauthenticated'),
                    'w')
                print >>apt_conf_au, 'APT::Get::AllowUnauthenticated "true";'
                print >>apt_conf_au, \
                    'Aptitude::CmdLine::Ignore-Trust-Violations "true";'
                apt_conf_au.close()
        except debconf.DebconfError:
            pass

        # let apt inside the chroot see the cdrom
        if self.target != "/":
            target_cdrom = os.path.join(self.target, 'cdrom')
            misc.execute('umount', target_cdrom)
            if not os.path.exists(target_cdrom):
                os.mkdir(target_cdrom)
            misc.execute('mount', '--bind', '/cdrom', target_cdrom)

        # Make apt-cdrom and apt not unmount/mount CD-ROMs.
        # This file will be left in place until the end of the install.
        apt_conf_nmc = open(os.path.join(
            self.target, 'etc/apt/apt.conf.d/00NoMountCDROM'), 'w')
        print >>apt_conf_nmc, textwrap.dedent("""\
            APT::CDROM::NoMount "true";
            Acquire::cdrom {
              mount "/cdrom";
              "/cdrom/" {
                Mount  "true";
                UMount "true";
              };
              AutoDetect "false";
            }""")
        apt_conf_nmc.close()

        # This will be reindexed after installation based on the full
        # installed sources.list.
        try:
            shutil.rmtree(
                os.path.join(self.target, 'var/lib/apt-xapian-index'),
                ignore_errors=True)
        except OSError:
            pass

        dbfilter = apt_setup.AptSetup(None, self.db)
        ret = dbfilter.run_command(auto_process=True)
        if ret != 0:
            raise InstallStepError("AptSetup failed with code %d" % ret)


    def get_cache_pkg(self, cache, pkg):
        # work around broken has_key in python-apt 0.6.16
        try:
            return cache[pkg]
        except KeyError:
            return None

    def mark_install(self, cache, pkg):
        cachedpkg = self.get_cache_pkg(cache, pkg)
        if cachedpkg is not None and not cachedpkg.isInstalled:
            apt_error = False
            try:
                cachedpkg.markInstall()
            except SystemError:
                apt_error = True
            if cache._depcache.BrokenCount > 0 or apt_error:
                brokenpkgs = self.broken_packages(cache)
                while brokenpkgs:
                    for brokenpkg in brokenpkgs:
                        self.get_cache_pkg(cache, brokenpkg).markKeep()
                    new_brokenpkgs = self.broken_packages(cache)
                    if brokenpkgs == new_brokenpkgs:
                        break # we can do nothing more
                    brokenpkgs = new_brokenpkgs
                assert cache._depcache.BrokenCount == 0


    def locale_to_language_pack(self, locale):
        lang = locale.split('.')[0]
        if lang == 'zh_CN':
            return 'zh-hans'
        elif lang == 'zh_TW':
            return 'zh-hant'
        else:
            lang = locale.split('_')[0]
            return lang

    def select_language_packs(self):
        try:
            keep_packages = self.db.get('ubiquity/keep-installed')
            keep_packages = keep_packages.replace(',', '').split()
            syslog.syslog('keeping packages due to preseeding: %s' %
                          ' '.join(keep_packages))
            install_misc.record_installed(keep_packages)
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
                    langpack_set.add(self.locale_to_language_pack(locale))
                langpacks = sorted(langpack_set)
            except debconf.DebconfError:
                pass
        if not langpacks:
            langpack_db = self.db.get('debian-installer/locale')
            langpacks = [self.locale_to_language_pack(langpack_db)]
        self.languages = langpacks
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
                toplevel_pkg = self.get_cache_pkg(cache, toplevel)
                if toplevel_pkg and toplevel_pkg.isInstalled:
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
                         if self.get_cache_pkg(cache, lp) is not None]

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
                             if self.get_cache_pkg(cache, lp).isInstalled]

        del cache

        install_misc.record_installed(to_install)
        if install_new:
            self.langpacks = to_install

    def install_language_packs(self):

        if not self.langpacks:
            return

        self.do_install(self.langpacks)
        self.verify_language_packs()

    def verify_language_packs(self):

        if len(self.languages) == 1 and self.languages[0] in ('C', 'en'):
            return # always complete enough

        if self.db.get('pkgsel/ignore-incomplete-language-support') == 'true':
            return

        cache = Cache()
        incomplete = False
        for pkg in self.langpacks:
            if pkg.startswith('gimp-help-'):
                # gimp-help-common is far too big to fit on CDs, so don't
                # worry about it.
                continue
            cachedpkg = self.get_cache_pkg(cache, pkg)
            if cachedpkg is None or not cachedpkg.isInstalled:
                incomplete = True
                break
        if incomplete:
            language_support_dir = \
                os.path.join(self.target, 'usr/share/language-support')
            update_notifier_dir = \
                os.path.join(self.target, 'var/lib/update-notifier/user.d')
            for note in ('incomplete-language-support-gnome.note',
                         'incomplete-language-support-qt.note'):
                notepath = os.path.join(language_support_dir, note)
                if os.path.exists(notepath):
                    if not os.path.exists(update_notifier_dir):
                        os.makedirs(update_notifier_dir)
                    shutil.copy(notepath,
                                os.path.join(update_notifier_dir, note))
                    break


    def select_ecryptfs(self):
        """Is ecryptfs in use by an existing user? If so, keep it installed.

        This duplicates code from user-setup, but necessarily so; when
        user-setup-ask runs in ubiquity, /target is not yet mounted, but we
        need to make this decision before generating the file copy blacklist
        so user-setup-apply would be too late."""

        home = os.path.join(self.target, 'home')
        if os.path.isdir(home):
            for homedir in os.listdir(home):
                if os.path.isdir(os.path.join(home, homedir, '.ecryptfs')):
                    syslog.syslog('ecryptfs already in use in %s' %
                                  os.path.join(home, homedir))
                    install_misc.record_installed(['ecryptfs-utils'])
                    break

    def get_resume_partition(self):
        biggest_size = 0
        biggest_partition = None
        swaps = open('/proc/swaps')
        for line in swaps:
            words = line.split()
            if words[1] != 'partition':
                continue
            if not os.path.exists(words[0]):
                continue
            if words[0].startswith('/dev/ramzswap'):
                continue
            size = int(words[2])
            if size > biggest_size:
                biggest_size = size
                biggest_partition = words[0]
        swaps.close()
        return biggest_partition

    def configure_hardware(self):
        """reconfiguring several packages which depends on the
        hardware system in which has been installed on and need some
        automatic configurations to get work."""

        self.nested_progress_start()
        install_misc.chroot_setup(self.target)
        try:
            dbfilter = hw_detect.HwDetect(None, self.db)
            ret = dbfilter.run_command(auto_process=True)
            if ret != 0:
                raise InstallStepError("HwDetect failed with code %d" % ret)
        finally:
            install_misc.chroot_cleanup(self.target)
        self.nested_progress_end()

        self.db.progress('INFO', 'ubiquity/install/hardware')

        script = '/usr/lib/ubiquity/debian-installer-utils' \
                 '/register-module.post-base-installer'
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            script += '-oem'
        misc.execute(script)

        resume = self.get_resume_partition()
        if resume is not None:
            resume_uuid = None
            try:
                resume_uuid = subprocess.Popen(
                    ['block-attr', '--uuid', resume],
                    stdout=subprocess.PIPE).communicate()[0].rstrip('\n')
            except OSError:
                pass
            if resume_uuid:
                resume = "UUID=%s" % resume_uuid
            if os.path.exists(os.path.join(self.target,
                                           'etc/initramfs-tools/conf.d')):
                configdir = os.path.join(self.target,
                                         'etc/initramfs-tools/conf.d')
            elif os.path.exists(os.path.join(self.target,
                                             'etc/mkinitramfs/conf.d')):
                configdir = os.path.join(self.target,
                                         'etc/mkinitramfs/conf.d')
            else:
                configdir = None
            if configdir is not None:
                configfile = open(os.path.join(configdir, 'resume'), 'w')
                print >>configfile, "RESUME=%s" % resume
                configfile.close()

        osextras.unlink_force(os.path.join(self.target, 'etc/usplash.conf'))
        osextras.unlink_force(os.path.join(self.target,
                                           'etc/popularity-contest.conf'))
        try:
            participate = self.db.get('popularity-contest/participate')
            install_misc.set_debconf(self.target, 'popularity-contest/participate', participate, self.db)
        except debconf.DebconfError:
            pass

        osextras.unlink_force(os.path.join(self.target, 'etc/papersize'))
        subprocess.call(['log-output', '-t', 'ubiquity', 'chroot', self.target,
                         'ucf', '--purge', '/etc/papersize'],
                        preexec_fn=install_misc.debconf_disconnect, close_fds=True)
        try:
            install_misc.set_debconf(self.target, 'libpaper/defaultpaper', '', self.db)
        except debconf.DebconfError:
            pass

        osextras.unlink_force(os.path.join(
            self.target, 'etc/ssl/certs/ssl-cert-snakeoil.pem'))
        osextras.unlink_force(os.path.join(
            self.target, 'etc/ssl/private/ssl-cert-snakeoil.key'))

        install_misc.chroot_setup(self.target, x11=True)
        install_misc.chrex(self.target,'dpkg-divert', '--package', 'ubiquity', '--rename',
                   '--quiet', '--add', '/usr/sbin/update-initramfs')
        try:
            os.symlink('/bin/true', os.path.join(self.target,
                                                 'usr/sbin/update-initramfs'))
        except OSError:
            pass

        packages = ['linux-image-' + self.kernel_version,
                    'usplash',
                    'splashy',
                    'popularity-contest',
                    'libpaper1',
                    'ssl-cert']

        try:
            for package in packages:
                install_misc.reconfigure(self.target, package)
        finally:
            osextras.unlink_force(os.path.join(self.target,
                                               'usr/sbin/update-initramfs'))
            install_misc.chrex(self.target,'dpkg-divert', '--package', 'ubiquity', '--rename',
                       '--quiet', '--remove', '/usr/sbin/update-initramfs')
            install_misc.chrex(self.target,'update-initramfs', '-c', '-k', self.kernel_version)
            install_misc.chroot_cleanup(self.target, x11=True)

        # Fix up kernel symlinks now that the initrd exists. Depending on
        # the architecture, these may be in / or in /boot.
        bootdir = os.path.join(self.target, 'boot')
        if self.db.get('base-installer/kernel/linux/link_in_boot') == 'true':
            linkdir = bootdir
            linkprefix = ''
        else:
            linkdir = self.target
            linkprefix = 'boot'

        # Remove old symlinks. We'll set them up from scratch.
        re_symlink = re.compile('vmlinu[xz]|initrd.img$')
        for entry in os.listdir(linkdir):
            if re_symlink.match(entry) is not None:
                filename = os.path.join(linkdir, entry)
                if os.path.islink(filename):
                    os.unlink(filename)
        if linkdir != self.target:
            # Remove symlinks in /target too, which may have been created on
            # the live filesystem. This isn't necessary, but it may help
            # avoid confusion.
            for entry in os.listdir(self.target):
                if re_symlink.match(entry) is not None:
                    filename = os.path.join(self.target, entry)
                    if os.path.islink(filename):
                        os.unlink(filename)

        # Create symlinks. Prefer our current kernel version if possible,
        # but if not (perhaps due to a customised live filesystem image),
        # it's better to create some symlinks than none at all.
        re_image = re.compile('(vmlinu[xz]|initrd.img)-')
        for entry in os.listdir(bootdir):
            match = re_image.match(entry)
            if match is not None:
                imagetype = match.group(1)
                linksrc = os.path.join(linkprefix, entry)
                linkdst = os.path.join(linkdir, imagetype)
                if os.path.exists(linkdst):
                    if entry.endswith('-' + self.kernel_version):
                        os.unlink(linkdst)
                    else:
                        continue
                os.symlink(linksrc, linkdst)

    def configure_network(self):
        """Automatically configure the network.

        At present, the only thing the user gets to tweak in the UI is the
        hostname. Some other things will be copied from the live filesystem,
        so changes made there will be reflected in the installed system.

        Unfortunately, at present we have to duplicate a fair bit of netcfg
        here, because it's hard to drive netcfg in a way that won't try to
        bring interfaces up and down."""

        # TODO cjwatson 2006-03-30: just call netcfg instead of doing all
        # this; requires a netcfg binary that doesn't bring interfaces up
        # and down

        if self.target != '/':
            for path in ('/etc/network/interfaces', '/etc/resolv.conf'):
                if os.path.exists(path):
                    shutil.copy2(path, os.path.join(self.target, path[1:]))

        try:
            hostname = self.db.get('netcfg/get_hostname')
        except debconf.DebconfError:
            hostname = ''
        try:
            domain = self.db.get('netcfg/get_domain')
        except debconf.DebconfError:
            domain = ''
        if hostname == '':
            hostname = 'mint'

        hosts = open(os.path.join(self.target, 'etc/hosts'), 'w')
        print >>hosts, "127.0.0.1\tlocalhost"
        if domain:
            print >>hosts, "127.0.1.1\t%s.%s\t%s" % (hostname, domain,
                                                     hostname)
        else:
            print >>hosts, "127.0.1.1\t%s" % hostname
        print >>hosts, textwrap.dedent("""\

            # The following lines are desirable for IPv6 capable hosts
            ::1     localhost ip6-localhost ip6-loopback
            fe00::0 ip6-localnet
            ff00::0 ip6-mcastprefix
            ff02::1 ip6-allnodes
            ff02::2 ip6-allrouters
            ff02::3 ip6-allhosts""")
        hosts.close()

        # Network Manager's ifupdown plugin has an inotify watch on
        # /etc/hostname, which can trigger a race condition if /etc/hostname is
        # written and immediately followed with /etc/hosts.
        fp = open(os.path.join(self.target, 'etc/hostname'), 'w')
        print >>fp, hostname
        fp.close()

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            os.system("hostname %s" % hostname)

        persistent_net = '/etc/udev/rules.d/70-persistent-net.rules'
        if os.path.exists(persistent_net):
            if self.target != '/':
                shutil.copy2(persistent_net,
                             os.path.join(self.target, persistent_net[1:]))
        else:
            # TODO cjwatson 2006-03-30: from <bits/ioctls.h>; ugh, but no
            # binding available
            SIOCGIFHWADDR = 0x8927
            # <net/if_arp.h>
            ARPHRD_ETHER = 1

            if_names = {}
            sock = socket.socket(socket.SOCK_DGRAM)
            interfaces = install_misc.get_all_interfaces()
            for i in range(len(interfaces)):
                if_names[interfaces[i]] = struct.unpack('H6s',
                    fcntl.ioctl(sock.fileno(), SIOCGIFHWADDR,
                                struct.pack('256s', interfaces[i]))[16:24])
            sock.close()

            iftab = open(os.path.join(self.target, 'etc/iftab'), 'w')

            print >>iftab, textwrap.dedent("""\
                # This file assigns persistent names to network interfaces.
                # See iftab(5) for syntax.
                """)

            for i in range(len(interfaces)):
                dup = False

                if_name = if_names[interfaces[i]]
                if if_name is None or if_name[0] != ARPHRD_ETHER:
                    continue

                for j in range(len(interfaces)):
                    if i == j or if_names[interfaces[j]] is None:
                        continue
                    if if_name[1] != if_names[interfaces[j]][1]:
                        continue

                    if if_names[interfaces[j]][0] == ARPHRD_ETHER:
                        dup = True

                if dup:
                    continue

                line = (interfaces[i] + " mac " +
                        ':'.join(['%02x' % ord(if_name[1][c])
                                  for c in range(6)]))
                line += " arp %d" % if_name[0]
                print >>iftab, line

            iftab.close()


    def configure_bootloader(self):
        """configuring and installing boot loader into installed
        hardware system."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

        install_bootloader = self.db.get('ubiquity/install_bootloader')
        if install_bootloader == "true":
            misc.execute('mount', '--bind', '/proc', self.target + '/proc')
            misc.execute('mount', '--bind', '/sys', self.target + '/sys')
            misc.execute('mount', '--bind', '/dev', self.target + '/dev')

            arch, subarch = self.archdetect()

            try:
                if arch in ('amd64', 'i386', 'lpia'):
                    from ubiquity.components import grubinstaller
                    while 1:
                        dbfilter = grubinstaller.GrubInstaller(None, self.db)
                        ret = dbfilter.run_command(auto_process=True)
                        if ret != 0:
                            old_bootdev = self.db.get('grub-installer/bootdev')
                            bootdev = 'ubiquity/install/new-bootdev'
                            self.db.fset(bootdev, 'seen', 'false')
                            self.db.set(bootdev, old_bootdev)
                            self.db.input('critical', bootdev)
                            self.db.go()
                            response = self.db.get(bootdev)
                            if response == 'skip':
                                break
                            if not response:
                                raise InstallStepError(
                                    "GrubInstaller failed with code %d" % ret)
                            else:
                                self.db.set('grub-installer/bootdev', response)
                        else:
                            break
                elif (arch == 'armel' and
                      subarch in ('dove', 'imx51', 'iop32x', 'ixp4xx', 'orion5x', 'omap')):
                    from ubiquity.components import flash_kernel
                    dbfilter = flash_kernel.FlashKernel(None, self.db)
                    ret = dbfilter.run_command(auto_process=True)
                    if ret != 0:
                        raise InstallStepError(
                            "FlashKernel failed with code %d" % ret)
                elif arch == 'powerpc' and subarch == 'ps3':
                    from ubiquity.components import kbootinstaller
                    dbfilter = kbootinstaller.KbootInstaller(None, self.db)
                    ret = dbfilter.run_command(auto_process=True)
                    if ret != 0:
                        raise InstallStepError(
                            "KbootInstaller failed with code %d" % ret)
                elif arch == 'powerpc':
                    from ubiquity.components import yabootinstaller
                    dbfilter = yabootinstaller.YabootInstaller(None, self.db)
                    ret = dbfilter.run_command(auto_process=True)
                    if ret != 0:
                        raise InstallStepError(
                            "YabootInstaller failed with code %d" % ret)
                else:
                    raise InstallStepError("No bootloader installer found")
            except ImportError:
                raise InstallStepError("No bootloader installer found")

            misc.execute('umount', '-f', self.target + '/proc')
            misc.execute('umount', '-f', self.target + '/sys')
            misc.execute('umount', '-f', self.target + '/dev')


    def broken_packages(self, cache):
        expect_count = cache._depcache.BrokenCount
        count = 0
        brokenpkgs = set()
        for pkg in cache.keys():
            try:
                if cache._depcache.IsInstBroken(cache._cache[pkg]):
                    brokenpkgs.add(pkg)
                    count += 1
            except KeyError:
                # Apparently sometimes the cache goes a bit bonkers ...
                continue
            if count >= expect_count:
                break
        return brokenpkgs

    def warn_broken_packages(self, pkgs, err):
        pkgs = ', '.join(pkgs)
        syslog.syslog('broken packages after installation: %s' % pkgs)
        self.db.subst('ubiquity/install/broken_install', 'ERROR', err)
        self.db.subst('ubiquity/install/broken_install', 'PACKAGES', pkgs)
        self.db.input('critical', 'ubiquity/install/broken_install')
        self.db.go()

    def do_install(self, to_install):
        self.nested_progress_start()

        if self.langpacks:
            self.db.progress('START', 0, 10, 'ubiquity/langpacks/title')
        else:
            self.db.progress('START', 0, 10, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/find_installables')

        self.progress_region(0, 1)
        fetchprogress = DebconfFetchProgress(
            self.db, 'ubiquity/install/title',
            'ubiquity/install/apt_indices_starting',
            'ubiquity/install/apt_indices')
        cache = Cache()

        if cache._depcache.BrokenCount > 0:
            syslog.syslog(
                'not installing additional packages, since there are broken '
                'packages: %s' % ', '.join(self.broken_packages(cache)))
            self.db.progress('STOP')
            self.nested_progress_end()
            return

        for pkg in to_install:
            self.mark_install(cache, pkg)

        self.db.progress('SET', 1)
        self.progress_region(1, 10)
        if self.langpacks:
            fetchprogress = DebconfFetchProgress(
                self.db, 'ubiquity/langpacks/title', None,
                'ubiquity/langpacks/packages')
            installprogress = DebconfInstallProgress(
                self.db, 'ubiquity/langpacks/title',
                'ubiquity/install/apt_info')
        else:
            fetchprogress = DebconfFetchProgress(
                self.db, 'ubiquity/install/title', None,
                'ubiquity/install/fetch_remove')
            installprogress = DebconfInstallProgress(
                self.db, 'ubiquity/install/title',
                'ubiquity/install/apt_info',
                'ubiquity/install/apt_error_install')
        install_misc.chroot_setup(self.target)
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
            install_misc.chroot_cleanup(self.target)
        self.db.progress('SET', 10)

        cache.open(None)
        if commit_error or cache._depcache.BrokenCount > 0:
            if commit_error is None:
                commit_error = ''
            brokenpkgs = self.broken_packages(cache)
            self.warn_broken_packages(brokenpkgs, commit_error)

        self.db.progress('STOP')

        self.nested_progress_end()


    def expand_dependencies_simple(self, cache, keep, to_remove,
                                   recommends=True):
        """Return the list of packages in to_remove that clearly cannot be
        removed if we want to keep the set of packages in keep. Except in
        the case of Recommends, this is not required for correctness (we
        could just let apt figure it out), but it allows us to ask apt fewer
        separate questions, and so is faster."""

        keys = ['Pre-Depends', 'Depends']
        if recommends:
            keys.append('Recommends')

        to_scan = set(keep)
        to_scan_next = set()
        expanded = set(keep)
        while to_scan:
            for pkg in to_scan:
                cachedpkg = self.get_cache_pkg(cache, pkg)
                if cachedpkg is None:
                    continue
                ver = cachedpkg._pkg.CurrentVer
                if ver is None:
                    continue
                for key in keys:
                    if key in ver.DependsList:
                        for dep_or in ver.DependsList[key]:
                            # Keep the first element of a disjunction that's
                            # installed; this mirrors what 'apt-get install'
                            # would do if you were installing the package
                            # from scratch. This doesn't handle versioned
                            # dependencies, but that's largely OK since apt
                            # will spot those later; the only case I can
                            # think of where this might have trouble is
                            # "Recommends: foo (>= 2) | bar".
                            for dep in dep_or:
                                depname = dep.TargetPkg.Name
                                cacheddep = self.get_cache_pkg(cache, depname)
                                if cacheddep is None:
                                    continue
                                if cacheddep._pkg.CurrentVer is not None:
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


    def get_remove_list(self, cache, to_remove, recursive=False):
        to_remove = set(to_remove)
        all_removed = set()
        while True:
            removed = set()
            for pkg in to_remove:
                cachedpkg = self.get_cache_pkg(cache, pkg)
                if cachedpkg is not None and cachedpkg.isInstalled:
                    apt_error = False
                    try:
                        cachedpkg.markDelete(autoFix=False, purge=True)
                    except SystemError:
                        apt_error = True
                    if apt_error:
                        cachedpkg.markKeep()
                    elif cache._depcache.BrokenCount > 0:
                        # If we're recursively removing packages, or if all
                        # of the broken packages are in the set of packages
                        # to remove anyway, then go ahead and try to remove
                        # them too.
                        brokenpkgs = self.broken_packages(cache)
                        broken_removed = set()
                        while brokenpkgs and (recursive or
                                              brokenpkgs <= to_remove):
                            broken_removed_inner = set()
                            for pkg2 in brokenpkgs:
                                cachedpkg2 = self.get_cache_pkg(cache, pkg2)
                                if cachedpkg2 is not None:
                                    broken_removed_inner.add(pkg2)
                                    try:
                                        cachedpkg2.markDelete(autoFix=False,
                                                              purge=True)
                                    except SystemError:
                                        apt_error = True
                                        break
                            broken_removed |= broken_removed_inner
                            if apt_error or not broken_removed_inner:
                                break
                            brokenpkgs = self.broken_packages(cache)
                        if apt_error or cache._depcache.BrokenCount > 0:
                            # That didn't work. Revert all the removals we
                            # just tried.
                            for pkg2 in broken_removed:
                                self.get_cache_pkg(cache, pkg2).markKeep()
                            cachedpkg.markKeep()
                        else:
                            removed.add(pkg)
                            removed |= broken_removed
                    else:
                        removed.add(pkg)
                    assert cache._depcache.BrokenCount == 0
            if not removed:
                break
            to_remove -= removed
            all_removed |= removed
        return all_removed


    def do_remove(self, to_remove, recursive=False):
        self.nested_progress_start()

        self.db.progress('START', 0, 5, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/find_removables')

        fetchprogress = DebconfFetchProgress(
            self.db, 'ubiquity/install/title',
            'ubiquity/install/apt_indices_starting',
            'ubiquity/install/apt_indices')
        cache = Cache()

        if cache._depcache.BrokenCount > 0:
            syslog.syslog(
                'not processing removals, since there are broken packages: '
                '%s' % ', '.join(self.broken_packages(cache)))
            self.db.progress('STOP')
            self.nested_progress_end()
            return

        self.get_remove_list(cache, to_remove, recursive)

        self.db.progress('SET', 1)
        self.progress_region(1, 5)
        fetchprogress = DebconfFetchProgress(
            self.db, 'ubiquity/install/title', None,
            'ubiquity/install/fetch_remove')
        installprogress = DebconfInstallProgress(
            self.db, 'ubiquity/install/title', 'ubiquity/install/apt_info',
            'ubiquity/install/apt_error_remove')
        install_misc.chroot_setup(self.target)
        commit_error = None
        try:
            try:
                if not cache.commit(fetchprogress, installprogress):
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
            install_misc.chroot_cleanup(self.target)
        self.db.progress('SET', 5)

        cache.open(None)
        if commit_error or cache._depcache.BrokenCount > 0:
            if commit_error is None:
                commit_error = ''
            brokenpkgs = self.broken_packages(cache)
            syslog.syslog('broken packages after removal: '
                          '%s' % ', '.join(brokenpkgs))
            self.db.subst('ubiquity/install/broken_remove', 'ERROR',
                          commit_error)
            self.db.subst('ubiquity/install/broken_remove', 'PACKAGES',
                          ', '.join(brokenpkgs))
            self.db.input('critical', 'ubiquity/install/broken_remove')
            self.db.go()

        self.db.progress('STOP')

        self.nested_progress_end()

    def traverse_for_kernel(self, cache, pkg):
        kern = self.get_cache_pkg(cache, pkg)
        if kern is None:
            return None
        pkc = cache._depcache.GetCandidateVer(kern._pkg)
        if pkc.DependsList.has_key('Depends'):
            dependencies = pkc.DependsList['Depends']
        else:
            # Didn't find.
            return None
        for dep in dependencies:
            name = dep[0].TargetPkg.Name
            if name.startswith('linux-image-2.'):
                return name
            elif name.startswith('linux-'):
                return self.traverse_for_kernel(cache, name)

    def remove_unusable_kernels(self):
        """Remove unusable kernels; keeping them may cause us to be unable
        to boot."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

        self.db.progress('START', 0, 5, 'ubiquity/install/title')

        self.db.progress('INFO', 'ubiquity/install/find_removables')

        # Check for kernel packages to remove.
        dbfilter = check_kernels.CheckKernels(None, self.db)
        dbfilter.run_command(auto_process=True)

        install_kernels = set()
        new_kernel_pkg = None
        new_kernel_version = None
        if os.path.exists("/var/lib/ubiquity/install-kernels"):
            install_kernels_file = open("/var/lib/ubiquity/install-kernels")
            for line in install_kernels_file:
                kernel = line.strip()
                install_kernels.add(kernel)
                # If we decided to actively install a particular kernel like
                # this, it's probably because we prefer it to the default
                # one, so we'd better update kernel_version to match.
                if kernel.startswith('linux-image-2.'):
                    new_kernel_pkg = kernel
                    new_kernel_version = kernel[12:]
                elif kernel.startswith('linux-generic-'):
                    # Traverse dependencies to find the real kernel image.
                    cache = Cache()
                    kernel = self.traverse_for_kernel(cache, kernel)
                    if kernel:
                        new_kernel_pkg = kernel
                        new_kernel_version = kernel[12:]
            install_kernels_file.close()

        remove_kernels = set()
        if os.path.exists("/var/lib/ubiquity/remove-kernels"):
            remove_kernels_file = open("/var/lib/ubiquity/remove-kernels")
            for line in remove_kernels_file:
                remove_kernels.add(line.strip())
            remove_kernels_file.close()

        if len(install_kernels) == 0 and len(remove_kernels) == 0:
            self.db.progress('STOP')
            return

        # TODO cjwatson 2009-10-19: These regions are rather crude and
        # should be improved.
        self.db.progress('SET', 1)
        self.progress_region(1, 2)
        if install_kernels:
            self.do_install(install_kernels)
            if new_kernel_pkg:
                cache = Cache()
                cached_pkg = self.get_cache_pkg(cache, new_kernel_pkg)
                if cached_pkg is not None and cached_pkg.isInstalled:
                    self.kernel_version = new_kernel_version
                else:
                    remove_kernels = []
                del cache
            else:
                remove_kernels = []

        self.db.progress('SET', 2)
        self.progress_region(2, 5)
        try:
            if remove_kernels:
                install_misc.record_removed(remove_kernels, recursive=True)
        except:
            self.db.progress('STOP')
            raise
        self.db.progress('SET', 5)
        self.db.progress('STOP')


    def install_oem_extras(self):
        """Try to install additional packages requested by the distributor"""

        try:
            inst_langpacks = \
                self.db.get('oem-config/install-language-support') == 'true'
        except debconf.DebconfError:
            inst_langpacks = False
        if inst_langpacks:
            self.select_language_packs()

        try:
            extra_packages = self.db.get('oem-config/extra_packages')
            if extra_packages:
                extra_packages = extra_packages.replace(',', ' ').split()
            elif not inst_langpacks:
                return
            else:
                extra_packages = []
        except debconf.DebconfError:
            if not inst_langpacks:
                return

        if inst_langpacks:
            extra_packages += self.langpacks

        save_replace = None
        save_override = None
        custom = '/etc/apt/sources.list.d/oem-config.list'
        apt_update = ['debconf-apt-progress', '--', 'apt-get', 'update']
        trusted_db = '/etc/apt/trusted.gpg'
        try:
            if 'DEBCONF_DB_REPLACE' in os.environ:
                save_replace = os.environ['DEBCONF_DB_REPLACE']
            if 'DEBCONF_DB_OVERRIDE' in os.environ:
                save_override = os.environ['DEBCONF_DB_OVERRIDE']
            os.environ['DEBCONF_DB_REPLACE'] = 'configdb'
            os.environ['DEBCONF_DB_OVERRIDE'] = 'Pipe{infd:none outfd:none}'

            try:
                extra_pool = self.db.get('oem-config/repository')
            except debconf.DebconfError:
                extra_pool = ''
            try:
                extra_key = self.db.get('oem-config/key')
            except debconf.DebconfError:
                extra_key = ''

            if extra_pool:
                with open(custom, 'w') as f:
                    print >>f, extra_pool
            if extra_key and os.path.exists(extra_key):
                if os.path.exists(trusted_db):
                    shutil.copy(trusted_db, trusted_db + '.oem-config')
                subprocess.call(['apt-key', 'add', extra_key])
            if extra_pool:
                subprocess.call(apt_update)
            # We don't support asking questions on behalf of packages specified
            # here yet, as we don't support asking arbitrary questions in
            # components/install.py yet.  This is complicated not only by the
            # present lack of dialogs for string and multiselect, but also
            # because we don't have any way of discerning between questions
            # asked by this module and questions asked by packages being
            # installed.
            cmd = ['debconf-apt-progress', '--', 'apt-get', '-y', 'install']
            cmd += extra_packages
            try:
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError, e:
                if e.returncode != 30:
                    cache = Cache()
                    brokenpkgs = self.broken_packages(cache)
                    self.warn_broken_packages(brokenpkgs, str(e))
        finally:
            if os.path.exists(trusted_db + '.oem-config'):
                shutil.copy(trusted_db + '.oem-config', trusted_db)
            if os.path.exists(custom):
                os.unlink(custom)
                subprocess.call(apt_update)
            if save_replace:
                os.environ['DEBCONF_DB_REPLACE'] = save_replace
            if save_override:
                os.environ['DEBCONF_DB_OVERRIDE'] = save_override

        if inst_langpacks:
            self.verify_language_packs()

    def install_extras(self):
        """Try to install additional packages requested by installer
        components."""

        # We only ever install these packages from the CD.
        sources_list = os.path.join(self.target, 'etc/apt/sources.list')
        os.rename(sources_list, "%s.apt-setup" % sources_list)
        old_sources = open("%s.apt-setup" % sources_list)
        new_sources = open(sources_list, 'w')
        found_cdrom = False
        for line in old_sources:
            if 'cdrom:' in line:
                print >>new_sources, line,
                found_cdrom = True
        new_sources.close()
        old_sources.close()
        if not found_cdrom:
            os.rename("%s.apt-setup" % sources_list, sources_list)

        self.do_install(install_misc.query_recorded_installed())

        if found_cdrom:
            os.rename("%s.apt-setup" % sources_list, sources_list)

        # TODO cjwatson 2007-08-09: python reimplementation of
        # oem-config/finish-install.d/07oem-config-user. This really needs
        # to die in a great big chemical fire and call the same shell script
        # instead.
        try:
            if self.db.get('oem-config/enable') == 'true':
                if os.path.isdir(os.path.join(self.target, 'home/oem')):
                    open(os.path.join(self.target, 'home/oem/.hwdb'),
                         'w').close()

                    for desktop_file in (
                        'usr/share/applications/oem-config-prepare-gtk.desktop',
                        'usr/share/applications/kde4/oem-config-prepare-kde.desktop'):
                        if os.path.exists(os.path.join(self.target,
                                                       desktop_file)):
                            desktop_base = os.path.basename(desktop_file)
                            install_misc.chrex(self.target,'install', '-d',
                                       '-o', 'oem', '-g', 'oem',
                                       '/home/oem/Desktop')
                            install_misc.chrex(self.target,'install', '-o', 'oem', '-g', 'oem',
                                       '/%s' % desktop_file,
                                       '/home/oem/Desktop/%s' % desktop_base)
                            break

                # Carry the locale setting over to the installed system.
                # This mimics the behavior in 01oem-config-udeb.
                di_locale = self.db.get('debian-installer/locale')
                if di_locale:
                    install_misc.set_debconf(self.target, 'debian-installer/locale', di_locale, self.db)
                #in an automated install, this key needs to carry over
                installable_lang = self.db.get('ubiquity/only-show-installable-languages')
                if installable_lang:
                    install_misc.set_debconf(self.target,
                        'ubiquity/only-show-installable-languages',
                        installable_lang, self.db)
        except debconf.DebconfError:
            pass


    def remove_extras(self):
        """Try to remove packages that are needed on the live CD but not on
        the installed system."""

        # Looking through files for packages to remove is pretty quick, so
        # don't bother with a progress bar for that.

        # Check for packages specific to the live CD.
        manifest_desktop = os.path.join(self.casper_path,
                                        'filesystem.manifest-desktop')
        manifest = os.path.join(self.casper_path, 'filesystem.manifest')
        if (os.path.exists(manifest_desktop) and
            os.path.exists(manifest)):
            desktop_packages = set()
            manifest_file = open(manifest_desktop)
            for line in manifest_file:
                if line.strip() != '' and not line.startswith('#'):
                    desktop_packages.add(line.split()[0])
            manifest_file.close()
            live_packages = set()
            manifest_file = open(manifest)
            for line in manifest_file:
                if line.strip() != '' and not line.startswith('#'):
                    live_packages.add(line.split()[0])
            manifest_file.close()
            difference = live_packages - desktop_packages
        else:
            difference = set()

        # Keep packages we explicitly installed.
        keep = install_misc.query_recorded_installed()

        arch, subarch = self.archdetect()

        if arch in ('amd64', 'i386', 'lpia'):
            if 'grub' not in keep:
                difference.add('grub')
            if 'grub-pc' not in keep:
                difference.add('grub-pc')
            if 'lilo' not in keep:
                difference.add('lilo')

        cache = Cache()
        difference -= self.expand_dependencies_simple(cache, keep, difference)
        del cache

        if len(difference) == 0:
            return

        use_restricted = True
        try:
            if self.db.get('apt-setup/restricted') == 'false':
                use_restricted = False
        except debconf.DebconfError:
            pass
        if not use_restricted:
            cache = self.restricted_cache
            for pkg in cache.keys():
                if (cache[pkg].isInstalled and
                    cache[pkg].section.startswith('restricted/')):
                    difference.add(pkg)
            del cache

        install_misc.record_removed(difference)

        # Don't worry about failures removing packages; it will be easier
        # for the user to sort them out with a graphical package manager (or
        # whatever) after installation than it will be to try to deal with
        # them automatically here.
        (regular, recursive) = install_misc.query_recorded_removed()
        self.do_remove(regular)
        self.do_remove(recursive, recursive=True)

        oem_remove_extras = False
        try:
            oem_remove_extras = misc.create_bool(self.db.get('oem-config/remove_extras'))
        except debconf.DebconfError:
            pass

        if oem_remove_extras:
            installed = (desktop_packages | keep - regular - recursive)
            p = os.path.join(self.target, '/var/lib/ubiquity/installed-packages')
            with open(p, 'w') as fp:
                for line in installed:
                    print >>fp, line

    def remove_oem_extras(self):
        '''Try to remove packages that were not part of the base install and
        are not needed by the final system.
        
        This is roughly the set of packages installed by ubiquity + packages we
        explicitly installed in oem-config (langpacks, for example) -
        everything else.'''

        manifest = '/var/lib/ubiquity/installed-packages'
        if not os.path.exists(manifest):
            return
        
        keep = set()
        with open(manifest) as manifest_file:
            for line in manifest_file:
                if line.strip() != '' and not line.startswith('#'):
                    keep.add(line.split()[0])
        # Lets not rip out the ground beneath our feet.
        keep.add('ubiquity')
        keep.add('oem-config')

        cache = Cache()
        remove = set([pkg for pkg in cache.keys() if cache[pkg].isInstalled])
        # Keep packages we explicitly installed.
        keep |= install_misc.query_recorded_installed()
        remove -= self.expand_dependencies_simple(cache, keep, remove)
        del cache
        
        install_misc.record_removed(remove)
        (regular, recursive) = install_misc.query_recorded_removed()
        self.do_remove(regular)
        self.do_remove(recursive, recursive=True)

    def copy_tree(self, source, target, uid, gid):
        # Mostly stolen from copy_all.
        directory_times = []
        s = '/'
        for p in target.split(os.sep)[1:]:
            s = os.path.join(s, p)
            if not os.path.exists(s):
                os.mkdir(s)
                os.lchown(s, uid, gid)
        for dirpath, dirnames, filenames in os.walk(source):
            sp = dirpath[len(source) + 1:]
            for name in dirnames + filenames:
                relpath = os.path.join(sp, name)
                sourcepath = os.path.join(source, relpath)
                targetpath = os.path.join(target, relpath)
                st = os.lstat(sourcepath)
                mode = stat.S_IMODE(st.st_mode)
                if stat.S_ISLNK(st.st_mode):
                    if os.path.lexists(targetpath):
                        os.unlink(targetpath)
                    linkto = os.readlink(sourcepath)
                    os.symlink(linkto, targetpath)
                elif stat.S_ISDIR(st.st_mode):
                    if not os.path.isdir(targetpath):
                        os.mkdir(targetpath, mode)
                elif stat.S_ISCHR(st.st_mode):
                    os.mknod(targetpath, stat.S_IFCHR | mode, st.st_rdev)
                elif stat.S_ISBLK(st.st_mode):
                    os.mknod(targetpath, stat.S_IFBLK | mode, st.st_rdev)
                elif stat.S_ISFIFO(st.st_mode):
                    os.mknod(targetpath, stat.S_IFIFO | mode)
                elif stat.S_ISSOCK(st.st_mode):
                    os.mknod(targetpath, stat.S_IFSOCK | mode)
                elif stat.S_ISREG(st.st_mode):
                    osextras.unlink_force(targetpath)
                    self.copy_file(sourcepath, targetpath, True)

                os.lchown(targetpath, uid, gid)
                if not stat.S_ISLNK(st.st_mode):
                    os.chmod(targetpath, mode)
                if stat.S_ISDIR(st.st_mode):
                    directory_times.append((targetpath, st.st_atime, st.st_mtime))
                # os.utime() sets timestamp of target, not link
                elif not stat.S_ISLNK(st.st_mode):
                    os.utime(targetpath, (st.st_atime, st.st_mtime))

        # Apply timestamps to all directories now that the items within them
        # have been copied.
        for dirtime in directory_times:
            (directory, atime, mtime) = dirtime
            try:
                os.utime(directory, (atime, mtime))
            except OSError:
                # I have no idea why I've been getting lots of bug reports
                # about this failing, but I really don't care. Ignore it.
                pass

    def copy_network_config(self):
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

        if 'SUDO_USER' in os.environ:
            casper_user = os.path.expanduser('~%s' % os.environ['SUDO_USER'])
        else:
            casper_user = os.path.expanduser('~')
        target_user = self.db.get('passwd/username')

        # GTK
        # FIXME evand 2009-12-11: We assume /home here, but determine it below.
        target_keyrings = os.path.join(self.target, 'home', target_user,
                                       '.gnome2/keyrings')

        # Sanity checks.  We don't want to do anything if a network
        # configuration already exists, which will be the case if the user
        # selected to install without formatting.
        if os.path.exists(target_keyrings):
            return
        config_source = 'xml:readwrite:$HOME/.gconf'
        subp = subprocess.Popen(['chroot', self.target, 'sudo', '-i', '-n',
            '-u', target_user, '--', 'gconftool-2', '--direct',
            '--config-source', config_source, '--dir-exists',
            '/system/networking'], close_fds=True)
        subp.communicate()
        if subp.returncode == 0:
            return

        from ubiquity import gconftool
        if gconftool.dump('/system/networking', os.path.join(self.target,
                          'tmp/live-network-config')):
            # Ick.
            subprocess.call(['log-output', '-t', 'ubiquity', 'chroot',
                self.target, 'sudo', '-i', '-n', '-u', target_user, '--',
                'gconftool-2', '--direct', '--config-source', config_source,
                '--load', '/tmp/live-network-config'], close_fds=True)
            os.remove('/target/tmp/live-network-config')
            source_keyrings = os.path.join(casper_user, '.gnome2/keyrings')
            if os.path.exists(source_keyrings):
                # We could just figure out what $HOME is and stat it as an
                # alternative.
                uid = subprocess.Popen(['chroot', self.target, 'sudo', '-u',
                    target_user, '--', 'id', '-u'],
                    stdout=subprocess.PIPE).communicate()[0].strip('\n')
                gid = subprocess.Popen(['chroot', self.target, 'sudo', '-u',
                    target_user, '--', 'id', '-g'],
                    stdout=subprocess.PIPE).communicate()[0].strip('\n')
                uid = int(uid)
                gid = int(gid)
                self.copy_tree(source_keyrings, target_keyrings, uid, gid)

        # KDE TODO

    def recache_apparmor(self):
        """Generate an apparmor cache in /etc/apparmor.d/cache to speed up boot
        time."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return
        if not os.path.exists(os.path.join(self.target, 'etc/init.d/apparmor')):
            syslog.syslog('Apparmor is not installed, so not generating cache.')
            return
        install_misc.chrex(self.target,'mount', '-t', 'proc', 'proc', '/proc')
        install_misc.chrex(self.target,'mount', '-t', 'sysfs', 'sysfs', '/sys')
        install_misc.chrex(self.target,'mount', '-t', 'securityfs',
                   'securityfs', '/sys/kernel/security')
        install_misc.chrex(self.target,'/etc/init.d/apparmor', 'recache')
        install_misc.chrex(self.target,'umount', '/proc')
        install_misc.chrex(self.target,'umount', '/sys/kernel/security')
        install_misc.chrex(self.target,'umount', '/sys')

    def copy_wallpaper_cache(self):
        """Copy wallpaper cache for libgnome desktop so that it's taken into
        account by ureadahead. Only install on system having g-s-d."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

        # we don't use copy_network_config casper user trick as it's not and not
        # ubuntu in install mode
        casper_user = 'mint'
        casper_user_home = os.path.expanduser('~%s' % casper_user)
        casper_user_wallpaper_cache_dir = os.path.join(casper_user_home,
                                                       '.cache', 'wallpaper')
        target_user = self.db.get('passwd/username')
        target_user_cache_dir = os.path.join(self.target, 'home',
                                                       target_user, '.cache')
        target_user_wallpaper_cache_dir = os.path.join(target_user_cache_dir,
                                                       'wallpaper')
        if not os.path.isdir(target_user_wallpaper_cache_dir) and \
               os.path.isfile('/usr/lib/gnome-settings-daemon/'
                              'gnome-update-wallpaper-cache'):
            # installer mode (else, g-s-d created it)
            if not os.path.isdir(casper_user_wallpaper_cache_dir):
                subprocess.call(['sudo', '-u', casper_user, '-i', 'DISPLAY=:0',
                                 '/usr/lib/gnome-settings-daemon/'
                                 'gnome-update-wallpaper-cache'])
            # copy to targeted user
            uid = subprocess.Popen(['chroot', self.target, 'sudo', '-u',
                target_user, '--', 'id', '-u'],
                stdout=subprocess.PIPE).communicate()[0].strip('\n')
            gid = subprocess.Popen(['chroot', self.target, 'sudo', '-u',
                target_user, '--', 'id', '-g'],
                stdout=subprocess.PIPE).communicate()[0].strip('\n')
            uid = int(uid)
            gid = int(gid)
            self.copy_tree(casper_user_wallpaper_cache_dir,
                           target_user_wallpaper_cache_dir, uid, gid)
            os.chmod(target_user_cache_dir, 0700)
            os.chmod(target_user_wallpaper_cache_dir, 0700)

    def cleanup(self):
        """Miscellaneous cleanup tasks."""

        misc.execute('umount', os.path.join(self.target, 'cdrom'))

        env = dict(os.environ)
        env['OVERRIDE_BASE_INSTALLABLE'] = '1'
        subprocess.call(['/usr/lib/ubiquity/apt-setup/finish-install'],
                        env=env)

        for apt_conf in ('00NoMountCDROM', '00IgnoreTimeConflict',
                         '00AllowUnauthenticated'):
            osextras.unlink_force(os.path.join(
                self.target, 'etc/apt/apt.conf.d', apt_conf))

        if self.source == '/var/lib/ubiquity/source':
            self.umount_source()

if __name__ == '__main__':
    if not os.path.exists('/var/lib/ubiquity'):
        os.makedirs('/var/lib/ubiquity')
    osextras.unlink_force('/var/lib/ubiquity/install.trace')

    install = Install()
    sys.excepthook = install.excepthook
    install.run()
    sys.exit(0)

# vim:ai:et:sts=4:tw=80:sw=4:
