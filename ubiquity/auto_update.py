# Copyright (C) 2006, 2009 Canonical Ltd.
# Written by Michael Vogt <michael.vogt@ubuntu.com> and
# Colin Watson <cjwatson@ubuntu.com>.
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

# Update the installer from the network.

from __future__ import print_function

import os
import sys
import syslog

import apt
import apt_pkg

from ubiquity import misc


MAGIC_MARKER = "/var/run/ubiquity.updated"
# Make sure that ubiquity is last, otherwise apt may try to install another
# frontend.
UBIQUITY_PKGS = ["ubiquity-casper",
                 "ubiquity-frontend-debconf",
                 "ubiquity-frontend-gtk",
                 "ubiquity-frontend-kde",
                 "ubiquity-ubuntu-artwork",
                 "ubiquity"]


class CacheProgressDebconfProgressAdapter(apt.progress.base.OpProgress):
    def __init__(self, frontend):
        self.frontend = frontend
        self.frontend.debconf_progress_start(
            0, 100, self.frontend.get_string('reading_package_information'))

    def update(self, percent=None):
        super().update(percent)
        self.frontend.debconf_progress_set(self.percent)
        self.frontend.refresh()

    def really_done(self):
        # Unfortunately the process of opening a Cache calls done() twice,
        # so we have to take care of this manually.
        self.frontend.debconf_progress_stop()


class AcquireProgressDebconfProgressAdapter(apt.progress.base.AcquireProgress):
    def __init__(self, frontend):
        apt.progress.base.AcquireProgress.__init__(self)
        self.frontend = frontend

    def pulse(self, owner):
        apt.progress.base.AcquireProgress.pulse(self, owner)
        if self.current_cps > 0:
            info = self.frontend.get_string('apt_progress_cps')
            current_cps = apt_pkg.size_to_str(self.current_cps)
            if isinstance(current_cps, bytes):
                current_cps = current_cps.decode()
            info = info.replace('${SPEED}', current_cps)
        else:
            info = self.frontend.get_string('apt_progress')
        info = info.replace('${INDEX}', str(self.current_items))
        info = info.replace('${TOTAL}', str(self.total_items))
        self.frontend.debconf_progress_info(info)
        self.frontend.debconf_progress_set(
            ((self.current_bytes + self.current_items) * 100.0) /
            float(self.total_bytes + self.total_items))
        self.frontend.refresh()
        return True

    def stop(self):
        self.frontend.debconf_progress_stop()

    def start(self):
        self.frontend.debconf_progress_start(
            0, 100, self.frontend.get_string('updating_package_information'))


class InstallProgressDebconfProgressAdapter(apt.progress.base.InstallProgress):
    def __init__(self, frontend):
        apt.progress.base.InstallProgress.__init__(self)
        self.frontend = frontend

    def status_change(self, unused_pkg, percent, unused_status):
        self.frontend.debconf_progress_set(percent)

    def start_update(self):
        self.frontend.debconf_progress_start(
            0, 100, self.frontend.get_string('installing_update'))

    def finish_update(self):
        self.frontend.debconf_progress_stop()

    def update_interface(self):
        apt.progress.base.InstallProgress.update_interface(self)
        self.frontend.refresh()


@misc.raise_privileges
def update(frontend):
    frontend.debconf_progress_start(
        0, 3, frontend.get_string('checking_for_installer_updates'))
    # check if we have updates
    cache_progress = CacheProgressDebconfProgressAdapter(frontend)
    cache = apt.Cache(cache_progress)
    cache_progress.really_done()

    acquire_progress = AcquireProgressDebconfProgressAdapter(frontend)
    try:
        cache.update(acquire_progress)
        cache_progress = CacheProgressDebconfProgressAdapter(frontend)
        cache = apt.Cache(cache_progress)
        cache_progress.really_done()
        updates = [pkg for pkg in UBIQUITY_PKGS
                   if pkg in cache and cache[pkg].is_upgradable]
    except IOError as e:
        print("ERROR: cache.update() returned: '%s'" % e)
        updates = []

    if not updates:
        frontend.debconf_progress_stop()
        return False

    # We have something to upgrade.  Shut down debconf-communicator for
    # the duration, otherwise we'll have locking problems.
    if frontend.dbfilter is not None and frontend.dbfilter.db is not None:
        frontend.stop_debconf()
        frontend.dbfilter.db = None
        stopped_debconf = True
    else:
        stopped_debconf = False
    try:
        # install the updates
        os.environ['DPKG_UNTRANSLATED_MESSAGES'] = '1'
        fixer = apt.ProblemResolver(cache)
        for pkg in updates:
            cache[pkg].mark_install(auto_fix=False)
            fixer.clear(cache[pkg])
            fixer.protect(cache[pkg])
        fixer.resolve()
        try:
            # dpkg will talk to stdout. We'd rather have this in the debug
            # log file.
            old_stdout = os.dup(1)
            os.dup2(2, 1)
            cache.commit(AcquireProgressDebconfProgressAdapter(frontend),
                         InstallProgressDebconfProgressAdapter(frontend))
        except (SystemError, IOError) as e:
            syslog.syslog(syslog.LOG_ERR,
                          "Error installing the update: '%s'" % e)
            title = frontend.get_string('error_updating_installer')
            if frontend.locale is None:
                extended_locale = 'extended:c'
            else:
                extended_locale = 'extended:%s' % frontend.locale
            msg = frontend.get_string('error_updating_installer',
                                      extended_locale)
            msg = msg.replace('${ERROR}', str(e))
            frontend.error_dialog(title, msg)
            frontend.debconf_progress_stop()
            return True
        finally:
            os.dup2(old_stdout, 1)
            os.close(old_stdout)

        # all went well, write marker and restart self
        # FIXME: we probably want some sort of in-between-restart-splash
        #        or at least a dialog here
        with open(MAGIC_MARKER, "w") as magic_marker:
            magic_marker.write("1")
        os.execv(sys.argv[0], sys.argv)
        return False
    finally:
        if stopped_debconf:
            frontend.start_debconf()
            frontend.dbfilter.db = frontend.db


def already_updated():
    return os.path.exists(MAGIC_MARKER)
