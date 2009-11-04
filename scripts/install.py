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
from ubiquity import osextras
from ubiquity import plugin_manager
from ubiquity.casper import get_casper
from ubiquity.components import apt_setup, usersetup_apply, \
                                hw_detect, check_kernels, \
                                migrationassistant_apply

def debconf_disconnect():
    """Disconnect from debconf. This is only to be used as a subprocess
    preexec_fn helper."""
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    if 'DEBIAN_HAS_FRONTEND' in os.environ:
        del os.environ['DEBIAN_HAS_FRONTEND']
    if 'DEBCONF_USE_CDEBCONF' in os.environ:
        # Probably not a good idea to use this in /target too ...
        del os.environ['DEBCONF_USE_CDEBCONF']

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
        flags = fcntl.fcntl(self.statusfd.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(self.statusfd.fileno(), fcntl.F_SETFL,
                    flags & ~os.O_NONBLOCK)

    def startUpdate(self):
        self.db.progress('START', 0, 100, self.title)
        self.started = True

    def error(self, pkg, errormsg):
        if self.error_template is not None:
            self.db.subst(self.error_template, 'PACKAGE', pkg)
            self.db.subst(self.error_template, 'MESSAGE', errormsg)
            self.db.input('critical', self.error_template)
            self.db.go()

    def statusChange(self, pkg, percent, status):
        self.percent = percent
        self.status = status
        self.db.progress('SET', int(percent))
        self.db.subst(self.info, 'DESCRIPTION', status)
        self.db.progress('INFO', self.info)

    def updateInterface(self):
        # TODO cjwatson 2006-02-28: InstallProgress.updateInterface doesn't
        # give us a handy way to spot when percentages/statuses change and
        # aren't pmerror/pmconffile, so we have to reimplement it here.
        if self.statusfd is None:
            return False
        try:
            while not self.read.endswith("\n"):
                r = os.read(self.statusfd.fileno(),1)
                if not r:
                    return False
                self.read += r
        except OSError, (err,errstr):
            print errstr
        if self.read.endswith("\n"):
            s = self.read
            (status, pkg, percent, status_str) = s.split(":", 3)
            if status == "pmerror":
                self.error(pkg, status_str)
            elif status == "pmconffile":
                # we get a string like this:
                # 'current-conffile' 'new-conffile' useredited distedited
                match = re.compile("\s*\'(.*)\'\s*\'(.*)\'.*").match(status_str)
                if match:
                    self.conffile(match.group(1), match.group(2))
            else:
                self.statusChange(pkg, float(percent), status_str.strip())
            self.read = ""
        return True

    def run(self, pm):
        # Create a subprocess to deal with turning apt status messages into
        # debconf protocol messages.
        child_pid = self.fork()
        if child_pid == 0:
            # child
            os.close(self.writefd)
            try:
                while self.updateInterface():
                    pass
            except (KeyboardInterrupt, SystemExit):
                pass # we're going to exit anyway
            except:
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_WARNING, line)
            os._exit(0)

        self.statusfd.close()

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
            res = pm.DoInstall(self.writefd)
        finally:
            # Reap the status-to-debconf subprocess.
            os.close(self.writefd)
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

    def run(self):
        """Run the install stage: copy everything to the target system, then
        configure it as necessary."""

        # Give one extra progress point for each plugin, on the assumption that
        # they don't run long.
        start = 0
        end = 22 + len(self.plugins)
        if self.target != '/':
            end += 74
        count = 1

        self.db.progress('START', start, end, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/mounting_source')

        try:
            if self.source == '/var/lib/ubiquity/source':
                self.mount_source()

            if self.target != '/':
                self.db.progress('SET', count)
                self.db.progress('REGION', count, count+74)
                count += 74
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

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', 'ubiquity/install/network')
            self.configure_network()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', 'ubiquity/install/apt')
            self.configure_apt()

            self.configure_plugins(count)
            count += len(self.plugins)

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', 'ubiquity/install/user')
            self.configure_user()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.run_target_config_hooks()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+5)
            count += 5
            # Ignore failures from language pack installation.
            try:
                self.install_language_packs()
            except InstallStepError:
                pass
            except IOError:
                pass
            except SystemError:
                pass

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', 'ubiquity/install/migrationassistant')
            self.configure_ma()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.remove_unusable_kernels()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+4)
            count += 4
            self.db.progress('INFO', 'ubiquity/install/hardware')
            self.configure_hardware()

            # Tell apt-install to install packages directly from now on.
            apt_install_direct = open('/var/lib/ubiquity/apt-install-direct',
                                      'w')
            apt_install_direct.close()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', 'ubiquity/install/bootloader')
            self.configure_bootloader()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', 'ubiquity/install/installing')
            self.install_extras()

            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+4)
            count += 4
            self.db.progress('INFO', 'ubiquity/install/removing')
            self.remove_extras()

            self.remove_broken_cdrom()

            self.copy_dcd()
            self.db.progress('SET', count)
            self.db.progress('INFO', 'ubiquity/install/log_files')
            self.copy_logs()

            self.db.progress('SET', end)
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
        keep = self.query_recorded_installed()
        arch, subarch = self.archdetect()

        # Less than ideal.  Since we cannot know which bootloader we'll need
        # at file copy time, we should figure out why grub still fails when
        # apt-install-direct is present during configure_bootloader (code
        # removed).
        if arch in ('amd64', 'i386', 'lpia'):
            keep.add('grub')
            keep.add('grub-pc')
        elif (arch == 'armel' and
              subarch in ('dove', 'imx51', 'iop32x', 'ixp4xx', 'orion5x')):
            keep.add('flash-kernel')
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

        files = []
        total_size = 0

        self.db.progress('START', 0, 100, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/scanning')

        # Obviously doing os.walk() twice is inefficient, but I'd rather not
        # suck the list into ubiquity's memory, and I'm guessing that the
        # kernel's dentry cache will avoid most of the slowness anyway.
        walklen = 0
        for entry in os.walk(self.source):
            walklen += 1
        walkpos = 0
        walkprogress = 0

        for dirpath, dirnames, filenames in os.walk(self.source):
            walkpos += 1
            if int(float(walkpos) / walklen * 10) != walkprogress:
                walkprogress = int(float(walkpos) / walklen * 10)
                self.db.progress('SET', walkprogress)

            sourcepath = dirpath[len(self.source) + 1:]

            for name in dirnames + filenames:
                relpath = os.path.join(sourcepath, name)
                fqpath = os.path.join(dirpath, name)
                # /etc/fstab was legitimately created by partman, and
                # shouldn't be copied again.
                if relpath != "etc/fstab":
                    total_size += os.lstat(fqpath).st_size
                    files.append(relpath)

        self.db.progress('SET', 10)
        self.db.progress('INFO', 'ubiquity/install/copying')

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
        if self.db.get('ubiquity/install/md5_check') == 'false':
            md5_check = False
        else:
            md5_check = True
        
        old_umask = os.umask(0)
        for path in files:
            sourcepath = os.path.join(self.source, path)
            targetpath = os.path.join(self.target, path)
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
                if '/%s' % path in self.blacklist:
                    syslog.syslog('Not copying %s' % path)
                    continue
                if os.path.exists(targetpath):
                    os.unlink(targetpath)
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

        # Try some possible locations for the kernel we used to boot. This
        # lets us save a couple of megabytes of CD space.
        bootdir = os.path.join(self.target, 'boot')
        kernel = self.find_cd_kernel()
        if kernel:
            prefix = os.path.basename(kernel).split('-', 1)[0]
            release = os.uname()[2]
            target_kernel = os.path.join(bootdir, '%s-%s' % (prefix, release))
            if os.path.exists(target_kernel):
                os.unlink(target_kernel)
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
                shutil.copy(media_info,
                    os.path.join(self.target, 'var/log/installer/media-info'))
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


    def chroot_setup(self, x11=False):
        """Set up /target for safe package management operations."""
        if self.target == '/':
            return

        policy_rc_d = os.path.join(self.target, 'usr/sbin/policy-rc.d')
        f = open(policy_rc_d, 'w')
        print >>f, """\
#!/bin/sh
exit 101"""
        f.close()
        os.chmod(policy_rc_d, 0755)

        start_stop_daemon = os.path.join(self.target, 'sbin/start-stop-daemon')
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

        initctl = os.path.join(self.target, 'sbin/initctl')
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

        if not os.path.exists(os.path.join(self.target, 'proc/cmdline')):
            self.chrex('mount', '-t', 'proc', 'proc', '/proc')
        if not os.path.exists(os.path.join(self.target, 'sys/devices')):
            self.chrex('mount', '-t', 'sysfs', 'sysfs', '/sys')
        misc.execute('mount', '--bind', '/dev', os.path.join(self.target, 'dev'))

        if x11 and 'DISPLAY' in os.environ:
            if 'SUDO_USER' in os.environ:
                xauthority = os.path.expanduser('~%s/.Xauthority' %
                                                os.environ['SUDO_USER'])
            else:
                xauthority = os.path.expanduser('~/.Xauthority')
            if os.path.exists(xauthority):
                shutil.copy(xauthority,
                            os.path.join(self.target, 'root/.Xauthority'))

            if not os.path.isdir(os.path.join(self.target, 'tmp/.X11-unix')):
                os.mkdir(os.path.join(self.target, 'tmp/.X11-unix'))
            misc.execute('mount', '--bind', '/tmp/.X11-unix',
                         os.path.join(self.target, 'tmp/.X11-unix'))

    def chroot_cleanup(self, x11=False):
        """Undo the work done by chroot_setup."""
        if self.target == '/':
            return

        if x11 and 'DISPLAY' in os.environ:
            misc.execute('umount', os.path.join(self.target, 'tmp/.X11-unix'))
            try:
                os.rmdir(os.path.join(self.target, 'tmp/.X11-unix'))
            except OSError:
                pass
            try:
                os.unlink(os.path.join(self.target, 'root/.Xauthority'))
            except OSError:
                pass

        self.chrex('umount', '/dev')
        self.chrex('umount', '/sys')
        self.chrex('umount', '/proc')

        initctl = os.path.join(self.target, 'sbin/initctl')
        if os.path.exists('%s.REAL' % initctl):
            os.rename('%s.REAL' % initctl, initctl)

        start_stop_daemon = os.path.join(self.target, 'sbin/start-stop-daemon')
        if os.path.exists('%s.REAL' % start_stop_daemon):
            os.rename('%s.REAL' % start_stop_daemon, start_stop_daemon)
        else:
            os.unlink(start_stop_daemon)

        policy_rc_d = os.path.join(self.target, 'usr/sbin/policy-rc.d')
        os.unlink(policy_rc_d)


    def run_target_config_hooks(self):
        """Run hook scripts from /usr/lib/ubiquity/target-config. This allows
        casper to hook into us and repeat bits of its configuration in the
        target system."""

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


    def configure_plugins(self, count):
        """Apply plugin settings to installed system."""
        class Progress:
            def __init__(self, db):
                self._db = db
            def info(self, title):
                self._db.progress('INFO', title)

        for plugin in self.plugins:
            self.db.progress('SET', count)
            self.db.progress('REGION', count, count+1)
            count += 1
            self.db.progress('INFO', ' ') # clear info in case plugin doesn't provide one
            inst = plugin.Install(None, db=self.db)
            ret = inst.install(self.target, Progress(self.db))
            if ret:
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


    def record_installed(self, pkgs):
        """Record which packages we've explicitly installed so that we don't
        try to remove them later."""

        record_file = "/var/lib/ubiquity/apt-installed"
        if not os.path.exists(os.path.dirname(record_file)):
            os.makedirs(os.path.dirname(record_file))
        record = open(record_file, "a")

        for pkg in pkgs:
            print >>record, pkg

        record.close()


    def query_recorded_installed(self):
        apt_installed = set()
        if os.path.exists("/var/lib/ubiquity/apt-installed"):
            record_file = open("/var/lib/ubiquity/apt-installed")
            for line in record_file:
                apt_installed.add(line.strip())
            record_file.close()
        return apt_installed


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


    def select_language_packs(self):
        try:
            keep_packages = self.db.get('ubiquity/keep-installed')
            keep_packages = keep_packages.replace(',', '').split()
            syslog.syslog('keeping packages due to preseeding: %s' %
                          ' '.join(keep_packages))
            self.record_installed(keep_packages)
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
                    langpack_set.add(locale.split('_')[0])
                langpacks = sorted(langpack_set)
            except debconf.DebconfError:
                pass
        if not langpacks:
            langpack_db = self.db.get('debian-installer/locale')
            langpacks = [langpack_db.split('_')[0]]
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

        del cache

        self.record_installed(to_install)
        self.langpacks = to_install

    def install_language_packs(self):
        if not self.langpacks:
            return

        self.do_install(self.langpacks)

        if len(self.languages) == 1 and self.languages[0] in ('C', 'en'):
            return # always complete enough

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
                    self.record_installed(['ecryptfs-utils'])
                    break


    def configure_user(self):
        """create the user selected along the installation process
        into the installed system. Default user from live system is
        deleted and skel for this new user is copied to $HOME."""

        dbfilter = usersetup_apply.UserSetupApply(None)
        ret = dbfilter.run_command(auto_process=True)
        if ret != 0:
            raise InstallStepError("UserSetupApply failed with code %d" % ret)

    def configure_ma(self):
        """import documents, settings, and users from previous operating
        systems."""

        if 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
            dbfilter = migrationassistant_apply.MigrationAssistantApply(None)
            ret = dbfilter.run_command(auto_process=True)
            if ret != 0:
                raise InstallStepError("MigrationAssistantApply failed with code %d" % ret)


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

        self.chroot_setup()
        try:
            dbfilter = hw_detect.HwDetect(None, self.db)
            ret = dbfilter.run_command(auto_process=True)
            if ret != 0:
                raise InstallStepError("HwDetect failed with code %d" % ret)
        finally:
            self.chroot_cleanup()

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

        try:
            os.unlink(os.path.join(self.target, 'etc/usplash.conf'))
        except OSError:
            pass
        try:
            modes = self.db.get('xserver-xorg/config/display/modes')
            self.set_debconf('xserver-xorg/config/display/modes', modes)
        except debconf.DebconfError:
            pass

        try:
            os.unlink(os.path.join(self.target, 'etc/popularity-contest.conf'))
        except OSError:
            pass
        try:
            participate = self.db.get('popularity-contest/participate')
            self.set_debconf('popularity-contest/participate', participate)
        except debconf.DebconfError:
            pass

        try:
            os.unlink(os.path.join(self.target, 'etc/papersize'))
        except OSError:
            pass
        subprocess.call(['log-output', '-t', 'ubiquity', 'chroot', self.target,
                         'ucf', '--purge', '/etc/papersize'],
                        preexec_fn=debconf_disconnect, close_fds=True)
        try:
            self.set_debconf('libpaper/defaultpaper', '')
        except debconf.DebconfError:
            pass

        try:
            os.unlink(os.path.join(self.target,
                      'etc/ssl/certs/ssl-cert-snakeoil.pem'))
        except OSError:
            pass
        try:
            os.unlink(os.path.join(self.target,
                      'etc/ssl/private/ssl-cert-snakeoil.key'))
        except OSError:
            pass

        self.chroot_setup(x11=True)
        self.chrex('dpkg-divert', '--package', 'ubiquity', '--rename',
                   '--quiet', '--add', '/usr/sbin/update-initramfs')
        try:
            os.symlink('/bin/true', os.path.join(self.target,
                                                 'usr/sbin/update-initramfs'))
        except OSError:
            pass

        packages = ['linux-image-' + self.kernel_version,
                    'linux-restricted-modules-' + self.kernel_version,
                    'usplash',
                    'splashy',
                    'popularity-contest',
                    'libpaper1',
                    'ssl-cert']

        try:
            for package in packages:
                self.reconfigure(package)
        finally:
            try:
                os.unlink(os.path.join(self.target,
                          'usr/sbin/update-initramfs'))
            except OSError:
                pass
            self.chrex('dpkg-divert', '--package', 'ubiquity', '--rename',
                       '--quiet', '--remove', '/usr/sbin/update-initramfs')
            self.chrex('update-initramfs', '-c', '-k', self.kernel_version)
            self.chroot_cleanup(x11=True)

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


    def get_all_interfaces(self):
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
            hostname = 'ubuntu'

        fp = open(os.path.join(self.target, 'etc/hostname'), 'w')
        print >>fp, hostname
        fp.close()

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
            interfaces = self.get_all_interfaces()
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
                with_arp = False

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
        install_bootloader = self.db.get('ubiquity/install_bootloader')
        if install_bootloader == "true":
            misc.execute('mount', '--bind', '/proc', self.target + '/proc')
            misc.execute('mount', '--bind', '/sys', self.target + '/sys')
            misc.execute('mount', '--bind', '/dev', self.target + '/dev')

            arch, subarch = self.archdetect()

            try:
                if arch in ('amd64', 'i386', 'lpia'):
                    from ubiquity.components import grubinstaller
                    dbfilter = grubinstaller.GrubInstaller(None)
                    ret = dbfilter.run_command(auto_process=True)
                    if ret != 0:
                        raise InstallStepError(
                            "GrubInstaller failed with code %d" % ret)
                elif (arch == 'armel' and
                      subarch in ('dove', 'imx51', 'iop32x', 'ixp4xx', 'orion5x')):
                    from ubiquity.components import flash_kernel
                    dbfilter = flash_kernel.FlashKernel(None)
                    ret = dbfilter.run_command(auto_process=True)
                    if ret != 0:
                        raise InstallStepError(
                            "FlashKernel failed with code %d" % ret)
                elif arch == 'powerpc' and subarch == 'ps3':
                    from ubiquity.components import kbootinstaller
                    dbfilter = kbootinstaller.KbootInstaller(None)
                    ret = dbfilter.run_command(auto_process=True)
                    if ret != 0:
                        raise InstallStepError(
                            "KbootInstaller failed with code %d" % ret)
                elif arch == 'powerpc':
                    from ubiquity.components import yabootinstaller
                    dbfilter = yabootinstaller.YabootInstaller(None)
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

    def do_install(self, to_install):
        if self.langpacks:
            self.db.progress('START', 0, 10, 'ubiquity/langpacks/title')
        else:
            self.db.progress('START', 0, 10, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/find_installables')

        self.db.progress('REGION', 0, 1)
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
            return

        for pkg in to_install:
            self.mark_install(cache, pkg)

        self.db.progress('SET', 1)
        self.db.progress('REGION', 1, 10)
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
        self.chroot_setup()
        commit_error = None
        try:
            try:
                if not cache.commit(fetchprogress, installprogress):
                    fetchprogress.stop()
                    installprogress.finishUpdate()
                    self.db.progress('STOP')
                    return
            except IOError, e:
                for line in str(e).split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                fetchprogress.stop()
                installprogress.finishUpdate()
                self.db.progress('STOP')
                return
            except SystemError, e:
                for line in str(e).split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                commit_error = str(e)
        finally:
            self.chroot_cleanup()
        self.db.progress('SET', 10)

        cache.open(None)
        if commit_error or cache._depcache.BrokenCount > 0:
            if commit_error is None:
                commit_error = ''
            brokenpkgs = self.broken_packages(cache)
            syslog.syslog('broken packages after installation: '
                          '%s' % ', '.join(brokenpkgs))
            self.db.subst('ubiquity/install/broken_install', 'ERROR',
                          commit_error)
            self.db.subst('ubiquity/install/broken_install', 'PACKAGES',
                          ', '.join(brokenpkgs))
            self.db.input('critical', 'ubiquity/install/broken_install')
            self.db.go()

        self.db.progress('STOP')


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
            return

        self.get_remove_list(cache, to_remove, recursive)

        self.db.progress('SET', 1)
        self.db.progress('REGION', 1, 5)
        fetchprogress = DebconfFetchProgress(
            self.db, 'ubiquity/install/title', None,
            'ubiquity/install/fetch_remove')
        installprogress = DebconfInstallProgress(
            self.db, 'ubiquity/install/title', 'ubiquity/install/apt_info',
            'ubiquity/install/apt_error_remove')
        self.chroot_setup()
        commit_error = None
        try:
            try:
                if not cache.commit(fetchprogress, installprogress):
                    fetchprogress.stop()
                    installprogress.finishUpdate()
                    self.db.progress('STOP')
                    return
            except SystemError, e:
                for line in str(e).split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                commit_error = str(e)
        finally:
            self.chroot_cleanup()
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
        dbfilter = check_kernels.CheckKernels(None)
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
        self.db.progress('REGION', 1, 2)
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
        self.db.progress('REGION', 2, 5)
        try:
            if remove_kernels:
                self.do_remove(remove_kernels, recursive=True)
        except:
            self.db.progress('STOP')
            raise
        self.db.progress('SET', 5)
        self.db.progress('STOP')


    def install_extras(self):
        """Try to install additional packages requested by installer
        components."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

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

        self.do_install(self.query_recorded_installed())

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
                        'usr/share/applications/kde/oem-config-prepare-kde.desktop'):
                        if os.path.exists(os.path.join(self.target,
                                                       desktop_file)):
                            desktop_base = os.path.basename(desktop_file)
                            self.chrex('install', '-d',
                                       '-o', 'oem', '-g', 'oem',
                                       '/home/oem/Desktop')
                            self.chrex('install', '-o', 'oem', '-g', 'oem',
                                       '/%s' % desktop_file,
                                       '/home/oem/Desktop/%s' % desktop_base)
                            break

		# Carry the locale setting over to the installed system.
		# This mimics the behavior in 01oem-config-udeb.
                di_locale = self.db.get('debian-installer/locale')
                if di_locale:
                    self.set_debconf('debian-installer/locale', di_locale)
        except debconf.DebconfError:
            pass


    def remove_extras(self):
        """Try to remove packages that are needed on the live CD but not on
        the installed system."""

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

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
        keep = self.query_recorded_installed()

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

        # Don't worry about failures removing packages; it will be easier
        # for the user to sort them out with a graphical package manager (or
        # whatever) after installation than it will be to try to deal with
        # them automatically here.
        self.do_remove(difference)

    def remove_broken_cdrom(self):
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return
        fstab = os.path.join(self.target, 'etc/fstab')
        ret = []
        try:
            fp = open(fstab)
            for line in fp:
                l = line.split()
                if len(l) > 2:
                    if l[1].startswith('/cdrom') or l[1].startswith('/media/cdrom'):
                        try:
                            fstype = subprocess.Popen(
                                ['block-attr', '--type', l[0]],
                                stdout=subprocess.PIPE).communicate()[0].rstrip('\n')
                            if fstype != 'iso9660' and fstype != 'udf':
                                continue
                        except OSError:
                            pass
                ret.append(line)
            fp.close()
            fp = open(fstab, 'w')
            fp.writelines(ret)
        except Exception, e:
            syslog.syslog(syslog.LOG_ERR, 'Exception during installation:')
            syslog.syslog(syslog.LOG_ERR,
                'Unable to process /etc/fstab: ' + str(e))
        finally:
            if fp:
                fp.close()
            
    def cleanup(self):
        """Miscellaneous cleanup tasks."""

        misc.execute('umount', os.path.join(self.target, 'cdrom'))

        env = dict(os.environ)
        env['OVERRIDE_BASE_INSTALLABLE'] = '1'
        subprocess.call(['/usr/lib/ubiquity/apt-setup/finish-install'],
                        env=env)

        for apt_conf in ('00NoMountCDROM', '00IgnoreTimeConflict',
                         '00AllowUnauthenticated'):
            try:
                os.unlink(os.path.join(
                    self.target, 'etc/apt/apt.conf.d', apt_conf))
            except:
                pass

        if self.source == '/var/lib/ubiquity/source':
            self.umount_source()


    def chrex(self, *args):
        """executes commands on chroot system (provided by *args)."""
        return misc.execute('chroot', self.target, *args)


    def copy_debconf(self, package):
        """setting debconf database into installed system."""

        # TODO cjwatson 2006-02-25: unusable here now because we have a
        # running debconf frontend that's locked the database; fortunately
        # this isn't critical. We still need to think about how to handle
        # preseeding in general, though.
        targetdb = os.path.join(self.target, 'var/cache/debconf/config.dat')

        misc.execute('debconf-copydb', 'configdb', 'targetdb', '-p',
                     '^%s/' % package, '--config=Name:targetdb',
                     '--config=Driver:File','--config=Filename:' + targetdb)


    def set_debconf(self, question, value):
        try:
            if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
                dccomm = None
                dc = self.db
            else:
                dccomm = subprocess.Popen(['log-output', '-t', 'ubiquity',
                                           '--pass-stdout',
                                           'chroot', self.target,
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


    def reconfigure_preexec(self):
        debconf_disconnect()
        os.environ['XAUTHORITY'] = '/root/.Xauthority'

    def reconfigure(self, package):
        """executes a dpkg-reconfigure into installed system to each
        package which provided by args."""
        subprocess.call(['log-output', '-t', 'ubiquity', 'chroot', self.target,
                         'dpkg-reconfigure', '-fnoninteractive', package],
                        preexec_fn=self.reconfigure_preexec, close_fds=True)


if __name__ == '__main__':
    if not os.path.exists('/var/lib/ubiquity'):
        os.makedirs('/var/lib/ubiquity')
    if os.path.exists('/var/lib/ubiquity/install.trace'):
        os.unlink('/var/lib/ubiquity/install.trace')

    install = Install()
    sys.excepthook = install.excepthook
    install.run()
    sys.exit(0)

# vim:ai:et:sts=4:tw=80:sw=4:
