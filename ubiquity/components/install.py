# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006, 2007, 2008 Canonical Ltd.
# Author(s):
#   Colin Watson <cjwatson@ubuntu.com>.
#   Mario Limonciello <superm1@ubuntu.com>
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

import os

from ubiquity.filteredcommand import FilteredCommand
from ubiquity import misc

class Install(FilteredCommand):
    def prepare(self, unfiltered=False):
        automatic_mode = 'UBIQUITY_AUTOMATIC' in os.environ

        if os.access('/usr/share/grub-installer/grub-installer', os.X_OK):
            bootdevice = self.db.get('grub-installer/bootdev')
            with_other_os = self.db.get('grub-installer/with_other_os')
            only_debian = self.db.get('grub-installer/only_debian')

            # If we're in automatic mode and there's already preseeded data, we
            # want to use it, rather than blindly writing over it.
            if not (automatic_mode and bootdevice != ''):
                bootdev = self.frontend.get_summary_device()
                if bootdev is None or bootdev == '':
                    bootdev = misc.grub_default()
                self.preseed('grub-installer/bootdev', bootdev)
            if not (automatic_mode and with_other_os != ''):
                self.preseed('grub-installer/with_other_os', 'false')
            if not (automatic_mode and only_debian != ''):
                self.preseed('grub-installer/only_debian', 'false')

        install_bootloader_seen = self.db.fget('ubiquity/install_bootloader',
                                               'seen')
        if not (automatic_mode and install_bootloader_seen):
            if self.frontend.oem_user_config:
                self.preseed_bool('ubiquity/install_bootloader', False)
            elif self.frontend.get_grub() is not None:
                self.preseed_bool('ubiquity/install_bootloader', self.frontend.get_grub())
            else:
                self.preseed_bool('ubiquity/install_bootloader', True)

        popcon = self.frontend.get_popcon()
        if popcon is not None:
            if popcon:
                self.preseed('popularity-contest/participate', 'true')
            else:
                self.preseed('popularity-contest/participate', 'false')

        http_proxy = self.frontend.get_proxy()
        if http_proxy:
            self.preseed('mirror/http/proxy', http_proxy)

        reboot = self.db.get('ubiquity/reboot')
        if reboot == 'true':
            self.frontend.set_reboot(True)
        else:
            self.frontend.set_reboot(False)

        if self.frontend.oem_config:
            self.preseed('oem-config/enable', 'true')

        # for clock-setup
        self.preseed('netcfg/dhcp_ntp_servers', '', seen=False)

        questions = ['^.*/apt-install-failed$',
                     'migration-assistant/failed-unmount',
                     'ubiquity/install/copying_error/md5',
                     'ubiquity/install/new-bootdev',
                     'CAPB',
                     'ERROR',
                     'PROGRESS']
        return (['/usr/share/ubiquity/install.py'], questions)

    def capb(self, capabilities):
        self.frontend.debconf_progress_cancellable(
            'progresscancel' in capabilities)

    def error(self, priority, question):
        if question == 'hw-detect/modprobe_error':
            # don't need to display this, and it's non-fatal
            return True
        elif question == 'apt-setup/security-updates-failed':
            fatal = False
        else:
            fatal = True
        self.frontend.error_dialog(self.description(question),
                                   self.extended_description(question), fatal)
        if fatal:
            return FilteredCommand.error(self, priority, question)
        else:
            return True

    def run(self, priority, question):
        if question.endswith('/apt-install-failed'):
            return self.error(priority, question)

        elif question == 'migration-assistant/failed-unmount':
            response = self.frontend.question_dialog(
                self.description(question),
                self.extended_description(question),
                ('ubiquity/text/go_back', 'ubiquity/text/continue'))
            if response is None or response == 'ubiquity/text/continue':
                self.preseed(question, 'true')
            else:
                self.preseed(question, 'false')
            return True
        elif question == 'ubiquity/install/copying_error/md5':
            response = self.frontend.question_dialog(
                self.description(question),
                # TODO evand 2008-02-14: i18n.
                self.extended_description(question),
                ('Abort', 'Retry', 'Skip'),
                use_templates=False)
            if response is None or response == 'Abort':
                self.preseed(question, 'abort')
            elif response == 'Retry':
                self.preseed(question, 'retry')
            elif response == 'Skip':
                self.preseed(question, 'skip')
            return True
        elif question == 'ubiquity/install/new-bootdev':
            current_device = self.db.get(question)
            response = self.frontend.bootloader_dialog(current_device)
            self.preseed(question, response)
            return True

        return FilteredCommand.run(self, priority, question)
