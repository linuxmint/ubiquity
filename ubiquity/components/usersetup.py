# -*- coding: UTF-8 -*-

# Copyright (C) 2005, 2006, 2007, 2008 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
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
import debconf

class UserSetup(FilteredCommand):
    def prepare(self):
        if self.frontend.get_hostname() == '':
            try:
                hostname = self.db.get('netcfg/get_hostname')
                domain = self.db.get('netcfg/get_domain')
                if hostname and domain:
                    hostname = '%s.%s' % (hostname, domain)
                if hostname != '':
                    self.frontend.set_hostname(hostname)
            except debconf.DebconfError:
                pass
        if self.frontend.get_fullname() == '':
            try:
                fullname = self.db.get('passwd/user-fullname')
                if fullname != '':
                    self.frontend.set_fullname(fullname)
            except debconf.DebconfError:
                pass
        if self.frontend.get_username() == '':
            try:
                username = self.db.get('passwd/username')
                if username != '':
                    self.frontend.set_username(username)
            except debconf.DebconfError:
                pass
        try:
            auto_login = self.db.get('passwd/auto-login')
            self.frontend.set_auto_login(auto_login == 'true')
        except debconf.DebconfError:
            pass
        try:
            encrypt_home = self.db.get('user-setup/encrypt-home')
            self.frontend.set_encrypt_home(encrypt_home == 'true')
        except debconf.DebconfError:
            pass

        # We intentionally don't listen to passwd/auto-login or
        # user-setup/encrypt-home because we don't want those alone to force
        # the page to be shown, if they're the only questions not preseeded.
        questions = ['^passwd/user-fullname$', '^passwd/username$',
                     '^passwd/user-password$', '^passwd/user-password-again$',
                     '^user-setup/password-weak$',
                     'ERROR']
        return (['/usr/lib/ubiquity/user-setup/user-setup-ask', '/target'],
                questions)

    def set(self, question, value):
        if question == 'passwd/username':
            if self.frontend.get_username() != '':
                self.frontend.set_username(value)

    def run(self, priority, question):
        if question.startswith('user-setup/password-weak'):
            # A dialog is a bit clunky, but workable for now. Perhaps it
            # would be better to display some text in the style of
            # password_error, and then let the user carry on anyway by
            # clicking next again?
            response = self.frontend.question_dialog(
                self.description(question),
                self.extended_description(question),
                ('ubiquity/text/choose_another_password',
                 'ubiquity/text/continue'))
            if response is None or response == 'ubiquity/text/continue':
                self.preseed(question, 'true')
            else:
                self.preseed(question, 'false')
                self.succeeded = False
                self.done = False
                self.frontend.select_password()
            return True

        return FilteredCommand.run(self, priority, question)

    def ok_handler(self):
        fullname = self.frontend.get_fullname()
        username = self.frontend.get_username()
        password = self.frontend.get_password()
        password_confirm = self.frontend.get_verified_password()
        auto_login = self.frontend.get_auto_login()
        encrypt_home = self.frontend.get_encrypt_home()

        self.preseed('passwd/user-fullname', fullname)
        self.preseed('passwd/username', username)
        # TODO: maybe encrypt these first
        self.preseed('passwd/user-password', password)
        self.preseed('passwd/user-password-again', password_confirm)
        if self.frontend.oem_config:
            self.preseed('passwd/user-uid', '29999')
        else:
            self.preseed('passwd/user-uid', '')
        self.preseed_bool('passwd/auto-login', auto_login)
        self.preseed_bool('user-setup/encrypt-home', encrypt_home)
        
        hostname = self.frontend.get_hostname()
        if hostname is not None and hostname != '':
            hd = hostname.split('.', 1)
            self.preseed('netcfg/get_hostname', hd[0])
            if len(hd) > 1:
                self.preseed('netcfg/get_domain', hd[1])
            else:
                self.preseed('netcfg/get_domain', '')

        FilteredCommand.ok_handler(self)

    def error(self, priority, question):
        if question.startswith('passwd/username-'):
            self.frontend.username_error(self.extended_description(question))
        elif question.startswith('user-setup/password-'):
            self.frontend.password_error(self.extended_description(question))
        else:
            self.frontend.error_dialog(self.description(question),
                                       self.extended_description(question))
        return FilteredCommand.error(self, priority, question)
