# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006 Evan Dandrea <evand@ubuntu.com>.
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

import syslog
import sys
import os
import debconf

from ubiquity.plugin import *
from ubiquity.filteredcommand import FilteredCommand
from ubiquity.misc import *

NAME = 'migrationassistant'

class PageGtk(PluginUI):
    plugin_optional_widgets = 'stepMigrationAssistant'

class PageNoninteractive(PluginUI):
    pass

class Page(FilteredCommand):
    def prepare(self):
        self.got_a_question = False
        questions = ['^migration-assistant/partitions',
                     '^migration-assistant/.*/users$',
                     '^migration-assistant/.*/items$',
                     '^migration-assistant/.*/user$',
                     '^migration-assistant/.*/password$',
                     '^migration-assistant/failed-unmount',
                     '^ubiquity/run-ma-again',
                     'ERROR']
        return (['/usr/share/ubiquity/migration-assistant'], questions)


    def run(self, priority, question):
        if question.endswith('items'):
            self.got_a_question = True
        if question == 'migration-assistant/failed-unmount':
            response = self.frontend.question_dialog(
                self.description(question),
                self.extended_description(question),
                ('ubiquity/text/go_back', 'ubiquity/text/continue'))
            if response is None or response == 'ubiquity/text/continue':
                self.preseed(question, 'true')
            else:
                self.preseed(question, 'false')
            return True

        # We cannot currently import from partitions that are scheduled for
        # deletion, so we filter them out of the list.
        if question == 'migration-assistant/partitions':
            self.filter_parts()

        elif question == 'ubiquity/run-ma-again':
            self.db.set('ubiquity/run-ma-again', 'false')
            self.set_choices()
            # If we didn't ask any questions, they're all preseeded and we don't
            # need to show the page, so we'll continue along.  If we got at
            # least one question, show the page.
            if not self.got_a_question:
                return self.succeeded
            else:
                return FilteredCommand.run(self, priority, question)

        elif question.endswith('user'):
            username = self.db.get('passwd/username')
            self.preseed(question, username)
        elif question.endswith('password'):
            # Just in case for now.  It should never get here as there's a check
            # in ma-ask that skips asking the user details if the username is
            # already preseeded in passwd.
            password = self.db.get('passwd/user-password')
            self.preseed(question, password)
            self.preseed(question + '-again', password)
        else:
            self.preseed(question, ", ".join(self.choices(question)))

        return True

    def error(self, priority, question):
        self.frontend.error_dialog(self.description(question),
                                   self.extended_description(question))
        return FilteredCommand.error(self, priority, question)
    
    def ok_handler(self):
        choices = self.frontend.ma_get_choices()
        username = self.db.get('passwd/username')
        users = {}

        for c in choices:
            if c['selected']:
                question = 'migration-assistant/%s/%s/' % \
                    (c['part'],c['user'].replace(' ','+'))
                self.db.register('migration-assistant/items', question + 'items')
                self.preseed(question + 'items', ', '.join(c['items']))
                self.db.register('migration-assistant/user', question + 'user')
                self.preseed(question + 'user', username)
                try:
                    users[c['part']].append(c['user'])
                except KeyError:
                    users[c['part']] = [c['user']]

        for p in users.iterkeys():
            question = 'migration-assistant/%s/users' % p
            self.db.register('migration-assistant/users', question)
            self.preseed(question, ', '.join(users[p]))

        FilteredCommand.ok_handler(self)

    def filter_parts(self):
        question = 'migration-assistant/partitions'
        from ubiquity.parted_server import PartedServer
        regain_privileges()
        parted = PartedServer()

        parts = []
        for disk in parted.disks():
            parted.select_disk(disk)
            for partition in parted.partitions():
                # We check to see if the partition is scheduled to be
                # formatted and if not add it to the list of post-commit
                # available partitions.
                filename = '/var/lib/partman/devices/%s/%s/format' % \
                    (disk, partition[1])
                if os.path.exists(filename):
                    syslog.syslog('filtering out %s as it is to be formatted.' % partition[5])
                else:
                    parts.append(partition[5])

        drop_privileges()
        ret = []
        for choice in self.choices(question):
            if choice[choice.rfind('(')+1:choice.rfind(')')] in parts:
                ret.append(choice)

        self.preseed(question, ", ".join(ret))

    def set_choices(self):
        tree = []
        systems = self.db.get('migration-assistant/partitions')
        if systems:
            systems = systems.split(', ')
            try:
                ret = []
                for oper in systems:
                    osref = oper
                    part = oper[oper.rfind('/')+1:-1] # hda1
                    oper = oper[:oper.rfind('(')-1]

                    users = self.db.get('migration-assistant/' + part + '/users')
                    if not users:
                        syslog.syslog('migration-assistant: filtering out %s' \
                            ' as it has no users' % osref)
                        continue
                    else:
                        ret.append(osref)

                    users = users.split(', ')
                    for user in users:
                        items = self.db.get('migration-assistant/' + part + '/' + \
                            user.replace(' ', '+') + '/items')
                        # If there are no items to import for the user, there's no sense
                        # in showing it.  It might make more sense to move this check
                        # into ma-ask.
                        if items:
                            items = items.split(', ')
                            tree.append({'user': user,
                                         'part': part,
                                         'os': oper,
                                         'items': items,
                                         'selected': False})
                    # We now unset everything as the checkboxes will be unselected
                    # by default and debconf needs to match that.
                    self.db.set('migration-assistant/%s/users' % part, '')
                # Prune out partitions that do not have any users.
                self.db.set('migration-assistant/partitions', ", ".join(ret))
            except debconf.DebconfError, e:
                for line in str(e).split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                self.db.set('migration-assistant/partitions', '')
                tree = []

        self.frontend.ma_set_choices(tree)

# vim:ai:et:sts=4:tw=80:sw=4:
