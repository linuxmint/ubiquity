# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2018 Canonical Ltd.
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


import json
import os
import stat
import syslog

from ubiquity.misc import raise_privileges

START_INSTALL_STAGE_TAG = 'start_install'


def get():
    """Return a singleton _Telemetry instance."""
    if _Telemetry._telemetry is None:
        _Telemetry._telemetry = _Telemetry()
    return _Telemetry._telemetry


class _Telemetry():

    _telemetry = None

    def __init__(self):
        self._metrics = {}
        self._stages_hist = {}
        self._start_time = self._get_current_uptime()
        self.add_stage('start')
        self._dest_path = '/target/var/log/installer/telemetry'
        try:
            with open('/cdrom/.disk/info') as f:
                self._metrics['Media'] = f.readline()
        except FileNotFoundError:
            self._metrics['Media'] = 'unknown'

    def _get_current_uptime(self):
        """Get current uptime info. None if we couldn't fetch it."""
        uptime = None
        try:
            with open('/proc/uptime') as f:
                uptime = float(f.read().split()[0])
        except (FileNotFoundError, OSError, ValueError) as e:
            syslog.syslog(syslog.LOG_ERR,
                          "Exception while fetching current uptime: " + str(e))
        return uptime

    def add_stage(self, stage_name):
        """Record installer stage with current time"""
        now = self._get_current_uptime()
        if self._start_time is None or now is None:
            return
        self._stages_hist[int(now - self._start_time)] = stage_name

    def set_installer_type(self, installer_type):
        """Record installer type"""
        self._metrics['Type'] = installer_type

    def set_is_oem(self, is_oem):
        """Record if OEM installation"""
        self._metrics['OEM'] = is_oem

    def set_partition_method(self, method):
        """Record anynomized partition method"""
        self._metrics['PartitionMethod'] = method

    def _db_get_bool(self, value):
        if value == 'true':
            return True
        return False

    @raise_privileges
    def done(self, db):
        """Close telemetry collection

        Set as installation done, add additional info and save to
        destination file"""
        self.add_stage('done')

        self._metrics['DownloadUpdates'] = self._db_get_bool(
            db.get('ubiquity/download_updates'))
        self._metrics['Language'] = db.get('localechooser/languagelist')
        self._metrics['Minimal'] = self._db_get_bool(
            db.get('ubiquity/minimal_install'))
        self._metrics['RestrictedAddons'] = self._db_get_bool(
            db.get('ubiquity/use_nonfree'))
        self._metrics['Stages'] = self._stages_hist

        # don't save oem user config for now. We may merge the 2 installation
        # records in the future.
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return

        target_dir = os.path.dirname(self._dest_path)
        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            with open(self._dest_path, 'w') as f:
                json.dump(self._metrics, f)
            os.chmod(self._dest_path,
                     stat.S_IRUSR | stat.S_IWUSR |
                     stat.S_IRGRP | stat.S_IROTH)
        except OSError as e:
            syslog.syslog(syslog.LOG_ERR,
                          "Exception while storing telemetry data: " + str(e))

# vim:ai:et:sts=4:tw=80:sw=4:
