# -*- coding: UTF-8 -*-

# Copyright (C) 2006, 2007, 2008 Canonical Ltd.
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

import os
import re
import shutil
import signal

import debconf

from ubiquity.filteredcommand import FilteredCommand
from ubiquity import parted_server
from ubiquity.misc import *

PARTITION_TYPE_PRIMARY = 0
PARTITION_TYPE_LOGICAL = 1

PARTITION_PLACE_BEGINNING = 0
PARTITION_PLACE_END = 1

class PartmanOptionError(LookupError):
    pass

class Partman(FilteredCommand):
    def __init__(self, frontend=None):
        FilteredCommand.__init__(self, frontend)
        self.some_device_desc = ''
        self.resize_desc = ''
        self.manual_desc = ''

    def prepare(self):
        # If an old parted_server is still running, clean it up.
        regain_privileges()
        if os.path.exists('/var/run/parted_server.pid'):
            try:
                pidline = open('/var/run/parted_server.pid').readline().strip()
                pid = int(pidline)
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
            try:
                os.unlink('/var/run/parted_server.pid')
            except OSError:
                pass

        # Force autopartitioning to be re-run.
        shutil.rmtree('/var/lib/partman', ignore_errors=True)
        drop_privileges()

        self.autopartition_question = None
        self.auto_state = None
        self.extra_options = {}
        self.extra_choice = None

        self.update_partitions = None
        self.building_cache = True
        self.__state = [['', None, None]]
        self.disk_cache = {}
        self.partition_cache = {}
        self.cache_order = []
        self.creating_label = None
        self.creating_partition = None
        self.editing_partition = None
        self.deleting_partition = None
        self.undoing = False
        self.finish_partitioning = False
        self.bad_auto_size = False

        questions = ['^partman-auto/.*automatically_partition$',
                     '^partman-auto/select_disk$',
                     '^partman-partitioning/confirm_resize$',
                     '^partman-partitioning/confirm_new_label$',
                     '^partman-partitioning/new_size$',
                     '^partman/choose_partition$',
                     '^partman/confirm.*',
                     '^partman/free_space$',
                     '^partman/active_partition$',
                     '^partman-partitioning/new_partition_(size|type|place)$',
                     '^partman-target/choose_method$',
                     '^partman-basicfilesystems/(fat_mountpoint|mountpoint|mountpoint_manual)$',
                     '^partman/exception_handler$',
                     '^partman/exception_handler_note$',
                     '^partman/unmount_active$',
                     '^partman/installation_medium_mounted$',
                     'type:boolean',
                     'ERROR',
                     'PROGRESS']
        return ('/bin/partman', questions,
                {'PARTMAN_NO_COMMIT': '1', 'PARTMAN_SNOOP': '1'})

    def snoop(self):
        """Read the partman snoop file hack, returning a list of tuples
        mapping from keys to displayed options. (We use a list of tuples
        because this preserves ordering and is reasonably fast to convert to
        a dictionary.)"""

        try:
            snoop = open('/var/lib/partman/snoop')
            options = []
            for line in snoop:
                line = unicode(line.rstrip('\n'), 'utf-8', 'replace')
                fields = line.split('\t', 1)
                if len(fields) == 2:
                    (key, option) = fields
                    options.append((key, option))
                    continue
            snoop.close()
            return options
        except IOError:
            return {}

    def snoop_menu(self, options):
        """Parse the raw snoop data into script, argument, and displayed
        name, as used by ask_user."""

        menu_options = []
        for (key, option) in options:
            keybits = key.split('__________', 1)
            if len(keybits) == 2:
                (script, arg) = keybits
                menu_options.append((script, arg, option))
        return menu_options

    def find_script(self, menu_options, want_script, want_arg=None):
        scripts = []
        for (script, arg, option) in menu_options:
            if ((want_script is None or script[2:] == want_script) and
                (want_arg is None or arg == want_arg)):
                scripts.append((script, arg, option))
        return scripts

    def must_find_one_script(self, question, menu_options,
                             want_script, want_arg=None):
        for (script, arg, option) in menu_options:
            if ((want_script is None or script[2:] == want_script) and
                (want_arg is None or arg == want_arg)):
                return (script, arg, option)
        else:
            raise PartmanOptionError, ("%s should have %s (%s) option" %
                                       (question, want_script, want_arg))

    def preseed_script(self, question, menu_options,
                       want_script, want_arg=None):
        (script, arg, option) = self.must_find_one_script(
            question, menu_options, want_script, want_arg)
        self.preseed(question, '%s__________%s' % (script, arg), seen=False)

    def split_devpart(self, devpart):
        dev, part_id = devpart.split('//', 1)
        if dev.startswith(parted_server.devices + '/'):
            dev = dev[len(parted_server.devices) + 1:]
            return dev, part_id
        else:
            return None, None

    def subdirectories(self, directory):
        for name in sorted(os.listdir(directory)):
            if os.path.isdir(os.path.join(directory, name)):
                yield name[2:]

    def scripts(self, directory):
        for name in sorted(os.listdir(directory)):
            if os.access(os.path.join(directory, name), os.X_OK):
                yield name[2:]

    def method_description(self, method):
        try:
            question = None
            if method == 'swap':
                question = 'partman/method_long/swap'
            elif method == 'efi':
                question = 'partman-efi/text/efi'
            elif method == 'newworld':
                question = 'partman/method_long/newworld'
            if question is not None:
                return self.description(question)
        except debconf.DebconfError:
            pass
        return method

    def filesystem_description(self, filesystem):
        try:
            return self.description('partman/filesystem_long/%s' % filesystem)
        except debconf.DebconfError:
            return filesystem

    def create_use_as(self):
        """Yields the possible methods that a new partition may use."""

        # TODO cjwatson 2006-11-01: This is a particular pain; we can't find
        # out the real list of possible uses from partman until after the
        # partition has been created, so we have to partially hardcode this.

        for method in self.subdirectories('/lib/partman/choose_method'):
            if method == 'filesystem':
                for fs in self.scripts('/lib/partman/valid_filesystems'):
                    if fs == 'ntfs':
                        pass
                    elif fs == 'fat':
                        yield (method, 'fat16',
                               self.filesystem_description('fat16'))
                        yield (method, 'fat32',
                               self.filesystem_description('fat32'))
                    else:
                        yield (method, fs, self.filesystem_description(fs))
            elif method == 'dont_use':
                question = 'partman-basicmethods/text/dont_use'
                yield (method, 'dontuse', self.description(question))
            elif method == 'efi':
                if os.path.exists('/var/lib/partman/efi'):
                    yield (method, method, self.method_description(method))
            else:
                yield (method, method, self.method_description(method))

    def default_mountpoint_choices(self, fs='ext3'):
        """Yields the possible mountpoints for a partition."""

        # We can't find out the real list of possible mountpoints from
        # partman until after the partition has been created, but we can at
        # least fish it out of the appropriate debconf template rather than
        # having to hardcode it.

        if fs in ('fat16', 'fat32', 'ntfs'):
            question = 'partman-basicfilesystems/fat_mountpoint'
        else:
            question = 'partman-basicfilesystems/mountpoint'
        choices_c = self.choices_untranslated(question)
        choices = self.choices(question)
        assert len(choices_c) == len(choices)
        for i in range(len(choices_c)):
            if choices_c[i].startswith('/'):
                yield (choices_c[i].split(' ')[0], choices_c[i], choices[i])

    def get_current_method(self, partition):
        if 'method' in partition:
            if partition['method'] in ('format', 'keep'):
                if 'filesystem' in partition:
                    return partition['filesystem']
                else:
                    return None
            else:
                return partition['method']
        else:
            return 'dontuse'

    def get_current_mountpoint(self, partition):
        if ('method' in partition and 'acting_filesystem' in partition and
            'mountpoint' in partition):
            return partition['mountpoint']
        else:
            return None

    def get_actions(self, devpart, partition):
        if devpart is None and partition is None:
            return
        if 'id' not in partition:
            yield 'new_label'
        if 'can_new' in partition and partition['can_new']:
            yield 'new'
        if 'id' in partition and partition['parted']['fs'] != 'free':
            yield 'edit'
            yield 'delete'
        # TODO cjwatson 2006-12-22: options for whole disks

    def set(self, question, value):
        if question == 'ubiquity/partman-rebuild-cache':
            if not self.building_cache:
                self.debug('Partman: Partition %s updated', value)
                if self.update_partitions is None:
                    self.update_partitions = []
                if value not in self.update_partitions:
                    self.update_partitions.append(value)
            self.debug('Partman: update_partitions = %s',
                       self.update_partitions)

    def subst(self, question, key, value):
        if question == 'partman-partitioning/new_size':
            if self.building_cache and self.autopartition_question is None:
                state = self.__state[-1]
                assert state[0] == 'partman/active_partition'
                partition = self.partition_cache[state[1]]
                if key == 'RAWMINSIZE':
                    partition['resize_min_size'] = int(value)
                elif key == 'RAWMAXSIZE':
                    partition['resize_max_size'] = int(value)
            if key == 'RAWMINSIZE':
                self.resize_min_size = int(value)
            elif key == 'RAWMAXSIZE':
                self.resize_max_size = int(value)
            elif key == 'ORISIZE':
                self.resize_orig_size = int(value)
            elif key == 'PATH':
                self.resize_path = value

    def error(self, priority, question):
        if question == 'partman-partitioning/impossible_resize':
            # Back up silently.
            return False
        elif question == 'partman-partitioning/bad_new_partition_size':
            if self.creating_partition:
                # Break out of creating the partition.
                self.creating_partition['bad_size'] = True
        elif question in ('partman-partitioning/bad_new_size',
                          'partman-partitioning/big_new_size',
                          'partman-partitioning/small_new_size',
                          'partman-partitioning/new_size_commit_failed'):
            if self.editing_partition:
                # Break out of resizing the partition.
                self.editing_partition['bad_size'] = True
            else:
                # Break out of resizing the partition in cases where partman
                # fed us bad boundary values.  These are bugs in partman, but
                # we should handle the result as gracefully as possible.
                self.bad_auto_size = True
        elif question == 'partman-basicfilesystems/bad_mountpoint':
            # Break out of creating or editing the partition.
            if self.creating_partition:
                self.creating_partition['bad_mountpoint'] = True
            elif self.editing_partition:
                self.editing_partition['bad_mountpoint'] = True
        self.frontend.error_dialog(self.description(question),
                                   self.extended_description(question))
        return FilteredCommand.error(self, priority, question)

    def run(self, priority, question):
        if self.done:
            # user answered confirmation question or backed up
            return self.succeeded

        self.current_question = question
        options = self.snoop()
        menu_options = self.snoop_menu(options)
        self.debug('Partman: state = %s', self.__state)
        self.debug('Partman: auto_state = %s', self.auto_state)

        if question.endswith('automatically_partition'):
            self.autopartition_question = question
            choices = self.choices(question)

            if self.auto_state is None:
                self.some_device_desc = \
                    self.description('partman-auto/text/use_device')
                self.resize_desc = \
                    self.description('partman-auto/text/resize_use_free')
                self.manual_desc = \
                    self.description('partman-auto/text/custom_partitioning')
                self.biggest_free_desc = \
                    self.description('partman-auto/text/use_biggest_free')
                self.extra_options = {}
                if choices:
                    self.auto_state = [0, None]
            else:
                self.auto_state[0] += 1
            while self.auto_state[0] < len(choices):
                self.auto_state[1] = choices[self.auto_state[0]]
                if (self.auto_state[1] == self.some_device_desc or
                    self.auto_state[1] == self.resize_desc):
                    break
                else:
                    self.auto_state[0] += 1
            if self.auto_state[0] < len(choices):
                self.preseed_as_c(question, self.auto_state[1], seen=False)
                self.succeeded = True
                return True
            else:
                self.auto_state = None

            if self.resize_desc not in self.extra_options:
                try:
                    del choices[choices.index(self.resize_desc)]
                except ValueError:
                    pass
            regain_privileges()
            # {'/dev/sda' : ('/dev/sda1', 24973242, '32256-2352430079'), ...
            # TODO evand 2009-04-16: We should really use named tuples here.
            parted = parted_server.PartedServer()
            layout = {}
            for disk in parted.disks():
                parted.select_disk(disk)
                ret = []
                total = 0
                for partition in parted.partitions():
                    size = int(partition[2])
                    if partition[4] == 'free':
                        dev = 'free'
                    else:
                        dev = partition[5]
                    ret.append((dev, size, partition[1]))
                layout[disk] = ret

            self.frontend.set_disk_layout(layout)
            drop_privileges()
            
            # Set up translation mappings to avoid debian-installer
            # specific text ('Guided -').
            self.translation_mappings = {}
            def map_trans(di_string, ubiquity_string):
                ubiquity_string = self.description(ubiquity_string)
                self.translation_mappings[ubiquity_string] = di_string
                try:
                    choices[choices.index(di_string)] = ubiquity_string
                except ValueError:
                    pass
                if di_string in self.extra_options:
                    t = self.extra_options[di_string]
                    del self.extra_options[di_string]
                    self.extra_options[ubiquity_string] = t
                return ubiquity_string

            self.some_device_desc = map_trans(self.some_device_desc, 'ubiquity/text/use_device')
            self.biggest_free_desc = map_trans(self.biggest_free_desc, 'ubiquity/text/biggest_free')
            self.resize_desc = map_trans(self.resize_desc, 'ubiquity/text/resize_use_free')
            self.manual_desc = map_trans(self.manual_desc, 'ubiquity/text/custom_partitioning')
            
            biggest_free = self.find_script(menu_options, 'biggest_free')
            if biggest_free:
                biggest_free = biggest_free[0][1]
                biggest_free = self.split_devpart(biggest_free)[1]
            self.extra_options[self.biggest_free_desc] = biggest_free

            self.frontend.set_autopartition_choices(
                choices, self.extra_options, self.resize_desc,
                self.manual_desc, self.biggest_free_desc)

        elif question == 'partman-auto/select_disk':
            if self.auto_state is not None:
                self.extra_options[self.auto_state[1]] = self.choices(question)
                # Back up to autopartitioning question.
                self.succeeded = False
                return False
            else:
                assert self.extra_choice is not None
                self.preseed_as_c(question, self.extra_choice, seen=False)
                self.succeeded = True
                return True

        elif question == 'partman/choose_partition':
            self.autopartition_question = None # not autopartitioning any more

            if not self.building_cache and self.update_partitions:
                # Rebuild our cache of just these partitions.
                self.__state = [['', None, None]]
                self.building_cache = True
                if 'ALL' in self.update_partitions:
                    self.update_partitions = None

            if self.building_cache:
                state = self.__state[-1]
                if state[0] == question:
                    # advance to next partition
                    self.frontend.debconf_progress_step(1)
                    self.frontend.refresh()
                    self.debug('Partman: update_partitions = %s',
                               self.update_partitions)
                    state[1] = None
                    while self.update_partitions:
                        state[1] = self.update_partitions[0]
                        del self.update_partitions[0]
                        if state[1] not in self.partition_cache:
                            self.debug('Partman: %s not found in cache',
                                       partition)
                            state[1] = None
                            self.frontend.debconf_progress_step(1)
                            self.frontend.refresh()
                        else:
                            break

                    if state[1] is not None:
                        # Move on to the next partition.
                        partition = self.partition_cache[state[1]]
                        self.debug('Partman: Building cache (%s)',
                                   partition['parted']['path'])
                        self.preseed(question, partition['display'],
                                     seen=False)
                        return True
                    else:
                        # Finished building the cache.
                        self.debug('Partman: Finished building cache')
                        self.__state.pop()
                        self.update_partitions = None
                        self.building_cache = False
                        self.frontend.debconf_progress_stop()
                        self.frontend.refresh()
                        self.frontend.update_partman(
                            self.disk_cache, self.partition_cache,
                            self.cache_order)
                else:
                    self.debug('Partman: Building cache')
                    regain_privileges()
                    parted = parted_server.PartedServer()
                    matches = self.find_script(menu_options, 'partition_tree')

                    # If we're only updating our cache for certain
                    # partitions, then self.update_partitions will be a list
                    # of the partitions to update; otherwise, we build the
                    # cache from scratch.
                    rebuild_all = self.update_partitions is None

                    if rebuild_all:
                        self.disk_cache = {}
                        self.partition_cache = {}
                    self.cache_order = []

                    # Clear out the partitions we're updating to make sure
                    # stale keys are removed.
                    if self.update_partitions is not None:
                        for devpart in self.update_partitions:
                            if devpart in self.partition_cache:
                                del self.partition_cache[devpart]

                    # Initialise any items we haven't heard of yet.
                    for script, arg, option in matches:
                        dev, part_id = self.split_devpart(arg)
                        if not dev:
                            continue
                        parted.select_disk(dev)
                        self.cache_order.append(arg)
                        if part_id:
                            if rebuild_all or arg not in self.partition_cache:
                                self.partition_cache[arg] = {
                                    'dev': dev,
                                    'id': part_id,
                                    'parent': dev.replace('=', '/')
                                }
                        else:
                            if rebuild_all or arg not in self.disk_cache:
                                device = parted.readline_device_entry('device')
                                self.disk_cache[arg] = {
                                    'dev': dev,
                                    'device': device
                                }

                    if self.update_partitions is None:
                        self.update_partitions = self.partition_cache.keys()
                    else:
                        self.update_partitions = [devpart
                            for devpart in self.update_partitions
                            if devpart in self.partition_cache]

                    # Update the display names of all disks and partitions.
                    for script, arg, option in matches:
                        dev, part_id = self.split_devpart(arg)
                        if not dev:
                            continue
                        parted.select_disk(dev)
                        if part_id:
                            self.partition_cache[arg]['display'] = '%s__________%s' % (script, arg)
                        else:
                            self.disk_cache[arg]['display'] = '%s__________%s' % (script, arg)

                    # Get basic information from parted_server for each
                    # partition being updated.
                    for devpart in self.update_partitions:
                        dev, part_id = self.split_devpart(devpart)
                        if not dev:
                            continue
                        parted.select_disk(dev)
                        info = parted.partition_info(part_id)
                        self.partition_cache[devpart]['parted'] = {
                            'num': info[0],
                            'id': info[1],
                            'size': info[2],
                            'type': info[3],
                            'fs': info[4],
                            'path': info[5],
                            'name': info[6]
                        }

                    drop_privileges()
                    self.frontend.debconf_progress_start(
                        0, len(self.update_partitions),
                        self.description('partman/progress/init/parted'))
                    self.frontend.refresh()
                    self.debug('Partman: update_partitions = %s',
                               self.update_partitions)

                    # Selecting a disk will ask to create a new disklabel,
                    # so don't bother with that.

                    devpart = None
                    if self.partition_cache:
                        while self.update_partitions:
                            devpart = self.update_partitions[0]
                            del self.update_partitions[0]
                            if devpart not in self.partition_cache:
                                self.debug('Partman: %s not found in cache',
                                           partition)
                                devpart = None
                                self.frontend.debconf_progress_step(1)
                                self.frontend.refresh()
                            else:
                                break
                    if devpart is not None:
                        partition = self.partition_cache[devpart]
                        self.debug('Partman: Building cache (%s)',
                                   partition['parted']['path'])
                        self.__state.append([question, devpart, None])
                        self.preseed(question, partition['display'],
                                     seen=False)
                        return True
                    else:
                        self.debug('Partman: Finished building cache '
                                   '(no partitions to update)')
                        self.update_partitions = None
                        self.building_cache = False
                        self.frontend.debconf_progress_stop()
                        self.frontend.refresh()
                        self.frontend.update_partman(
                            self.disk_cache, self.partition_cache,
                            self.cache_order)
            elif self.creating_partition:
                devpart = self.creating_partition['devpart']
                if devpart in self.partition_cache:
                    self.frontend.update_partman(
                        self.disk_cache, self.partition_cache,
                        self.cache_order)
            elif self.editing_partition:
                devpart = self.editing_partition['devpart']
                if devpart in self.partition_cache:
                    self.frontend.update_partman(
                        self.disk_cache, self.partition_cache,
                        self.cache_order)
            elif self.deleting_partition:
                raise AssertionError, "Deleting partition didn't rebuild cache?"

            if self.debug_enabled():
                import pprint
                self.debug('disk_cache:')
                printer = pprint.PrettyPrinter()
                for line in printer.pformat(self.disk_cache).split('\n'):
                    self.debug('%s', line)
                self.debug('disk_cache end')
                self.debug('partition_cache:')
                printer = pprint.PrettyPrinter()
                for line in printer.pformat(self.partition_cache).split('\n'):
                    self.debug('%s', line)
                self.debug('partition_cache end')

            self.__state = [['', None, None]]
            self.creating_label = None
            self.creating_partition = None
            self.editing_partition = None
            self.deleting_partition = None
            self.undoing = False
            self.finish_partitioning = False

            FilteredCommand.run(self, priority, question)

            if self.finish_partitioning or self.done:
                if self.succeeded:
                    self.preseed_script(question, menu_options, 'finish')
                return self.succeeded

            elif self.creating_label:
                devpart = self.creating_label['devpart']
                if devpart in self.disk_cache:
                    disk = self.disk_cache[devpart]
                    # No need to use self.__state to keep track of this.
                    self.preseed(question, disk['display'], seen=False)
                return True

            elif self.creating_partition:
                devpart = self.creating_partition['devpart']
                if devpart in self.partition_cache:
                    partition = self.partition_cache[devpart]
                    self.__state.append([question, devpart, None])
                    self.preseed(question, partition['display'], seen=False)
                return True

            elif self.editing_partition:
                devpart = self.editing_partition['devpart']
                if devpart in self.partition_cache:
                    partition = self.partition_cache[devpart]
                    self.__state.append([question, devpart, None])
                    self.preseed(question, partition['display'], seen=False)
                return True

            elif self.deleting_partition:
                devpart = self.deleting_partition['devpart']
                if devpart in self.partition_cache:
                    partition = self.partition_cache[devpart]
                    # No need to use self.__state to keep track of this.
                    self.preseed(question, partition['display'], seen=False)
                return True

            elif self.undoing:
                self.preseed_script(question, menu_options, 'undo')
                return True

            else:
                raise AssertionError, ("Returned to %s with nothing to do" %
                                       question)

        elif question == 'partman-partitioning/confirm_new_label':
            if self.creating_label:
                response = self.frontend.question_dialog(
                    self.description(question),
                    self.extended_description(question),
                    ('ubiquity/text/go_back', 'ubiquity/text/continue'))
                if response is None or response == 'ubiquity/text/continue':
                    self.preseed(question, 'true', seen=False)
                else:
                    self.preseed(question, 'false', seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman/free_space':
            if self.building_cache:
                state = self.__state[-1]
                assert state[0] == 'partman/choose_partition'
                partition = self.partition_cache[state[1]]
                can_new = False
                if self.find_script(menu_options, 'new'):
                    can_new = True
                partition['can_new'] = can_new
                # Back up to the previous menu.
                return False
            elif self.creating_partition:
                self.preseed_script(question, menu_options, 'new')
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-partitioning/new_partition_size':
            if self.creating_partition:
                if 'bad_size' in self.creating_partition:
                    return False
                size = self.creating_partition['size']
                if re.search(r'^[0-9.]+$', size):
                    # ensure megabytes just in case partman's semantics change
                    size += 'M'
                self.preseed(question, size, seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-partitioning/new_partition_type':
            if self.creating_partition:
                if self.creating_partition['type'] == PARTITION_TYPE_PRIMARY:
                    self.preseed(question, 'Primary', seen=False)
                else:
                    self.preseed(question, 'Logical', seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-partitioning/new_partition_place':
            if self.creating_partition:
                if (self.creating_partition['place'] ==
                    PARTITION_PLACE_BEGINNING):
                    self.preseed(question, 'Beginning', seen=False)
                else:
                    self.preseed(question, 'End', seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman/active_partition':
            if self.building_cache:
                state = self.__state[-1]
                partition = self.partition_cache[state[1]]

                if state[0] == question:
                    state[2] += 1
                    if state[2] < len(partition['active_partition_build']):
                        # Move on to the next item.
                        visit = partition['active_partition_build']
                        self.preseed_as_c(question, visit[state[2]][2], seen=False)
                        return True
                    else:
                        # Finished building the cache for this submenu; go
                        # back to the previous one.
                        try:
                            del partition['active_partition_build']
                        except KeyError:
                            pass
                        self.__state.pop()
                        return False

                assert state[0] == 'partman/choose_partition'
                regain_privileges()
                parted = parted_server.PartedServer()

                parted.select_disk(partition['dev'])
                for entry in ('method',
                              'filesystem', 'detected_filesystem',
                              'acting_filesystem',
                              'existing', 'formatable',
                              'mountpoint'):
                    if parted.has_part_entry(partition['id'], entry):
                        partition[entry] = \
                            parted.readline_part_entry(partition['id'], entry)

                drop_privileges()
                visit = []
                for (script, arg, option) in menu_options:
                    if arg in ('method', 'mountpoint'):
                        visit.append((script, arg, option))
                    elif arg == 'format':
                        partition['can_activate_format'] = True
                    elif arg == 'resize':
                        visit.append((script, arg, option))
                        partition['can_resize'] = True
                if visit:
                    partition['active_partition_build'] = visit
                    self.__state.append([question, state[1], 0])
                    self.preseed_as_c(question, visit[0][2], seen=False)
                    return True
                else:
                    # Back up to the previous menu.
                    return False

            elif self.creating_partition or self.editing_partition:
                if self.creating_partition:
                    request = self.creating_partition
                else:
                    request = self.editing_partition

                state = self.__state[-1]
                partition = self.partition_cache[state[1]]

                if state[0] != question:
                    # Set up our intentions for this menu.
                    visit = []
                    for item in ('method', 'mountpoint', 'format'):
                        if item in request and request[item] is not None:
                            visit.append(item)
                    if (self.editing_partition and
                        'size' in request and request['size'] is not None):
                        visit.append('resize')
                    partition['active_partition_edit'] = visit
                    self.__state.append([question, state[1], -1])
                    state = self.__state[-1]

                state[2] += 1
                while state[2] < len(partition['active_partition_edit']):
                    # Move on to the next item.
                    visit = partition['active_partition_edit']
                    item = visit[state[2]]
                    scripts = self.find_script(menu_options, None, item)
                    if scripts:
                        self.preseed_as_c(question, scripts[0][2], seen=False)
                        return True
                    state[2] += 1

                # If we didn't find anything to do, finish editing this
                # partition.
                try:
                    del partition['active_partition_edit']
                except KeyError:
                    pass
                self.__state.pop()
                self.preseed_script(question, menu_options, 'finish')
                return True

            elif self.deleting_partition:
                self.preseed_script(question, menu_options, 'delete')
                self.deleting_partition = None
                return True

            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-partitioning/confirm_resize':
            if self.autopartition_question is not None:
                if self.auto_state is not None:
                    # Proceed through confirmation question; we'll back up
                    # later.
                    self.preseed(question, 'true', seen=False)
                    return True
                else:
                    response = self.frontend.question_dialog(
                        self.description(question),
                        self.extended_description(question),
                        ('ubiquity/text/go_back', 'ubiquity/text/continue'))
                    if (response is None or
                        response == 'ubiquity/text/continue'):
                        self.preseed(question, 'true', seen=False)
                    else:
                        self.preseed(question, 'false', seen=False)
                    return True
            elif self.building_cache:
                state = self.__state[-1]
                assert state[0] == 'partman/active_partition'
                # Proceed through to asking for the size; don't worry, we'll
                # back up from there.
                self.preseed(question, 'true', seen=False)
                return True
            elif self.editing_partition:
                response = self.frontend.question_dialog(
                    self.description(question),
                    self.extended_description(question),
                    ('ubiquity/text/go_back', 'ubiquity/text/continue'))
                if response is None or response == 'ubiquity/text/continue':
                    self.preseed(question, 'true', seen=False)
                else:
                    self.preseed(question, 'false', seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-partitioning/new_size':
            if self.autopartition_question is not None:
                if self.auto_state is not None:
                    self.extra_options[self.auto_state[1]] = \
                        (self.resize_min_size, self.resize_max_size,
                            self.resize_orig_size, self.resize_path)
                    # Back up to autopartitioning question.
                    self.succeeded = False
                    return False
                else:
                    assert self.extra_choice is not None
                    if self.bad_auto_size:
                        self.bad_auto_size = False
                        return False
                    self.preseed(question, self.extra_choice, seen=False)
                    self.succeeded = True
                    return True
            elif self.building_cache:
                # subst() should have gathered the necessary information.
                # Back up.
                return False
            elif self.editing_partition:
                if 'bad_size' in self.editing_partition:
                    return False
                size = self.editing_partition['size']
                if re.search(r'^[0-9.]+$', size):
                    # ensure megabytes just in case partman's semantics change
                    size += 'M'
                self.preseed(question, size, seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-target/choose_method':
            if self.building_cache:
                state = self.__state[-1]
                assert state[0] == 'partman/active_partition'
                partition = self.partition_cache[state[1]]
                partition['method_choices'] = []
                for (script, arg, option) in menu_options:
                    partition['method_choices'].append((script, arg, option))
                # Back up to the previous menu.
                return False
            elif self.creating_partition or self.editing_partition:
                if self.creating_partition:
                    request = self.creating_partition
                else:
                    request = self.editing_partition

                self.preseed_script(question, menu_options,
                                    None, request['method'])
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question in ('partman-basicfilesystems/mountpoint',
                          'partman-basicfilesystems/fat_mountpoint'):
            if self.building_cache:
                state = self.__state[-1]
                assert state[0] == 'partman/active_partition'
                partition = self.partition_cache[state[1]]
                partition['mountpoint_choices'] = []
                choices_c = self.choices_untranslated(question)
                choices = self.choices(question)
                assert len(choices_c) == len(choices)
                for i in range(len(choices_c)):
                    if choices_c[i].startswith('/'):
                        partition['mountpoint_choices'].append((
                            choices_c[i].split(' ')[0],
                            choices_c[i], choices[i]))
                # Back up to the previous menu.
                return False
            elif self.creating_partition or self.editing_partition:
                if self.creating_partition:
                    request = self.creating_partition
                else:
                    request = self.editing_partition
                if 'bad_mountpoint' in request:
                    return False
                mountpoint = request['mountpoint']

                if mountpoint == '' or mountpoint is None:
                    self.preseed(question, 'Do not mount it', seen=False)
                else:
                    self.preseed(question, 'Enter manually', seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question == 'partman-basicfilesystems/mountpoint_manual':
            if self.creating_partition or self.editing_partition:
                if self.creating_partition:
                    request = self.creating_partition
                else:
                    request = self.editing_partition
                if 'bad_mountpoint' in request:
                    return False

                self.preseed(question, request['mountpoint'], seen=False)
                return True
            else:
                raise AssertionError, "Arrived at %s unexpectedly" % question

        elif question.startswith('partman/confirm'):
            if question == 'partman/confirm':
                self.db.set('ubiquity/partman-made-changes', 'true')
            else:
                self.db.set('ubiquity/partman-made-changes', 'false')
            self.preseed(question, 'true', seen=False)
            self.succeeded = True
            self.done = True
            return True

        elif question == 'partman/exception_handler':
            if priority == 'critical' or priority == 'high':
                response = self.frontend.question_dialog(
                    self.description(question),
                    self.extended_description(question),
                    self.choices(question), use_templates=False)
                self.preseed(question, response, seen=False)
            else:
                self.preseed(question, 'unhandled', seen=False)
            return True

        elif question == 'partman/exception_handler_note':
            if priority == 'critical' or priority == 'high':
                self.frontend.error_dialog(self.description(question),
                                           self.extended_description(question))
                return FilteredCommand.error(self, priority, question)
            else:
                return True

        elif question == 'partman/installation_medium_mounted':
            self.frontend.installation_medium_mounted(
                self.extended_description(question))
            return True

        elif self.question_type(question) == 'boolean':
            if question == 'partman/unmount_active':
                yes = 'ubiquity/imported/yes'
                no = 'ubiquity/imported/no'
            else:
                yes = 'ubiquity/text/continue'
                no = 'ubiquity/text/go_back'
            response = self.frontend.question_dialog(
                self.description(question),
                self.extended_description(question), (no, yes))

            answer_reversed = False
            if question in ('partman-jfs/jfs_boot', 'partman-jfs/jfs_root',
                            'partman/unmount_active'):
                answer_reversed = True
            if response is None or response == yes:
                answer = answer_reversed
            else:
                answer = not answer_reversed
            if answer:
                self.preseed(question, 'true', seen=False)
            else:
                self.preseed(question, 'false', seen=False)
            return True

        return FilteredCommand.run(self, priority, question)

    def ok_handler(self):
        if self.current_question.endswith('automatically_partition'):
            (autopartition_choice, self.extra_choice) = \
                self.frontend.get_autopartition_choice()
            if autopartition_choice in self.translation_mappings:
                autopartition_choice = \
                    self.translation_mappings[autopartition_choice]
            self.preseed_as_c(self.current_question, autopartition_choice,
                              seen=False)
            # Don't exit partman yet.
        else:
            self.finish_partitioning = True
        self.succeeded = True
        self.exit_ui_loops()

    # TODO cjwatson 2006-11-01: Do we still need this?
    def rebuild_cache(self):
        assert self.current_question == 'partman/choose_partition'
        self.building_cache = True

    def create_label(self, devpart):
        assert self.current_question == 'partman/choose_partition'
        self.creating_label = {
            'devpart': devpart
        }
        self.exit_ui_loops()

    def create_partition(self, devpart, size, prilog, place,
                         method=None, mountpoint=None):
        assert self.current_question == 'partman/choose_partition'
        self.creating_partition = {
            'devpart': devpart,
            'size': size,
            'type': prilog,
            'place': place,
            'method': method,
            'mountpoint': mountpoint
        }
        self.exit_ui_loops()

    def edit_partition(self, devpart, size=None,
                       method=None, mountpoint=None, format=None):
        assert self.current_question == 'partman/choose_partition'
        self.editing_partition = {
            'devpart': devpart,
            'size': size,
            'method': method,
            'mountpoint': mountpoint,
            'format': format
        }
        self.exit_ui_loops()

    def delete_partition(self, devpart):
        assert self.current_question == 'partman/choose_partition'
        self.deleting_partition = {
            'devpart': devpart
        }
        self.exit_ui_loops()

    def undo(self):
        assert self.current_question == 'partman/choose_partition'
        self.undoing = True
        self.exit_ui_loops()

# Notes:
#
#   partman-auto/init_automatically_partition
#     Resize <partition> and use freed space
#     Erase entire disk: <disk> - <description>
#     Manually edit partition table
#
#   may show multiple disks, in which case massage into disk chooser (later)
#
#   if the resize option shows up, then run os-prober and display at the
#   top?
#
#   resize follow-up question:
#       partman-partitioning/new_size
#   progress bar:
#       partman-partitioning/progress_resizing
#
#   manual editing:
#       partman/choose_partition
#
#   final confirmation:
#       partman/confirm*
