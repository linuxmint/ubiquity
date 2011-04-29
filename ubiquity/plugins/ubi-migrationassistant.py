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
import os
import debconf

from ubiquity import plugin

NAME = 'migrationassistant'
AFTER = 'usersetup'
WEIGHT = 10
# Not useful in oem-config.
OEM = False

class PageBase(plugin.PluginUI):
    def ma_set_choices(self, choices):
        """Set the available migration-assistant choices."""
        pass

    def ma_get_choices(self):
        """Get the selected migration-assistant choices."""
        raise NotImplementedError('ma_get_choices')

    def ma_user_error(self, error, user):
        """The selected migration-assistant username was bad."""
        raise NotImplementedError('ma_user_error')

    def ma_password_error(self, error, user):
        """The selected migration-assistant password was bad."""
        raise NotImplementedError('ma_password_error')

class PageGtk(PageBase):
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        self.ma_choices = []
        try:
            import gtk
            builder = gtk.Builder()
            self.controller.add_builder(builder)
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], 'stepMigrationAssistant.ui'))
            builder.connect_signals(self)
            self.page = builder.get_object('stepMigrationAssistant')
            self.matreeview = builder.get_object('matreeview')
        except Exception, e:
            self.debug('Could not create keyboard page: %s', e)
            self.page = None
        self.plugin_widgets = self.page

    def ma_get_choices(self):
        return self.ma_choices

    def ma_cb_toggle(self, cell, path, model=None):
        iterator = model.get_iter(path)
        checked = not cell.get_active()
        model.set_value(iterator, 0, checked)

        # We're on a user checkbox.
        if model.iter_children(iterator):
            if not cell.get_active():
                model.get_value(iterator, 1)['selected'] = True
            else:
                model.get_value(iterator, 1)['selected'] = False
            parent = iterator
            iterator = model.iter_children(iterator)
            items = []
            while iterator:
                model.set_value(iterator, 0, checked)
                if checked:
                    items.append(model.get_value(iterator, 1))
                iterator = model.iter_next(iterator)
            model.get_value(parent, 1)['items'] = items

        # We're on an item checkbox.
        else:
            parent = model.iter_parent(iterator)
            if not model.get_value(parent, 0):
                model.set_value(parent, 0, True)
                model.get_value(parent, 1)['selected'] = True

            item = model.get_value(iterator, 1)
            items = model.get_value(parent, 1)['items']
            if checked:
                items.append(item)
            else:
                items.remove(item)

    def ma_set_choices(self, choices):
        import gtk

        def cell_data_func(unused_column, cell, model, iterator):
            val = model.get_value(iterator, 1)
            if model.iter_children(iterator):
                # Windows XP...
                text = '%s  <small><i>%s (%s)</i></small>' % \
                       (val['user'], val['os'], val['part'])
            else:
                # Gaim, Yahoo, etc
                text = model.get_value(iterator, 1)

            try:
                cell.set_property("markup", unicode(text))
            except:
                cell.set_property("text", '%s  %s (%s)' % \
                    (val['user'], val['os'], val['part']))
        # Showing the interface for the second time.
        if self.matreeview.get_model():
            for col in self.matreeview.get_columns():
                self.matreeview.remove_column(col)

        # For the previous selected item.
        self.ma_previous_selection = None

        # TODO evand 2007-01-11 I'm on the fence as to whether or not skipping
        # the page would be better than showing the user this error.
        if not choices:
            # TODO cjwatson 2009-04-01: i18n
            msg = 'There were no users or operating systems suitable for ' \
                  'importing from.'
            liststore = gtk.ListStore(str)
            liststore.append([msg])
            self.matreeview.set_model(liststore)
            column = gtk.TreeViewColumn('item', gtk.CellRendererText(), text=0)
            self.matreeview.append_column(column)
        else:
            treestore = gtk.TreeStore(bool, object)

            # We save the choices list so we can preserve state, should the user
            # decide to move back through the interface.  We cannot just put the
            # old list back as the options could conceivably change.  For
            # example, the user moves back to the partitioning page, removes a
            # partition, and moves forward to the migration-assistant page.

            # TODO evand 2007-12-04: simplify.
            for choice in choices:
                kept = False
                for old_choice in self.ma_choices:
                    if (old_choice['user'] == choice['user']) and \
                    (old_choice['part'] == choice['part']):
                        piter = treestore.append(None, \
                            [old_choice['selected'], choice])
                        choice['selected'] = old_choice['selected']
                        new_items = []
                        for item in choice['items']:
                            if item in old_choice['items']:
                                treestore.append(piter, [True, item])
                                new_items.append(item)
                            else:
                                treestore.append(piter, [False, item])
                        choice['items'] = new_items
                        kept = True
                        break
                if not kept:
                    piter = treestore.append(None, [False, choice])
                    for item in choice['items']:
                        treestore.append(piter, [False, item])
                    choice['items'] = []

            self.matreeview.set_model(treestore)

            renderer = gtk.CellRendererToggle()
            renderer.connect('toggled', self.ma_cb_toggle, treestore)
            column = gtk.TreeViewColumn('boolean', renderer, active=0)
            column.set_clickable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.matreeview.append_column(column)

            renderer = gtk.CellRendererText()
            column = gtk.TreeViewColumn('item', renderer)
            column.set_cell_data_func(renderer, cell_data_func)
            self.matreeview.append_column(column)

            self.matreeview.set_search_column(1)

        self.matreeview.show_all()

        # Save the list so we can preserve state.
        self.ma_choices = choices


class PageNoninteractive(PageBase):
    pass

class Page(plugin.Plugin):
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

        elif question == 'ubiquity/run-ma-again':
            self.db.set('ubiquity/run-ma-again', 'false')
            self.set_choices()
            # If we didn't ask any questions, they're all preseeded and we don't
            # need to show the page, so we'll continue along.  If we got at
            # least one question, show the page.
            if not self.got_a_question:
                return self.succeeded
            else:
                return plugin.Plugin.run(self, priority, question)

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
        return plugin.Plugin.error(self, priority, question)

    def ok_handler(self):
        choices = self.ui.ma_get_choices()
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

        return plugin.Plugin.ok_handler(self)

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

        self.ui.ma_set_choices(tree)

class Install(plugin.InstallPlugin):
    def prepare(self):
        return (['/usr/lib/ubiquity/migration-assistant/ma-apply',
                 '/usr/lib/ubiquity/migration-assistant'], [])

    def install(self, target, progress, *args, **kwargs):
        progress.info('ubiquity/install/migrationassistant')
        return plugin.InstallPlugin.install(self, target, progress, *args, **kwargs)

    def error(self, priority, question):
        self.frontend.error_dialog(self.description(question))
        return plugin.InstallPlugin.error(self, priority, question)

# vim:ai:et:sts=4:tw=80:sw=4:
