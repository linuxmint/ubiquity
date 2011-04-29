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
import errno
import stat
import subprocess
import time
import syslog
import debconf
import warnings
warnings.filterwarnings("ignore", "apt API not stable yet", FutureWarning)
import apt_pkg
from apt.cache import Cache

sys.path.insert(0, '/usr/lib/ubiquity')

from ubiquity import misc
from ubiquity import install_misc
from ubiquity import osextras
from ubiquity.casper import get_casper


class Install(install_misc.InstallBase):

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
        self.db = debconf.Debconf()
        self.blacklist = {}

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            self.source = None
            self.target = '/'
            return

        assert os.path.ismount(self.target), \
            'Failed to mount the target: %s' % str(self.target)

        self.select_language_packs(save=True)
        self.select_ecryptfs()
        if self.db.get('ubiquity/install/generate-blacklist') == 'true':
            self.db.progress('START', 0, 100, 'ubiquity/install/title')
            self.db.progress('INFO', 'ubiquity/install/blacklist')
            self.generate_blacklist()

        apt_pkg.InitConfig()
        apt_pkg.Config.set("Dir", self.target)
        apt_pkg.Config.set("Dir::State::status",
                           os.path.join(self.target, 'var/lib/dpkg/status'))
        apt_pkg.Config.set("APT::GPGV::TrustedKeyring",
                           os.path.join(self.target, 'etc/apt/trusted.gpg'))
        apt_pkg.Config.set("Acquire::gpgv::Options::",
                           "--ignore-time-conflict")
        apt_pkg.Config.set("DPkg::Options::", "--root=%s" % self.target)
        # We don't want apt-listchanges or dpkg-preconfigure, so just clear
        # out the list of pre-installation hooks.
        apt_pkg.Config.clear("DPkg::Pre-Install-Pkgs")
        apt_pkg.InitSystem()

    def run(self):
        """Run the install stage: copy everything to the target system, then
        configure it as necessary."""

        self.start = 0
        self.end = 74
        self.prev_count = 0
        self.count = 1

        self.db.progress('START', self.start, self.end, 'ubiquity/install/title')
        self.db.progress('INFO', 'ubiquity/install/mounting_source')

        if self.source == '/var/lib/ubiquity/source':
            self.mount_source()

        if self.target != '/':
            self.next_region(size=74)
            # We don't later wait() on this pid by design.  There's no
            # sense waiting for updates to finish downloading when they can
            # quite easily finish downloading them once inside the new
            # Ubuntu system.
            # TODO can we incorporate the bytes copied / bytes total into
            # the main progress bar?
            # TODO log to /var/log/installer/debug
            # TODO make sure KeyboardInterrupt and SystemExit kills this
            # TODO the install will blow up spectacularly if this is still
            # holding the apt lock when other apt install tasks run, I
            # imagine.  Have those spin until the lock is released.
            if self.db.get('ubiquity/download_updates') == 'true':
                cmd = ['/usr/share/ubiquity/update-apt-cache']
                subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE)
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
                    # Exit code 3 signals to the frontend that we have handled
                    # this error.
                    sys.exit(3)
                elif e.errno == errno.ENOSPC:
                    error_template = 'ubiquity/install/copying_error/no_space'
                    self.db.subst(error_template, 'ERROR', str(e))
                    self.db.input('critical', error_template)
                    self.db.go()
                    sys.exit(3)
                else:
                    raise
        self.db.progress('INFO', 'ubiquity/install/waiting')

        if self.source == '/var/lib/ubiquity/source':
            self.umount_source()

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
                if (cache[pkg].is_installed and
                    cache[pkg].section.startswith('restricted/')):
                    difference.add(pkg)

        # Keep packages we explicitly installed.
        keep = install_misc.query_recorded_installed()
        arch, subarch = install_misc.archdetect()

        # Less than ideal.  Since we cannot know which bootloader we'll need
        # at file copy time, we should figure out why grub still fails when
        # apt-install-direct is present during configure_bootloader (code
        # removed).
        if arch in ('amd64', 'i386'):
            if subarch == 'efi':
                keep.add('grub-efi')
                keep.add('grub-efi-amd64')
            else:
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

        # Even adding ubiquity as a depends to oem-config-{gtk,kde} doesn't
        # appear to force ubiquity and libdebian-installer4 to copy all of
        # their files, so this does the trick.
        try:
            if self.db.get('oem-config/enable') == 'true':
                keep.add('ubiquity')
        except (debconf.DebconfError, IOError):
            pass

        difference -= install_misc.expand_dependencies_simple(cache, keep, difference)

        # Consider only packages that don't have a prerm, and which can
        # therefore have their files removed without any preliminary work.
        difference = set(filter(
            lambda x: not os.path.exists('/var/lib/dpkg/info/%s.prerm' % x),
            difference))

        confirmed_remove = set()
        for pkg in sorted(difference):
            if pkg in confirmed_remove:
                continue
            would_remove = install_misc.get_remove_list(cache, [pkg], recursive=True)
            if would_remove <= difference:
                confirmed_remove |= would_remove
                # Leave these marked for removal in the apt cache to speed
                # up further calculations.
            else:
                for removedpkg in would_remove:
                    cachedpkg = install_misc.get_cache_pkg(cache, removedpkg)
                    cachedpkg.mark_keep()
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
                    install_misc.copy_file(self.db, sourcepath, targetpath, md5_check)

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
            install_misc.copy_file(self.db, kernel, target_kernel, md5_check)
            os.lchown(target_kernel, 0, 0)
            os.chmod(target_kernel, 0644)
            st = os.lstat(kernel)
            os.utime(target_kernel, (st.st_atime, st.st_mtime))

        os.umask(old_umask)

        self.db.progress('SET', 100)
        self.db.progress('STOP')

    def mount_one_image(self, fsfile, mountpoint=None):
        if os.path.splitext(fsfile)[1] == '.cloop':
            blockdev_prefix = 'cloop'
        elif os.path.splitext(fsfile)[1] == '.squashfs':
            blockdev_prefix = 'loop'

        if blockdev_prefix == '':
            raise install_misc.InstallStepError("No source device found for %s" % fsfile)

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
            raise install_misc.InstallStepError("No loop device available for %s" % fsfile)

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
                raise install_misc.InstallStepError(
                    "Preseeded filesystem image %s not found" % fs_preseed)

                dev, mountpoint = self.mount_one_image(fsfile, self.source)
                self.devs.append(dev)
                self.mountpoints.append(mountpoint)
        else:
            # OK, so we need to mount multiple images and unionfs them
            # together.
            for fsfile in fs_preseed.split():
                if not os.path.isfile(fsfile):
                    raise install_misc.InstallStepError(
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

    # TODO need to somehow get this to plugininstall
    def umount_source(self):
        """umounting loop system from cloop or squashfs system."""

        devs = self.devs
        devs.reverse()
        mountpoints = self.mountpoints
        mountpoints.reverse()

        for mountpoint in mountpoints:
            if not misc.execute('umount', mountpoint):
                raise install_misc.InstallStepError("Failed to unmount %s" % mountpoint)
        for dev in devs:
            if (dev != '' and dev != 'unused' and
                not misc.execute('losetup', '-d', dev)):
                raise install_misc.InstallStepError(
                    "Failed to detach loopback device %s" % dev)

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

if __name__ == '__main__':
    if not os.path.exists('/var/lib/ubiquity'):
        os.makedirs('/var/lib/ubiquity')
    osextras.unlink_force('/var/lib/ubiquity/install.trace')

    install = Install()
    sys.excepthook = install_misc.excepthook
    install.run()
    sys.exit(0)

# vim:ai:et:sts=4:tw=80:sw=4:
