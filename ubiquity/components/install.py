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

from ubiquity.filteredcommand import FilteredCommand


class Install(FilteredCommand):
    def prepare(self, unfiltered=False):
        reboot = self.db.get('ubiquity/reboot')
        if reboot == 'true':
            self.frontend.set_reboot(True)
        else:
            self.frontend.set_reboot(False)

        shutdown = self.db.get('ubiquity/poweroff')
        if shutdown == 'true':
            self.frontend.set_shutdown(True)
        else:
            self.frontend.set_shutdown(False)

        if self.frontend.oem_config:
            self.preseed('oem-config/enable', 'true')

        questions = ['^.*/apt-install-failed$',
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
        self.frontend.error_dialog(self.description(question),
                                   self.extended_description(question), True)
        return FilteredCommand.error(self, priority, question)

    def run(self, priority, question):
        if question == 'ubiquity/install/copying_error/md5':
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

        return FilteredCommand.run(self, priority, question)
