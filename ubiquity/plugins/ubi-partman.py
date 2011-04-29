# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

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

from ubiquity import plugin
from ubiquity import parted_server
from ubiquity import misc
from ubiquity import osextras
from ubiquity.install_misc import archdetect
from collections import namedtuple

NAME = 'partman'
AFTER = 'prepare'
WEIGHT = 11
# Not useful in oem-config.
OEM = False

PartitioningOption = namedtuple('PartitioningOption', ['title', 'desc'])
Partition = namedtuple('Partition', ['device', 'size', 'id', 'filesystem'])


class PageBase(plugin.PluginUI):
    def __init__(self, *args, **kwargs):
        plugin.PluginUI.__init__(self)

    def show_page_advanced(self):
        pass

    def set_disk_layout(self, layout):
        pass

    def set_default_filesystem(self, fs):
        '''The default filesystem used when creating partitions.'''
        self.default_filesystem = fs

    def set_autopartition_heading(self, heading):
        pass

    def set_autopartition_options(self, options, extra_options):
        pass

    def get_autopartition_choice(self):
        """Get the selected autopartitioning choice."""
        pass

    def installation_medium_mounted(self, message):
        """Note that the installation medium is mounted."""
        pass

    def update_partman(self, disk_cache, partition_cache, cache_order):
        """Update the manual partitioner display."""
        pass

    def get_grub_choice(self):
        return misc.grub_default()

class PageGtk(PageBase):
    plugin_title = 'ubiquity/text/part_auto_heading_label'
    plugin_is_install = True
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        try:
            import gtk
            builder = gtk.Builder()
            self.controller.add_builder(builder)
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], 'stepPartAsk.ui'))
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], 'stepPartAuto.ui'))
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], 'stepPartAdvanced.ui'))
            builder.connect_signals(self)

            self.page_ask = builder.get_object('stepPartAsk')
            self.page_auto = builder.get_object('stepPartAuto')
            self.page_advanced = builder.get_object('stepPartAdvanced')

            # Grub options
            self.bootloader_vbox = builder.get_object('bootloader_vbox')
            self.grub_device_entry = builder.get_object('grub_device_entry')

            # Automatic page
            self.resizewidget = builder.get_object('resizewidget')
            self.partitionbox = builder.get_object('partitionbox')
            self.partition_container = builder.get_object('partition_container')
            self.part_auto_select_drive = builder.get_object('part_auto_select_drive')
            self.resize_use_free = builder.get_object('resize_use_free')
            self.custom_partitioning = builder.get_object('custom_partitioning')
            self.use_device = builder.get_object('use_device')
            self.reuse_partition = builder.get_object('reuse_partition')
            self.part_auto_allocate_label = builder.get_object('part_auto_allocate_label')
            self.part_auto_hidden_label = builder.get_object('part_auto_hidden_label')
            self.part_advanced_vbox = builder.get_object('part_advanced_vbox')

            # Ask page
            self.part_ask_heading = builder.get_object('part_ask_heading')
            self.use_device_title = builder.get_object('use_device_title')
            self.use_device_desc = builder.get_object('use_device_desc')
            self.replace_partition = builder.get_object('replace_partition')
            self.replace_partition_title = builder.get_object('replace_partition_title')
            self.replace_partition_desc = builder.get_object('replace_partition_desc')
            self.reuse_partition_title = builder.get_object('reuse_partition_title')
            self.reuse_partition_desc = builder.get_object('reuse_partition_desc')
            self.resize_use_free_title = builder.get_object('resize_use_free_title')
            self.resize_use_free_desc = builder.get_object('resize_use_free_desc')
            self.custom_partitioning_title = builder.get_object('custom_partitioning_title')
            self.custom_partitioning_desc = builder.get_object('custom_partitioning_desc')

            # Ask page accessibility
            import atk
            self.atk_use_device = self.use_device.get_accessible()
            self.atk_use_device_title = self.use_device_title.get_accessible()
            self.atk_use_device_title.add_relationship(atk.RELATION_LABEL_FOR, self.atk_use_device)
            self.atk_use_device.add_relationship(atk.RELATION_LABELLED_BY, self.atk_use_device_title)
            self.atk_replace_partition = self.replace_partition.get_accessible()
            self.atk_replace_partition_title = self.replace_partition_title.get_accessible()
            self.atk_replace_partition_title.add_relationship(atk.RELATION_LABEL_FOR, self.atk_replace_partition)
            self.atk_replace_partition.add_relationship(atk.RELATION_LABELLED_BY, self.atk_replace_partition_title)
            self.atk_reuse_partition = self.reuse_partition.get_accessible()
            self.atk_reuse_partition_title = self.reuse_partition_title.get_accessible()
            self.atk_reuse_partition_title.add_relationship(atk.RELATION_LABEL_FOR, self.atk_reuse_partition)
            self.atk_reuse_partition.add_relationship(atk.RELATION_LABELLED_BY, self.atk_reuse_partition_title)
            self.atk_resize_use_free = self.resize_use_free.get_accessible()
            self.atk_resize_use_free_title = self.resize_use_free_title.get_accessible()
            self.atk_resize_use_free_title.add_relationship(atk.RELATION_LABEL_FOR, self.atk_resize_use_free)
            self.atk_resize_use_free.add_relationship(atk.RELATION_LABELLED_BY, self.atk_resize_use_free_title)
            self.atk_custom_partitioning = self.custom_partitioning.get_accessible()
            self.atk_custom_partitioning_title = self.custom_partitioning_title.get_accessible()
            self.atk_custom_partitioning_title.add_relationship(atk.RELATION_LABEL_FOR, self.atk_custom_partitioning)
            self.atk_custom_partitioning.add_relationship(atk.RELATION_LABELLED_BY, self.atk_custom_partitioning_title)

            # Advanced page
            self.partition_create_mount_combo = builder.get_object('partition_create_mount_combo')
            self.partition_edit_mount_combo = builder.get_object('partition_edit_mount_combo')
            self.partition_create_dialog = builder.get_object('partition_create_dialog')
            self.partition_list_treeview = builder.get_object('partition_list_treeview')
            self.partition_create_type_label = builder.get_object('partition_create_type_label')
            self.partition_create_type_primary = builder.get_object('partition_create_type_primary')
            self.partition_create_type_logical = builder.get_object('partition_create_type_logical')
            self.partition_create_size_spinbutton = builder.get_object('partition_create_size_spinbutton')
            self.partition_create_place_beginning = builder.get_object('partition_create_place_beginning')
            self.partition_create_use_combo = builder.get_object('partition_create_use_combo')
            self.partition_edit_dialog = builder.get_object('partition_edit_dialog')
            self.partition_edit_size_label = builder.get_object('partition_edit_size_label')
            self.partition_edit_size_spinbutton = builder.get_object('partition_edit_size_spinbutton')
            self.partition_edit_use_combo = builder.get_object('partition_edit_use_combo')
            self.partition_edit_format_label = builder.get_object('partition_edit_format_label')
            self.partition_edit_format_checkbutton = builder.get_object('partition_edit_format_checkbutton')
            self.partition_button_new_label = builder.get_object('partition_button_new_label')
            self.partition_button_new = builder.get_object('partition_button_new')
            self.partition_button_edit = builder.get_object('partition_button_edit')
            self.partition_button_delete = builder.get_object('partition_button_delete')
            self.partition_button_undo = builder.get_object('partition_button_undo')
            self.part_advanced_warning_message = builder.get_object('part_advanced_warning_message')
            self.part_advanced_warning_hbox = builder.get_object('part_advanced_warning_hbox')
            self.partition_list_buttonbox = builder.get_object('partition_list_buttonbox')
            self.part_advanced_recalculating_box = builder.get_object('part_advanced_recalculating_box')
            self.part_advanced_recalculating_spinner = builder.get_object('part_advanced_recalculating_spinner')
            self.part_advanced_recalculating_label = builder.get_object('part_advanced_recalculating_label')

            self.partition_bars = {}
            self.segmented_bar_vbox = None
            self.resize_min_size = None
            self.resize_max_size = None
            self.resize_pref_size = None
            self.resize_path = ''
            self.auto_colors = ['8b94ef', 'eeef2f', 'ef8b8b']
            self.extra_options = {}

            self.partition_create_mount_combo.child.set_activates_default(True)
            self.partition_edit_mount_combo.child.set_activates_default(True)

            self.plugin_optional_widgets = [self.page_auto, self.page_advanced]
            self.current_page = self.page_ask

            # Set some parameters that do not change between runs of the plugin
            release = misc.get_release()
            self.partitionbox.set_property('title', release.name)

            # New partition
            self.resizewidget.get_child2().child.set_property('title', release.name)

            # Annoyingly, you can't set packing properties for cell renderers
            # in Glade.
            cell = gtk.CellRendererText()
            self.part_auto_select_drive.pack_start(cell, False)
            self.part_auto_select_drive.add_attribute(cell, 'text', 0)
            cell = gtk.CellRendererText()
            cell.set_property('xalign', 1.0)
            cell.set_property('sensitive', False)
            self.part_auto_select_drive.pack_start(cell, True)
            self.part_auto_select_drive.add_attribute(cell, 'markup', 1)
        except Exception, e:
            self.debug('Could not create partman page: %s', e)
            self.page_ask = None
        self.plugin_widgets = self.page_ask

    def plugin_get_current_page(self):
        if self.current_page == self.page_ask:
            self.plugin_is_install = False
        else:
            self.plugin_is_install = True
        return self.current_page
    
    def configure_wubi_and_reboot(self):
        self.controller.allow_change_step(False)
        device = self.extra_options['wubi']
        import tempfile
        import subprocess
        import shutil
        mount_path = tempfile.mkdtemp()
        try:
            subprocess.check_call(['mount', device, mount_path])
            startup = misc.windows_startup_folder(mount_path)
            shutil.copy('/cdrom/wubi.exe', startup)
            self.controller._wizard.reboot()
        except subprocess.CalledProcessError:
            pass
        finally:
            subprocess.call(['umount', mount_path])
            if os.path.exists(mount_path):
                os.rmdir(mount_path)

    def plugin_on_next_clicked(self):
        reuse = self.reuse_partition.get_active()
        replace = self.replace_partition.get_active()
        resize = self.resize_use_free.get_active()
        custom = self.custom_partitioning.get_active()
        use_device = self.use_device.get_active()
        biggest_free = 'biggest_free' in self.extra_options

        # We already have all that we need from the user.
        done_partitioning = (resize and biggest_free) or reuse or replace

        if self.current_page == self.page_ask and not done_partitioning:
            if custom:
                title = self.custom_partitioning_title.get_text()
            elif resize:
                title = self.resize_use_free_title.get_text()
            elif use_device:
                title = self.use_device_title.get_text()
            self.controller._wizard.page_title.set_markup(
                '<span size="xx-large">%s</span>' % title)
            
            if resize and 'wubi' in self.extra_options:
                self.configure_wubi_and_reboot()
                return True
            elif resize:
                m = self.part_auto_select_drive.get_model()
                m.clear()
                extra_resize = self.extra_options['resize']
                disk_ids = extra_resize.keys()
                disks = self.extra_options['use_device'][1]
                # FIXME: perhaps it makes more sense to store the disk
                # description.
                for disk in disks:
                    key = disks[disk][0].rsplit('/', 1)[1]
                    if key in disk_ids:
                        min_size  = extra_resize[key][1]
                        part_size = extra_resize[key][5]
                        m.append([disk, '<small>%s</small>' %
                                  misc.format_size(part_size - min_size)])
                self.part_auto_select_drive.set_active(0)
                self.initialize_resize_mode()
            elif use_device:
                m = self.part_auto_select_drive.get_model()
                m.clear()
                for disk in self.extra_options['use_device'][1]:
                    m.append([disk, ''])
                self.part_auto_select_drive.set_active(0)
                self.initialize_use_disk_mode()

            if not custom:
                self.current_page = self.page_auto
                self.controller.go_to_page(self.current_page)
                self.controller.toggle_next_button('install_button')
                self.plugin_is_install = True
                return True
            else:
                self.current_page = self.page_advanced
                self.controller.go_to_page(self.current_page)
                self.controller.toggle_next_button('install_button')
                self.plugin_is_install = True
                return False
        else:
            # Return control to partman, which will call
            # get_autopartition_choice and start partitioninging the device.
            if not custom:
                self.controller.switch_to_install_interface()
            return False

    def plugin_on_back_clicked(self):
        if self.current_page == self.page_auto:
            title = self.controller.get_string(self.plugin_title)
            self.controller._wizard.page_title.set_markup(
                '<span size="xx-large">%s</span>' % title)
            self.current_page = self.page_ask
            self.controller.go_to_page(self.current_page)
            # If we arrived at a second partitioning page, then the option
            # selected on the first page would not cause the forward button to
            # be marked as Install Now.
            self.controller.toggle_next_button()
            self.plugin_is_install = False
            return True
        else:
            # If we're on the first page (ask), then we want to go back to
            # prepare. If we're on the advanced page, then we want to go back
            # to the first page (ask).
            return False

    def set_disk_layout(self, layout):
        self.disk_layout = layout

    # Automatic partitioning page

    def get_current_disk_partman_id (self):
        i = self.part_auto_select_drive.get_active_iter()
        if not i:
            return None
        m = self.part_auto_select_drive.get_model()
        val = unicode(m.get_value(i, 0))

        partman_id = self.extra_options['use_device'][1][val][0]
        disk_id = partman_id.rsplit('/', 1)[1]
        return disk_id

    def set_part_auto_hidden_label (self):
        '''Sets the number of partitions in the "X smaller partitions are
        hidden" label.  It subtracts one from the total count to account for
        the partition being resized.'''

        disk_id = self.get_current_disk_partman_id()
        if not disk_id:
            return
        partition_count = len(self.disk_layout[disk_id]) - 1
        if partition_count == 0:
            self.part_auto_hidden_label.set_text('')
        elif partition_count == 1:
            hidden = self.controller.get_string('part_auto_hidden_label_one')
            self.part_auto_hidden_label.set_markup(hidden)
        else:
            hidden = self.controller.get_string('part_auto_hidden_label')
            self.part_auto_hidden_label.set_markup(hidden % partition_count)

    def part_ask_option_changed (self, unused_widget):
        '''The use has selected one of the automatic partitioning options.'''
        about_to_install = False

        if (self.reuse_partition.get_active() or
            self.replace_partition.get_active()):
            about_to_install = True
        elif (self.resize_use_free.get_active() and
            'biggest_free' in self.extra_options):
            about_to_install = True

        if 'wubi' in self.extra_options and self.resize_use_free.get_active():
            self.controller.toggle_next_button('restart_to_continue')
        else:
            if about_to_install:
                self.controller.toggle_next_button('install_button')
            else:
                self.controller.toggle_next_button()
            self.plugin_is_install = about_to_install

    def initialize_resize_mode(self):
        disk_id = self.get_current_disk_partman_id()
        if not disk_id:
            return

        (resize_min_size, resize_max_size, resize_pref_size,
         resize_path, size, fs) = self.extra_options['resize'][disk_id][1:]
        self.resizewidget.set_property('min_size', int(resize_min_size))
        self.resizewidget.set_property('max_size', int(resize_max_size))

        title = misc.find_in_os_prober(resize_path)
        icon = self.resizewidget.get_child1().child
        if not title:
            # This is most likely a partition with some files on it.
            title = self.controller.get_string('ubiquity/text/part_auto_files')
            title = title.replace('${SIZE}', misc.format_size(resize_min_size))
            icon.set_property('icon-name', 'folder')
        else:
            if 'windows' in title.lower():
                PATH = os.environ.get('UBIQUITY_PATH', False) or '/usr/share/ubiquity'
                icon.logo.set_from_file(os.path.join(PATH, 'pixmaps', 'windows_square.png'))
            elif 'buntu' in title.lower():
                icon.set_property('icon-name', 'distributor-logo')
            else:
                icon.set_property('icon-name', 'block-device')

        # TODO See if we can get the filesystem label first in misc.py,
        # caching lookups.
        extra = '%s (%s)' % (resize_path, fs)

        self.resizewidget.get_child1().child.set_property('title', title)
        self.resizewidget.get_child1().child.set_property('extra', extra)
        self.resizewidget.set_property('part_size', size)
        self.resizewidget.set_pref_size(int(resize_pref_size))

        # Set the extra field of the partition being created via resizing.
        try:
            dev, partnum = re.search(r'(.*\D)(\d+)$', resize_path).groups()
            dev = '%s%d' % (dev, int(partnum) + 1)
        except Exception, e:
            dev = 'unknown'
            self.debug('Could not determine new partition number: %s', e)
            self.debug('extra_options: %s' % str(self.extra_options))
        extra = '%s (%s)' % (dev, self.default_filesystem)
        self.resizewidget.get_child2().child.set_property('extra', extra)

        self.partition_container.set_current_page(0)
        allocate = self.controller.get_string('part_auto_allocate_label')
        self.part_auto_allocate_label.set_text(allocate)

    def initialize_use_disk_mode(self):
        '''The selected partman ID will now be completely formatted if the user
        presses next.'''

        disk_id = self.get_current_disk_partman_id()
        if not disk_id:
            return
        # We don't want to hide it as we want to keep its size allocation.
        entire = self.controller.get_string('part_auto_allocate_entire_label')
        self.part_auto_allocate_label.set_text(entire)
        # Set the number of partitions that will be deleted.
        partition_count = len(self.disk_layout[disk_id])
        if partition_count == 0:
            self.part_auto_hidden_label.set_text('')
        elif partition_count == 1:
            deleted = self.controller.get_string('part_auto_deleted_label_one')
            self.part_auto_hidden_label.set_markup(deleted)
        else:
            deleted = self.controller.get_string('part_auto_deleted_label')
            self.part_auto_hidden_label.set_markup(deleted % partition_count)
        self.partition_container.set_current_page(1)
        # Set the filesystem and size of the partition.
        ext = '%s (%s)' % (disk_id.replace('=', '/'), self.default_filesystem)
        self.partitionbox.set_property('extra', ext)
        # Set the size of the disk.
        i = self.part_auto_select_drive.get_active_iter()
        if not i:
            return
        m = self.part_auto_select_drive.get_model()
        val = unicode(m.get_value(i, 0))
        size = self.extra_options['use_device'][1][val][1]
        self.partitionbox.set_size(size)

    def part_auto_select_drive_changed (self, unused_widget):
        self.set_part_auto_hidden_label()
        disk_id = self.get_current_disk_partman_id()
        if not disk_id:
            return
        if self.resize_use_free.get_active():
            self.initialize_resize_mode()
        else:
            self.initialize_use_disk_mode()

    def part_auto_hidden_label_activate_link(self, unused_widget, unused):
        self.custom_partitioning.set_active(True)
        self.controller.go_forward()

    def set_grub_options(self, default):
        import gtk, gobject
        self.bootloader_vbox.show()
        options = misc.grub_options()
        if default.startswith('/'):
            default = os.path.realpath(default)
        l = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        self.grub_device_entry.set_model(l)
        selected = False
        for opt in options:
            i = l.append(opt)
            if opt[0] == default:
                self.grub_device_entry.set_active_iter(i)
                selected = True
        if not selected:
            i = l.append([default, ''])
            self.grub_device_entry.set_active_iter(i)

    def get_grub_choice(self):
        i = self.grub_device_entry.get_active_iter()
        if i:
            return self.grub_device_entry.get_model().get_value(i, 0)
        else:
            self.debug('No active iterator for grub device entry.')
            return misc.grub_default()

    def set_autopartition_heading(self, heading):
        self.part_ask_heading.set_label(heading)

    def set_autopartition_options(self, options, extra_options):
        # TODO Need to select a radio button when resize isn't around.
        self.extra_options = extra_options

        fmt = '<span size="small">%s</span>'
        self.use_device_title.set_label(options['use_device'].title)
        self.use_device_desc.set_markup(fmt % options['use_device'].desc)
        # To give a nice text effect.
        self.use_device_desc.set_sensitive(False)
        self.custom_partitioning_title.set_label(options['manual'].title)
        self.custom_partitioning_desc.set_markup(fmt % options['manual'].desc)
        self.custom_partitioning_desc.set_sensitive(False)

        if 'replace' in options:
            self.replace_partition.show()
            self.replace_partition_title.set_label(options['replace'].title)
            self.replace_partition_desc.set_markup(fmt % options['replace'].desc)
            self.replace_partition_desc.set_sensitive(False)
        else:
            self.replace_partition.hide()

        if 'reuse' in options:
            self.reuse_partition.show()
            self.reuse_partition_title.set_markup(options['reuse'].title)
            self.reuse_partition_desc.set_markup(fmt % options['reuse'].desc)
            self.reuse_partition_desc.set_sensitive(False)
        else:
            self.reuse_partition.hide()

        if 'resize' in options:
            self.resize_use_free.show()
            self.resize_use_free_title.set_label(options['resize'].title)
            self.resize_use_free_desc.set_markup(fmt % options['resize'].desc)
            self.resize_use_free_desc.set_sensitive(False)
        else:
            self.resize_use_free.hide()

        for opt in (self.resize_use_free, self.reuse_partition,
                    self.replace_partition, self.use_device):
            if opt.get_property('visible'):
                opt.set_active(True)
                break

        # Process the default selection
        self.part_ask_option_changed(None)

        # Make sure we're on the autopartitioning page.
        self.current_page = self.page_ask

    def get_autopartition_choice (self):
        if self.reuse_partition.get_active():
            return self.extra_options['reuse'][0][0], None

        if self.replace_partition.get_active():
            return self.extra_options['replace'][0], None

        elif self.custom_partitioning.get_active():
            return self.extra_options['manual'], None

        elif self.resize_use_free.get_active():
            if 'biggest_free' in self.extra_options:
                choice = self.extra_options['biggest_free'][0]
                return choice, None
            else:
                disk_id = self.get_current_disk_partman_id()
                choice = self.extra_options['resize'][disk_id][0]
                return choice, '%s B' % self.resizewidget.get_size()

        elif self.use_device.get_active():
            i = self.part_auto_select_drive.get_active_iter()
            m = self.part_auto_select_drive.get_model()
            disk = m.get_value(i, 0)
            choice = self.extra_options['use_device'][0]
            # Is the encoding necessary?
            return choice, unicode(disk, 'utf-8', 'replace')
        
        else:
            raise AssertionError("Couldn't get autopartition choice")

    # Advanced partitioning page

    def show_page_advanced(self):
        self.current_page = self.page_advanced

    def progress_start(self, progress_title):
        self.partition_list_buttonbox.set_sensitive(False)
        self.part_advanced_recalculating_label.set_text(progress_title)
        self.part_advanced_recalculating_box.show()
        self.part_advanced_recalculating_spinner.start()

    def progress_info(self, progress_info):
        self.part_advanced_recalculating_label.set_text(progress_info)

    def progress_stop(self):
        self.partition_list_buttonbox.set_sensitive(True)
        self.part_advanced_recalculating_spinner.stop()
        self.part_advanced_recalculating_box.hide()

    def partman_column_name (self, unused_column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition:
            # whole disk
            cell.set_property('text', partition['device'])
        elif partition['parted']['fs'] != 'free':
            cell.set_property('text', '  %s' % partition['parted']['path'])
        elif partition['parted']['type'] == 'unusable':
            unusable = self.controller.get_string('partman/text/unusable')
            cell.set_property('text', '  %s' % unusable)
        else:
            # partman uses "FREE SPACE" which feels a bit too SHOUTY for
            # this interface.
            free_space = self.controller.get_string('partition_free_space')
            cell.set_property('text', '  %s' % free_space)

    def partman_column_type (self, unused_column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition or 'method' not in partition:
            if ('parted' in partition and
                partition['parted']['fs'] != 'free' and
                'detected_filesystem' in partition):
                cell.set_property('text', partition['detected_filesystem'])
            else:
                cell.set_property('text', '')
        elif ('filesystem' in partition and
              partition['method'] in ('format', 'keep')):
            cell.set_property('text', partition['acting_filesystem'])
        else:
            cell.set_property('text', partition['method'])

    @plugin.only_this_page
    def partman_column_mountpoint (self, unused_column, cell, model, iterator):
        partition = model[iterator][1]
        mountpoint = self.controller.dbfilter.get_current_mountpoint(partition)
        if mountpoint is None:
            mountpoint = ''
        cell.set_property('text', mountpoint)

    def partman_column_format (self, unused_column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition:
            cell.set_property('visible', False)
            cell.set_property('active', False)
            cell.set_property('activatable', False)
        elif 'method' in partition:
            cell.set_property('visible', True)
            cell.set_property('active', partition['method'] == 'format')
            cell.set_property('activatable', 'can_activate_format' in partition)
        else:
            cell.set_property('visible', True)
            cell.set_property('active', False)
            cell.set_property('activatable', False)

    @plugin.only_this_page
    def partman_column_format_toggled (self, unused_cell, path, user_data):
        if not self.controller.allowed_change_step():
            return
        model = user_data
        devpart = model[path][0]
        partition = model[path][1]
        if 'id' not in partition or 'method' not in partition:
            return
        self.controller.allow_change_step(False)
        self.controller.dbfilter.edit_partition(devpart, fmt='dummy')

    def partman_column_size (self, unused_column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition:
            cell.set_property('text', '')
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['parted']['size']) / 1000000
            cell.set_property('text', '%d MB' % size_mb)

    def partman_column_used (self, unused_column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition or partition['parted']['fs'] == 'free':
            cell.set_property('text', '')
        elif 'resize_min_size' not in partition:
            unknown = self.controller.get_string('partition_used_unknown')
            cell.set_property('text', unknown)
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['resize_min_size']) / 1000000
            cell.set_property('text', '%d MB' % size_mb)

    @plugin.only_this_page
    def partman_popup (self, widget, event):
        import gtk
        if not self.controller.allowed_change_step():
            return

        model, iterator = widget.get_selection().get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]

        partition_list_menu = gtk.Menu()
        for action in self.controller.dbfilter.get_actions(devpart, partition):
            if action == 'new_label':
                new_label_item = gtk.MenuItem(
                    self.controller.get_string('partition_button_new_label'))
                new_label_item.connect(
                    'activate', self.on_partition_list_new_label_activate)
                partition_list_menu.append(new_label_item)
            elif action == 'new':
                new_item = gtk.MenuItem(
                    self.controller.get_string('partition_button_new'))
                new_item.connect(
                    'activate', self.on_partition_list_new_activate)
                partition_list_menu.append(new_item)
            elif action == 'edit':
                edit_item = gtk.MenuItem(
                    self.controller.get_string('partition_button_edit'))
                edit_item.connect(
                    'activate', self.on_partition_list_edit_activate)
                partition_list_menu.append(edit_item)
            elif action == 'delete':
                delete_item = gtk.MenuItem(
                    self.controller.get_string('partition_button_delete'))
                delete_item.connect(
                    'activate', self.on_partition_list_delete_activate)
                partition_list_menu.append(delete_item)
        if partition_list_menu.get_children():
            partition_list_menu.append(gtk.SeparatorMenuItem())
        undo_item = gtk.MenuItem(
            self.controller.get_string('partition_button_undo'))
        undo_item.connect('activate', self.on_partition_list_undo_activate)
        partition_list_menu.append(undo_item)
        partition_list_menu.show_all()

        if event:
            button = event.button
            time = event.get_time()
        else:
            button = 0
            time = 0
        partition_list_menu.popup(None, None, None, button, time)

    @plugin.only_this_page
    def partman_create_dialog (self, devpart, partition):
        import gtk, gobject
        if not self.controller.allowed_change_step():
            return

        self.partition_create_dialog.show_all()

        # TODO cjwatson 2006-11-01: Because partman doesn't use a question
        # group for these, we have to figure out in advance whether each
        # question is going to be asked.

        if partition['parted']['type'] == 'pri/log':
            # Is there already a primary partition?
            model = self.partition_list_treeview.get_model()
            for otherpart in [row[1] for row in model]:
                if (otherpart['dev'] == partition['dev'] and
                    'id' in otherpart and
                    otherpart['parted']['type'] == 'primary'):
                    self.partition_create_type_logical.set_active(True)
                    break
            else:
                self.partition_create_type_primary.set_active(True)
        else:
            self.partition_create_type_label.hide()
            self.partition_create_type_primary.hide()
            self.partition_create_type_logical.hide()

        # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
        # partman expects.
        max_size_mb = int(partition['parted']['size']) / 1000000
        self.partition_create_size_spinbutton.set_adjustment(
            gtk.Adjustment(value=max_size_mb, upper=max_size_mb,
                           step_incr=1, page_incr=100))
        self.partition_create_size_spinbutton.set_value(max_size_mb)

        self.partition_create_place_beginning.set_active(True)

        self.partition_create_use_combo.clear()
        renderer = gtk.CellRendererText()
        self.partition_create_use_combo.pack_start(renderer)
        self.partition_create_use_combo.add_attribute(renderer, 'text', 2)
        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                                   gobject.TYPE_STRING)
        for method, name, description in self.controller.dbfilter.use_as(devpart, True):
            list_store.append([method, name, description])
        self.partition_create_use_combo.set_model(list_store)
        if list_store.get_iter_first():
            self.partition_create_use_combo.set_active(0)

        list_store = gtk.ListStore(gobject.TYPE_STRING)
        for mp, choice_c, choice in self.controller.dbfilter.default_mountpoint_choices():
            list_store.append([mp])
        self.partition_create_mount_combo.set_model(list_store)
        if self.partition_create_mount_combo.get_text_column() == -1:
            self.partition_create_mount_combo.set_text_column(0)
        self.partition_create_mount_combo.child.set_text('')

        response = self.partition_create_dialog.run()
        self.partition_create_dialog.hide()

        if (response == gtk.RESPONSE_OK):
            if partition['parted']['type'] == 'primary':
                prilog = PARTITION_TYPE_PRIMARY
            elif partition['parted']['type'] == 'logical':
                prilog = PARTITION_TYPE_LOGICAL
            elif partition['parted']['type'] == 'pri/log':
                if self.partition_create_type_primary.get_active():
                    prilog = PARTITION_TYPE_PRIMARY
                else:
                    prilog = PARTITION_TYPE_LOGICAL

            if self.partition_create_place_beginning.get_active():
                place = PARTITION_PLACE_BEGINNING
            else:
                place = PARTITION_PLACE_END

            method_iter = self.partition_create_use_combo.get_active_iter()
            if method_iter is None:
                method = None
            else:
                model = self.partition_create_use_combo.get_model()
                method = model.get_value(method_iter, 1)

            mountpoint = self.partition_create_mount_combo.child.get_text()

            self.controller.allow_change_step(False)
            self.controller.dbfilter.create_partition(
                devpart,
                str(self.partition_create_size_spinbutton.get_value()),
                prilog, place, method, mountpoint)

    @plugin.only_this_page
    def on_partition_create_use_combo_changed (self, combobox):
        model = combobox.get_model()
        iterator = combobox.get_active_iter()
        # If the selected method isn't a filesystem, then selecting a mount
        # point makes no sense.
        if iterator is None or model[iterator][0] != 'filesystem':
            self.partition_create_mount_combo.child.set_text('')
            self.partition_create_mount_combo.set_sensitive(False)
        else:
            self.partition_create_mount_combo.set_sensitive(True)
            mount_model = self.partition_create_mount_combo.get_model()
            if mount_model is not None:
                fs = model[iterator][1]
                mount_model.clear()
                for mp, choice_c, choice in \
                    self.controller.dbfilter.default_mountpoint_choices(fs):
                    mount_model.append([mp])

    @plugin.only_this_page
    def partman_edit_dialog (self, devpart, partition):
        import gtk, gobject
        if not self.controller.allowed_change_step():
            return

        self.partition_edit_dialog.show_all()

        current_size = None
        if ('can_resize' not in partition or not partition['can_resize'] or
            'resize_min_size' not in partition or
            'resize_max_size' not in partition):
            self.partition_edit_size_label.hide()
            self.partition_edit_size_spinbutton.hide()
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            min_size_mb = int(partition['resize_min_size']) / 1000000
            cur_size_mb = int(partition['parted']['size']) / 1000000
            max_size_mb = int(partition['resize_max_size']) / 1000000
            # Bad things happen if the current size is out of bounds.
            min_size_mb = min(min_size_mb, cur_size_mb)
            max_size_mb = max(cur_size_mb, max_size_mb)
            self.partition_edit_size_spinbutton.set_adjustment(
                gtk.Adjustment(value=cur_size_mb, lower=min_size_mb,
                               upper=max_size_mb,
                               step_incr=1, page_incr=100))
            self.partition_edit_size_spinbutton.set_value(cur_size_mb)
            current_size = str(self.partition_edit_size_spinbutton.get_value())

        self.partition_edit_use_combo.clear()
        renderer = gtk.CellRendererText()
        self.partition_edit_use_combo.pack_start(renderer)
        self.partition_edit_use_combo.add_attribute(renderer, 'text', 1)
        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        for script, arg, option in partition['method_choices']:
            list_store.append([arg, option])
        self.partition_edit_use_combo.set_model(list_store)
        current_method = self.controller.dbfilter.get_current_method(partition)
        if current_method:
            iterator = list_store.get_iter_first()
            while iterator:
                if list_store[iterator][0] == current_method:
                    self.partition_edit_use_combo.set_active_iter(iterator)
                    break
                iterator = list_store.iter_next(iterator)

        if 'id' not in partition:
            self.partition_edit_format_label.hide()
            self.partition_edit_format_checkbutton.hide()
            current_format = False
        elif 'method' in partition:
            self.partition_edit_format_label.show()
            self.partition_edit_format_checkbutton.show()
            self.partition_edit_format_checkbutton.set_sensitive(
                'can_activate_format' in partition)
            current_format = (partition['method'] == 'format')
        else:
            self.partition_edit_format_label.show()
            self.partition_edit_format_checkbutton.show()
            self.partition_edit_format_checkbutton.set_sensitive(False)
            current_format = False
        self.partition_edit_format_checkbutton.set_active(current_format)

        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        if 'mountpoint_choices' in partition:
            for mp, choice_c, choice in partition['mountpoint_choices']:
                list_store.append([mp, choice])
        self.partition_edit_mount_combo.set_model(list_store)
        if self.partition_edit_mount_combo.get_text_column() == -1:
            self.partition_edit_mount_combo.set_text_column(0)
        current_mountpoint = self.controller.dbfilter.get_current_mountpoint(partition)
        if current_mountpoint is not None:
            self.partition_edit_mount_combo.child.set_text(current_mountpoint)
            iterator = list_store.get_iter_first()
            while iterator:
                if list_store[iterator][0] == current_mountpoint:
                    self.partition_edit_mount_combo.set_active_iter(iterator)
                    break
                iterator = list_store.iter_next(iterator)

        response = self.partition_edit_dialog.run()
        self.partition_edit_dialog.hide()

        if (response == gtk.RESPONSE_OK):
            size = None
            if current_size is not None:
                size = str(self.partition_edit_size_spinbutton.get_value())

            method_iter = self.partition_edit_use_combo.get_active_iter()
            if method_iter is None:
                method = None
            else:
                model = self.partition_edit_use_combo.get_model()
                method = model.get_value(method_iter, 0)

            fmt = self.partition_edit_format_checkbutton.get_active()

            mountpoint = self.partition_edit_mount_combo.child.get_text()

            if (current_size is not None and size is not None and
                current_size == size):
                size = None
            if method == current_method:
                method = None
            if fmt == current_format:
                fmt = None
            if mountpoint == current_mountpoint:
                mountpoint = None

            if (size is not None or method is not None or fmt is not None or
                mountpoint is not None):
                self.controller.allow_change_step(False)
                edits = {'size': size, 'method': method,
                         'mountpoint': mountpoint}
                if fmt is not None:
                    edits['fmt'] = 'dummy'
                self.controller.dbfilter.edit_partition(devpart, **edits)

    @plugin.only_this_page
    def on_partition_edit_use_combo_changed (self, combobox):
        model = combobox.get_model()
        iterator = combobox.get_active_iter()
        # If the selected method isn't a filesystem, then selecting a mount
        # point makes no sense. TODO cjwatson 2007-01-31: Unfortunately we
        # have to hardcode the list of known filesystems here.
        known_filesystems = ('ext4', 'ext3', 'ext2',
                             'btrfs', 'reiserfs', 'jfs', 'xfs',
                             'fat16', 'fat32', 'ntfs', 'uboot')
        if iterator is None or model[iterator][0] not in known_filesystems:
            self.partition_edit_mount_combo.child.set_text('')
            self.partition_edit_mount_combo.set_sensitive(False)
            self.partition_edit_format_checkbutton.set_sensitive(False)
        else:
            self.partition_edit_mount_combo.set_sensitive(True)
            self.partition_edit_format_checkbutton.set_sensitive(True)
            mount_model = self.partition_edit_mount_combo.get_model()
            if mount_model is not None:
                fs = model[iterator][0]
                mount_model.clear()
                for mp, choice_c, choice in \
                    self.controller.dbfilter.default_mountpoint_choices(fs):
                    mount_model.append([mp, choice])

    def on_partition_list_treeview_button_press_event (self, widget, event):
        import gtk
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            path_at_pos = widget.get_path_at_pos(int(event.x), int(event.y))
            if path_at_pos is not None:
                selection = widget.get_selection()
                selection.unselect_all()
                selection.select_path(path_at_pos[0])

            self.partman_popup(widget, event)
            return True

    @plugin.only_this_page
    def on_partition_list_treeview_key_press_event (self, widget, event):
        import gtk
        if event.type != gtk.gdk.KEY_PRESS:
            return False

        if event.keyval == gtk.keysyms.Delete:
            devpart, partition = self.partition_list_get_selection()
            for action in self.controller.dbfilter.get_actions(devpart, partition):
                if action == 'delete':
                    self.on_partition_list_delete_activate(widget)
                    return True

        return False

    def on_partition_list_treeview_popup_menu (self, widget):
        self.partman_popup(widget, None)
        return True

    @plugin.only_this_page
    def on_partition_list_treeview_selection_changed (self, selection):
        self.partition_button_new_label.set_sensitive(False)
        self.partition_button_new.set_sensitive(False)
        self.partition_button_edit.set_sensitive(False)
        self.partition_button_delete.set_sensitive(False)

        model, iterator = selection.get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]
            if 'id' not in partition:
                dev = partition['device']
            else:
                dev = partition['parent']
            for p in self.partition_bars.itervalues():
                p.hide()
            self.partition_bars[dev].show()
        for action in self.controller.dbfilter.get_actions(devpart, partition):
            if action == 'new_label':
                self.partition_button_new_label.set_sensitive(True)
            elif action == 'new':
                self.partition_button_new.set_sensitive(True)
            elif action == 'edit':
                self.partition_button_edit.set_sensitive(True)
            elif action == 'delete':
                self.partition_button_delete.set_sensitive(True)
        self.partition_button_undo.set_sensitive(True)

    @plugin.only_this_page
    def on_partition_list_treeview_row_activated (self, treeview,
                                                  path, unused_view_column):
        if not self.controller.allowed_change_step():
            return
        model = treeview.get_model()
        try:
            devpart = model[path][0]
            partition = model[path][1]
        except (IndexError, KeyError):
            return

        if 'id' not in partition:
            # Are there already partitions on this disk? If so, don't allow
            # activating the row to offer to create a new partition table,
            # to avoid mishaps.
            for otherpart in [row[1] for row in model]:
                if otherpart['dev'] == partition['dev'] and 'id' in otherpart:
                    break
            else:
                self.controller.allow_change_step(False)
                self.controller.dbfilter.create_label(devpart)
        elif partition['parted']['fs'] == 'free':
            if 'can_new' in partition and partition['can_new']:
                self.partman_create_dialog(devpart, partition)
        else:
            self.partman_edit_dialog(devpart, partition)

    def partition_list_get_selection (self):
        model, iterator = self.partition_list_treeview.get_selection().get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]
        return (devpart, partition)

    @plugin.only_this_page
    def on_partition_list_new_label_activate (self, unused_widget):
        if not self.controller.allowed_change_step():
            return
        self.controller.allow_change_step(False)
        devpart, partition = self.partition_list_get_selection()
        self.controller.dbfilter.create_label(devpart)

    def on_partition_list_new_activate (self, unused_widget):
        devpart, partition = self.partition_list_get_selection()
        self.partman_create_dialog(devpart, partition)

    def on_partition_list_edit_activate (self, unused_widget):
        devpart, partition = self.partition_list_get_selection()
        self.partman_edit_dialog(devpart, partition)

    @plugin.only_this_page
    def on_partition_list_delete_activate (self, unused_widget):
        if not self.controller.allowed_change_step():
            return
        self.controller.allow_change_step(False)
        devpart, partition = self.partition_list_get_selection()
        self.controller.dbfilter.delete_partition(devpart)

    @plugin.only_this_page
    def on_partition_list_undo_activate (self, unused_widget):
        if not self.controller.allowed_change_step():
            return
        self.controller.allow_change_step(False)
        self.controller.dbfilter.undo()

    def update_partman (self, disk_cache, partition_cache, cache_order):
        import gtk, gobject
        from ubiquity import segmented_bar
        if self.partition_bars:
            for p in self.partition_bars.itervalues():
                self.segmented_bar_vbox.remove(p)
                del p

        partition_tree_model = self.partition_list_treeview.get_model()
        if partition_tree_model is None:
            partition_tree_model = gtk.ListStore(gobject.TYPE_STRING,
                                                 gobject.TYPE_PYOBJECT)

            cell_name = gtk.CellRendererText()
            column_name = gtk.TreeViewColumn(
                self.controller.get_string('partition_column_device'), cell_name)
            column_name.set_cell_data_func(cell_name, self.partman_column_name)
            column_name.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_name)

            cell_type = gtk.CellRendererText()
            column_type = gtk.TreeViewColumn(
                self.controller.get_string('partition_column_type'), cell_type)
            column_type.set_cell_data_func(cell_type, self.partman_column_type)
            column_type.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_type)

            cell_mountpoint = gtk.CellRendererText()
            column_mountpoint = gtk.TreeViewColumn(
                self.controller.get_string('partition_column_mountpoint'),
                cell_mountpoint)
            column_mountpoint.set_cell_data_func(
                cell_mountpoint, self.partman_column_mountpoint)
            column_mountpoint.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_mountpoint)

            cell_format = gtk.CellRendererToggle()
            column_format = gtk.TreeViewColumn(
                self.controller.get_string('partition_column_format'), cell_format)
            column_format.set_cell_data_func(
                cell_format, self.partman_column_format)
            column_format.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            cell_format.connect("toggled", self.partman_column_format_toggled,
                                partition_tree_model)
            self.partition_list_treeview.append_column(column_format)

            cell_size = gtk.CellRendererText()
            column_size = gtk.TreeViewColumn(
                self.controller.get_string('partition_column_size'), cell_size)
            column_size.set_cell_data_func(cell_size, self.partman_column_size)
            column_size.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_size)

            cell_used = gtk.CellRendererText()
            column_used = gtk.TreeViewColumn(
                self.controller.get_string('partition_column_used'), cell_used)
            column_used.set_cell_data_func(cell_used, self.partman_column_used)
            column_used.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_used)

            self.partition_list_treeview.set_model(partition_tree_model)

            selection = self.partition_list_treeview.get_selection()
            selection.connect(
                'changed', self.on_partition_list_treeview_selection_changed)
        else:
            # TODO cjwatson 2006-08-31: inefficient, but will do for now
            partition_tree_model.clear()

        partition_bar = None
        dev = ''
        total_size = {}
        i = 0
        if not self.segmented_bar_vbox:
            sw = gtk.ScrolledWindow()
            self.segmented_bar_vbox = gtk.VBox()
            sw.add_with_viewport(self.segmented_bar_vbox)
            sw.child.set_shadow_type(gtk.SHADOW_NONE)
            sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
            sw.show_all()
            self.part_advanced_vbox.pack_start(sw, expand=False)
            self.part_advanced_vbox.reorder_child(sw, 0)

        for item in cache_order:
            if item in disk_cache:
                partition_tree_model.append([item, disk_cache[item]])
                dev = disk_cache[item]['device']
                self.partition_bars[dev] = segmented_bar.SegmentedBar()
                partition_bar = self.partition_bars[dev]
                self.segmented_bar_vbox.add(partition_bar)
                total_size[dev] = 0.0
            else:
                partition_tree_model.append([item, partition_cache[item]])
                size = int(partition_cache[item]['parted']['size'])
                total_size[dev] = total_size[dev] + size
                fs = partition_cache[item]['parted']['fs']
                path = partition_cache[item]['parted']['path'].replace('/dev/','')
                if fs == 'free':
                    c = partition_bar.remainder_color
                    txt = self.controller.get_string('partition_free_space')
                else:
                    i = (i + 1) % len(self.auto_colors)
                    c = self.auto_colors[i]
                    txt = '%s (%s)' % (path, fs)
                partition_bar.add_segment_rgb(txt, size, c)
        sel = self.partition_list_treeview.get_selection()
        if sel.count_selected_rows() == 0:
            sel.select_path(0)
        # make sure we're on the advanced partitioning page
        self.show_page_advanced()

    def installation_medium_mounted (self, message):
        self.part_advanced_warning_message.set_text(message)
        self.part_advanced_warning_hbox.show_all()

class PageKde(PageBase):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_partition'
    plugin_is_install = True

    def __init__(self, controller, *args, **kwargs):
        PageBase.__init__(self)
        self.controller = controller

        from ubiquity.frontend.kde_components.PartAuto import PartAuto
        from ubiquity.frontend.kde_components.PartMan import PartMan

        self.partAuto = PartAuto(self.controller)
        self.partMan = PartMan(self.controller)

        self.page = self.partAuto
        self.page_advanced = self.partMan
        self.plugin_widgets = self.page
        self.plugin_optional_widgets = self.page_advanced
        self.current_page = self.page

    def show_page_advanced(self):
        self.current_page = self.page_advanced

    # provides the basic disk layout
    def set_disk_layout(self, layout):
        self.disk_layout = layout
        self.partAuto.setDiskLayout(layout)

    def set_grub_options(self, default):
        options = misc.grub_options()
        if default.startswith('/'):
            default = os.path.realpath(default)
        self.partMan.setGrubOptions(options, default)

    def get_grub_choice(self):
        choice = self.partMan.getGrubChoice()
        if choice:
            return choice
        else:
            return misc.grub_default()

    def set_autopartition_heading(self, heading):
        pass

    def set_autopartition_options(self, options, extra_options):
        use_device = self.controller.dbfilter.some_device_desc
        resize_choice = self.controller.dbfilter.resize_desc
        manual_choice = extra_options['manual']

        self.partAuto.setupChoices(None, extra_options,
                                   resize_choice, manual_choice,
                                   None, use_device)

        self.current_page = self.page

    def get_autopartition_choice (self):
        return self.partAuto.getChoice()

    def update_partman (self, disk_cache, partition_cache, cache_order):
        self.partMan.update(disk_cache, partition_cache, cache_order)
        # make sure we're on the advanced partitioning page
        self.show_page_advanced()

    def plugin_get_current_page(self):
        return self.current_page

class PageNoninteractive(PageBase):
    def set_part_page(self, p):
        pass

PARTITION_TYPE_PRIMARY = 0
PARTITION_TYPE_LOGICAL = 1

PARTITION_PLACE_BEGINNING = 0
PARTITION_PLACE_END = 1

class PartmanOptionError(LookupError):
    pass

class Page(plugin.Plugin):
    def prepare(self):
        self.some_device_desc = ''
        self.resize_desc = ''
        self.manual_desc = ''
        with misc.raised_privileges():
            # If an old parted_server is still running, clean it up.
            if os.path.exists('/var/run/parted_server.pid'):
                try:
                    pidline = open('/var/run/parted_server.pid').readline()
                    pidline = pidline.strip()
                    pid = int(pidline)
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
                osextras.unlink_force('/var/run/parted_server.pid')

            # Force autopartitioning to be re-run.
            shutil.rmtree('/var/lib/partman', ignore_errors=True)
        self.thaw_choices('choose_partition')
        self.thaw_choices('active_partition')

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
        self.description_cache = {}
        self.local_progress = False

        self.install_bootloader = False
        if (self.db.get('ubiquity/install_bootloader') == 'true' and
                'UBIQUITY_NO_BOOTLOADER' not in os.environ):
            arch, subarch = archdetect()
            if arch in ('amd64', 'i386'):
                self.install_bootloader = True

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
                     '^partman-uboot/mountpoint$',
                     '^partman/exception_handler$',
                     '^partman/exception_handler_note$',
                     '^partman/unmount_active$',
                     '^partman/installation_medium_mounted$',
                     'type:boolean',
                     'ERROR',
                     'PROGRESS']
        # TODO: It would be neater to use a wrapper script.
        return (['sh', '-c',
                 '/usr/share/ubiquity/activate-dmraid && /bin/partman'],
                questions, {'PARTMAN_NO_COMMIT': '1', 'PARTMAN_SNOOP': '1'})

    def snoop(self):
        """Read the partman snoop file hack, returning a list of tuples
        mapping from keys to displayed options. (We use a list of tuples
        because this preserves ordering and is reasonably fast to convert to
        a dictionary.)"""

        options = []
        try:
            snoop = open('/var/lib/partman/snoop')
            for line in snoop:
                line = unicode(line.rstrip('\n'), 'utf-8', 'replace')
                fields = line.split('\t', 1)
                if len(fields) == 2:
                    (key, option) = fields
                    options.append((key, option))
                    continue
            snoop.close()
        except IOError:
            pass
        return options

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
            raise PartmanOptionError("%s should have %s (%s) option" %
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

    def description(self, question):
        # We call this quite a lot on a small number of templates that never
        # change, so add a caching layer.
        try:
            return self.description_cache[question]
        except KeyError:
            description = plugin.Plugin.description(self, question)
            self.description_cache[question] = description
            return description

    def method_description(self, method):
        try:
            question = None
            if method == 'swap':
                question = 'partman/method_long/swap'
            elif method == 'efi':
                question = 'partman-efi/text/efi'
            elif method == 'newworld':
                question = 'partman/method_long/newworld'
            elif method == 'biosgrub':
                question = 'partman/method_long/biosgrub'
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

    def use_as(self, devpart, create):
        """Yields the possible methods that a partition may use.

        If create is True, then only list methods usable on new partitions."""

        # TODO cjwatson 2006-11-01: This is a particular pain; we can't find
        # out the real list of possible uses from partman until after the
        # partition has been created, so we have to partially hardcode this.

        for method in self.subdirectories('/lib/partman/choose_method'):
            if method == 'filesystem':
                for fs in self.scripts('/lib/partman/valid_filesystems'):
                    if fs == 'ntfs':
                        if not create and devpart in self.partition_cache:
                            partition = self.partition_cache[devpart]
                            if ('detected_filesystem' in partition and
                                partition['detected_filesystem'] == 'ntfs'):
                                yield (method, fs,
                                       self.filesystem_description(fs))
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
            elif method == 'biosgrub':
                # TODO cjwatson 2009-09-03: Quick kludge, since only GPT
                # supports this method at the moment. Maybe it would be
                # better to fetch VALID_FLAGS for each partition while
                # building the cache?
                dev = self.split_devpart(devpart)[0]
                if dev is not None:
                    dev = '%s/%s' % (parted_server.devices, dev)
                    if (dev in self.disk_cache and
                        'label' in self.disk_cache[dev] and
                        self.disk_cache[dev]['label'] == 'gpt'):
                        yield (method, method, self.method_description(method))
            else:
                yield (method, method, self.method_description(method))

    def default_mountpoint_choices(self, fs='ext4'):
        """Yields the possible mountpoints for a partition."""

        # We can't find out the real list of possible mountpoints from
        # partman until after the partition has been created, but we can at
        # least fish it out of the appropriate debconf template rather than
        # having to hardcode it.
        # (Actually, getting it from partman tends to be unacceptably slow
        # anyway.)

        if fs in ('fat16', 'fat32', 'ntfs'):
            question = 'partman-basicfilesystems/fat_mountpoint'
        elif fs == 'uboot':
            question = 'partman-uboot/mountpoint'
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

    def build_free(self, devpart):
        partition = self.partition_cache[devpart]
        if partition['parted']['fs'] == 'free':
            self.debug('Partman: %s is free space', devpart)
            # The alternative is descending into
            # partman/free_space and checking for a
            # 'new' script.  This is quicker.
            partition['can_new'] = partition['parted']['type'] in \
                ('primary', 'logical', 'pri/log')
            return True
        else:
            return False

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
                elif key == 'RAWPREFSIZE':
                    partition['resize_pref_size'] = int(value)
                elif key == 'RAWMAXSIZE':
                    partition['resize_max_size'] = int(value)
            if key == 'RAWMINSIZE':
                self.resize_min_size = int(value)
            elif key == 'RAWPREFSIZE':
                self.resize_pref_size = int(value)
            elif key == 'RAWMAXSIZE':
                self.resize_max_size = int(value)
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
        return plugin.Plugin.error(self, priority, question)

    @misc.raise_privileges
    def freeze_choices(self, menu):
        """Stop recalculating choices for a given menu. This is used to
        improve performance while rebuilding the cache. Be careful not to
        use preseed_as_c or similar while choices are frozen, as the current
        set of choices may not be valid; you must cache whatever you need
        before calling this method."""
        self.debug('Partman: Freezing choices for %s', menu)
        open('/lib/partman/%s/no_show_choices' % menu, 'w').close

    @misc.raise_privileges
    def thaw_choices(self, menu):
        """Reverse the effects of freeze_choices."""
        self.debug('Partman: Thawing choices for %s', menu)
        osextras.unlink_force('/lib/partman/%s/no_show_choices' % menu)

    def tidy_update_partitions(self):
        """Tidy up boring entries from the start of update_partitions."""
        while self.update_partitions:
            devpart = self.update_partitions[0]
            if devpart not in self.partition_cache:
                self.debug('Partman: %s not found in cache', devpart)
            elif self.build_free(devpart):
                pass
            else:
                break
            del self.update_partitions[0]
            self.progress_step('', 1)

    def maybe_thaw_choose_partition(self):
        # partman/choose_partition is special; it's the main control point
        # for building the partition cache.  If we're freezing choices (a
        # performance optimisation) while building the cache, we need to
        # make sure that we thaw them just before the last time we return to
        # choose_partition.  Otherwise, the first manual operation after
        # that may fail because we don't have enough information to preseed
        # choose_partition properly.
        if self.__state[-1][0] == 'partman/choose_partition':
            self.tidy_update_partitions()
            if not self.update_partitions:
                self.thaw_choices('choose_partition')

    def calculate_reuse_option(self):
        '''Takes the current Ubuntu version on disk and the release we're about
        to install as parameters.'''

        if self.db.get('ubiquity/online') != 'true':
            self.debug('Not online, so not showing the upgrade option.')
            return None
        # TODO: verify that ubuntu is the same partition as one of the ones
        #       offered in the reuse options.
        release = misc.get_release()
        if 'reuse' in self.extra_options:
            reuse = self.extra_options['reuse']
            if len(reuse) == 1:
                ubuntu = misc.find_in_os_prober(reuse[0][1])
                # TODO: come up with a better version check than this by using
                # SUBST with DISTRIB_ID and DISTRIB_RELEASE in partman-auto.
                # FIXME: this currently breaks as we now strip out "(11.04)".
                if '(%s)' % release.version in ubuntu:
                    # "Windows (or Mac, ...) and the current version of Ubuntu
                    # are present" case
                    q = 'ubiquity/partitioner/ubuntu_reinstall'
                    self.db.subst(q, 'CURDISTRO', ubuntu)
                    title = self.description(q)
                    desc = self.extended_description(q)
                    return PartitioningOption(title, desc)
                else:
                    # "Windows (or Mac, ...) and an older version of Ubuntu are
                    # present" case
                    # TODO: Verify that the version is in fact older.
                    q = 'ubiquity/partitioner/ubuntu_upgrade'
                    self.db.subst(q, 'CURDISTRO', ubuntu)
                    self.db.subst(q, 'VER', release.version)
                    title = self.description(q)
                    desc = self.extended_description(q)
                    return PartitioningOption(title, desc)
        return None

    def calculate_autopartitioning_heading(self, operating_systems,
                                           has_ubuntu):
        os_count = len(operating_systems)
        if os_count == 0:
            q = 'ubiquity/partitioner/heading_no_detected'
            return self.extended_description(q)
        if os_count == 1:
            q = 'ubiquity/partitioner/heading_one'
            self.db.subst(q, 'OS', operating_systems[0])
            return self.extended_description(q)
        elif os_count == 2 and has_ubuntu:
            q = 'ubiquity/partitioner/heading_dual'
            self.db.subst(q, 'OS1', operating_systems[0])
            self.db.subst(q, 'OS2', operating_systems[1])
            return self.extended_description(q)
        else:
            q = 'ubiquity/partitioner/heading_multiple'
            return self.extended_description(q)

    def calculate_operating_systems(self, layout):
        # Get your #2 pencil ready, it's time to crunch some numbers.
        operating_systems = []
        for disk in layout:
            for partition in layout[disk]:
                system = misc.find_in_os_prober(partition.device)
                if system and system != 'swap':
                    if not system.startswith('Windows Recovery'):
                        operating_systems.append(system)
        ubuntu_systems = filter(lambda x: x.lower().find('buntu') != -1,
                                operating_systems)
        return (operating_systems, ubuntu_systems)

    def calculate_autopartitioning_options(self, operating_systems,
                                           ubuntu_systems):
        '''
        There are six possibilities we have to consider:
        - Just Windows (or Mac, ...) is present
        - An older version of Ubuntu is present
        - There are no operating systems present
        - Windows (or Mac, ...) and an older version of Ubuntu are present
        - Windows (or Mac, ...) and the current version of Ubuntu are present
        - There are multiple operating systems present

        We leave ordering and providing icons for each option to the frontend,
        since each option falls under a specific partman-auto operation of a
        finite set.
        '''
        options = {}
        release = misc.get_release()
        os_count = len(operating_systems)
        wubi_option = 'wubi' in self.extra_options

        if wubi_option:
            pass
        elif ('resize' in self.extra_options and
              'biggest_free' in self.extra_options):
                self.debug('Partman: dropping resize option.')
                del self.extra_options['resize']

        resize_option = ('resize' in self.extra_options or
                         'biggest_free' in self.extra_options)

        # We always have the manual partitioner, and it always has the same
        # title and description.
        q = 'ubiquity/partitioner/advanced'
        self.db.subst(q, 'DISTRO', release.name)
        title = self.description(q)
        desc = self.extended_description(q)
        options['manual'] = PartitioningOption(title, desc)

        if os_count == 0:
            # "There are no operating systems present" case
            q = 'ubiquity/partitioner/no_systems_format'
            self.db.subst(q, 'DISTRO', release.name)
            title = self.description(q)
            desc = self.extended_description(q)
            opt = PartitioningOption(title, desc)
            options['use_device'] = opt
        elif os_count == 1:
            system = operating_systems[0]
            if len(ubuntu_systems) == 1:
                # "An older version of Ubuntu is present" case
                q = 'ubiquity/partitioner/ubuntu_format'
                self.db.subst(q, 'CURDISTRO', system)
                title = self.description(q)
                desc = self.extended_description(q)
                opt = PartitioningOption(title, desc)
                options['use_device'] = opt

                if wubi_option:
                    # We don't have a Wubi-like solution for Ubuntu yet (though
                    # wubi_option is also a check for ntfs).
                    pass
                elif resize_option:
                    q = 'ubiquity/partitioner/ubuntu_resize'
                    self.db.subst(q, 'DISTRO', release.name)
                    self.db.subst(q, 'VER', release.version)
                    self.db.subst(q, 'CURDISTRO', system)
                    title = self.description(q)
                    desc = self.extended_description(q)
                    opt = PartitioningOption(title, desc)
                    options['resize'] = opt

                reuse = self.calculate_reuse_option()
                if reuse is not None:
                    options['reuse'] = reuse
            else:
                # "Just Windows (or Mac, ...) is present" case
                q = 'ubiquity/partitioner/single_os_replace'
                self.db.subst(q, 'OS', system)
                self.db.subst(q, 'DISTRO', release.name)
                title = self.description(q)
                desc = self.extended_description(q)
                opt = PartitioningOption(title, desc)
                options['use_device'] = opt

                if wubi_option or resize_option:
                    if resize_option:
                        q = 'ubiquity/partitioner/single_os_resize'
                    else:
                        q = 'ubiquity/partitioner/ubuntu_inside'
                    self.db.subst(q, 'OS', system)
                    self.db.subst(q, 'DISTRO', release.name)
                    title = self.description(q)
                    desc = self.extended_description(q)
                    opt = PartitioningOption(title, desc)
                    options['resize'] = opt

        elif os_count == 2 and len(ubuntu_systems) == 1:
            # TODO: verify that ubuntu_systems[0] is the same partition as one
            # of the ones offered in the replace options.
            if 'replace' in self.extra_options:
                ubuntu = ubuntu_systems[0]
                q = 'ubiquity/partitioner/ubuntu_format'
                self.db.subst(q, 'CURDISTRO', ubuntu)
                title = self.description(q)
                desc = self.extended_description(q)
                opt = PartitioningOption(title, desc)
                options['replace'] = opt

            q = 'ubiquity/partitioner/ubuntu_and_os_format'
            system = (set(operating_systems) - set(ubuntu_systems)).pop()
            self.db.subst(q, 'OS', system)
            self.db.subst(q, 'CURDISTRO', ubuntu)
            title = self.description(q)
            desc = self.extended_description(q)
            opt = PartitioningOption(title, desc)
            options['use_device'] = opt

            reuse = self.calculate_reuse_option()
            if reuse is not None:
                options['reuse'] = reuse
        else:
            # "There are multiple operating systems present" case
            q = 'ubiquity/partitioner/multiple_os_format'
            self.db.subst(q, 'DISTRO', release.name)
            title = self.description(q)
            desc = self.extended_description(q)
            opt = PartitioningOption(title, desc)
            options['use_device'] = opt

            if wubi_option:
                pass
            elif resize_option:
                q = 'ubiquity/partitioner/multiple_os_resize'
                self.db.subst(q, 'DISTRO', release.name)
                title = self.description(q)
                desc = self.extended_description(q)
                opt = PartitioningOption(title, desc)
                options['resize'] = opt

        return options

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


            # You know what they say about assumptions.
            has_wubi = os.path.exists('/cdrom/wubi.exe')
            has_resize = 'resize' in self.extra_options
            try_for_wubi = has_wubi and not has_resize
            # Let's assume all disks are full unless we find a disk with
            # space for another partition.
            partition_table_full = True

            with misc.raised_privileges():
                # {'/dev/sda' : ('/dev/sda1', 24973242, '32256-2352430079'), ...
                parted = parted_server.PartedServer()
                layout = {}
                for disk in parted.disks():
                    parted.select_disk(disk)
                    if try_for_wubi and partition_table_full:
                        primary_count = 0
                        ntfs_count = 0
                        parted.open_dialog('GET_MAX_PRIMARY')
                        try:
                            max_primary = int(parted.read_line()[0])
                        except ValueError:
                            max_primary = None
                        finally:
                            parted.close_dialog()

                    ret = []
                    for partition in parted.partitions():
                        if try_for_wubi and partition_table_full:
                            if partition[3] == 'primary':
                                primary_count += 1
                                if partition[4] == 'ntfs':
                                    ntfs_count += 1

                        size = int(partition[2])
                        if partition[4] == 'free':
                            dev = 'free'
                        else:
                            dev = partition[5]

                        ret.append(Partition(dev, size,
                                             partition[1],
                                             partition[4]))
                    layout[disk] = ret
                    if try_for_wubi and partition_table_full:
                        if (max_primary is not None and
                            primary_count >= max_primary and ntfs_count > 0):
                            pass
                        else:
                            partition_table_full = False

                # TODO try the wubi check as a partman-auto choice.
                if try_for_wubi and partition_table_full:
                    import tempfile
                    import subprocess
                    mount_path = tempfile.mkdtemp()
                    for device, name in misc.os_prober().iteritems():
                        if name.find('indows') == -1:
                            continue
                        try:
                            subprocess.check_call(['mount', device, mount_path])
                            if misc.windows_startup_folder(mount_path):
                                self.extra_options['wubi'] = device
                                break
                        except subprocess.CalledProcessError:
                            pass
                        finally:
                            subprocess.call(['umount', mount_path])
                            if os.path.exists(mount_path):
                                os.rmdir(mount_path)

                biggest_free = self.find_script(menu_options, 'biggest_free')
                if biggest_free:
                    dev, p_id = self.split_devpart(biggest_free[0][1])
                    parted.select_disk(dev)
                    size = int(parted.partition_info(p_id)[2])
                    key = biggest_free[0][2]
                    filesystem_size = 5 * 1024 * 1024 * 1024 # 5GB
                    try:
                        with open('/cdrom/casper/filesystem.size') as fp:
                            filesystem_size = int(fp.readline())
                    except IOError:
                        self.debug('Could not determine filesystem size.')
                    fudge = 200 * 1024 * 1024 # 200 MB
                    if size > filesystem_size + fudge:
                        self.extra_options['biggest_free'] = (key, size)

                # TODO: Add misc.find_in_os_prober(info[5]) ...and size?
                reuse = self.find_script(menu_options, 'reuse')
                if reuse:
                    self.extra_options['reuse'] = []
                    r = self.extra_options['reuse']
                    for option in reuse:
                        dev, p_id = self.split_devpart(option[1])
                        parted.select_disk(dev)
                        info = parted.partition_info(p_id)
                        r.append((option[2], info[5]))

                replace = self.find_script(menu_options, 'replace')
                if replace:
                    self.extra_options['replace'] = []
                    for option in replace:
                        self.extra_options['replace'].append(option[2])

            # We always have the manual option.
            self.extra_options['manual'] = self.manual_desc
            self.ui.set_disk_layout(layout)
            self.ui.set_default_filesystem(self.db.get('partman/default_filesystem'))

            operating_systems, ubuntu_systems = \
                self.calculate_operating_systems(layout)
            has_ubuntu = len(ubuntu_systems) > 0
            heading = self.calculate_autopartitioning_heading(
                            operating_systems, has_ubuntu)
            options = self.calculate_autopartitioning_options(
                            operating_systems, ubuntu_systems)
            if self.debug_enabled():
                import pprint
                self.debug('options:')
                printer = pprint.PrettyPrinter()
                for line in printer.pformat(options).split('\n'):
                    self.debug('%s', line)
                self.debug('extra_options:')
                printer = pprint.PrettyPrinter()
                for line in printer.pformat(self.extra_options).split('\n'):
                    self.debug('%s', line)
            self.ui.set_autopartition_heading(heading)
            self.ui.set_autopartition_options(options, self.extra_options)

        elif question == 'partman-auto/select_disk':
            if self.auto_state is not None:
                disks = {}
                choices = self.choices(question)
                choices_c = self.choices_untranslated(question)
                with misc.raised_privileges():
                    for i in range(len(choices)):
                        size = 0
                        # It seemingly doesn't make sense to go through parted
                        # server when all it would be doing is constructing the
                        # path that we already have.
                        with open(os.path.join(choices_c[i], 'size')) as fp:
                            size = fp.readline()
                        size = int(size)
                        disks[choices[i]] = (choices_c[i], size)
                self.extra_options['use_device'] = (self.some_device_desc, disks)
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
                    self.progress_step('', 1)
                    self.debug('Partman: update_partitions = %s',
                               self.update_partitions)
                    state[1] = None
                    self.tidy_update_partitions()

                    if self.update_partitions:
                        state[1] = self.update_partitions.pop(0)
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
                        self.thaw_choices('choose_partition')
                        self.__state.pop()
                        self.update_partitions = None
                        self.building_cache = False
                        self.progress_stop()
                        self.frontend.refresh()
                        self.ui.show_page_advanced()
                        self.maybe_update_grub()
                        self.ui.update_partman(
                            self.disk_cache, self.partition_cache,
                            self.cache_order)
                else:
                    self.debug('Partman: Building cache')
                    misc.regain_privileges()
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
                                parted.open_dialog('GET_LABEL_TYPE')
                                try:
                                    label = parted.read_line()
                                finally:
                                    parted.close_dialog()
                                self.disk_cache[arg] = {
                                    'dev': dev,
                                    'device': device,
                                    'label': label
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
                    partition_info_cache = {}
                    for devpart in self.update_partitions:
                        dev, part_id = self.split_devpart(devpart)
                        if not dev:
                            continue
                        if dev not in partition_info_cache:
                            parted.select_disk(dev)
                            partition_info_cache[dev] = {}
                            for partition in parted.partitions():
                                partition_info_cache[dev][partition[1]] = \
                                    partition
                        if part_id not in partition_info_cache[dev]:
                            continue
                        info = partition_info_cache[dev][part_id]
                        self.partition_cache[devpart]['parted'] = {
                            'num': info[0],
                            'id': info[1],
                            'size': info[2],
                            'type': info[3],
                            'fs': info[4],
                            'path': info[5],
                            'name': info[6]
                        }

                    misc.drop_privileges()
                    # We want to immediately show the UI.
                    self.ui.show_page_advanced()
                    self.frontend.set_page(NAME)
                    self.progress_start(0, len(self.update_partitions),
                        'partman/progress/init/parted')
                    self.debug('Partman: update_partitions = %s',
                               self.update_partitions)

                    # Selecting a disk will ask to create a new disklabel,
                    # so don't bother with that.

                    devpart = None
                    self.tidy_update_partitions()
                    if self.update_partitions:
                        devpart = self.update_partitions.pop(0)
                        partition = self.partition_cache[devpart]
                        self.debug('Partman: Building cache (%s)',
                                   partition['parted']['path'])
                        self.__state.append([question, devpart, None])
                        self.preseed(question, partition['display'],
                                     seen=False)
                        self.freeze_choices('choose_partition')
                        return True
                    else:
                        self.debug('Partman: Finished building cache '
                                   '(no partitions to update)')
                        self.thaw_choices('choose_partition')
                        self.update_partitions = None
                        self.building_cache = False
                        self.progress_stop()
                        self.maybe_update_grub()
                        self.ui.update_partman(
                            self.disk_cache, self.partition_cache,
                            self.cache_order)
            elif self.creating_partition:
                devpart = self.creating_partition['devpart']
                if devpart in self.partition_cache:
                    self.ui.show_page_advanced()
                    self.maybe_update_grub()
                    self.ui.update_partman(
                        self.disk_cache, self.partition_cache,
                        self.cache_order)
            elif self.editing_partition:
                devpart = self.editing_partition['devpart']
                if devpart in self.partition_cache:
                    self.ui.show_page_advanced()
                    self.maybe_update_grub()
                    self.ui.update_partman(
                        self.disk_cache, self.partition_cache,
                        self.cache_order)
            elif self.deleting_partition:
                raise AssertionError("Deleting partition didn't rebuild cache?")

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

            plugin.Plugin.run(self, priority, question)

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
                raise AssertionError("Returned to %s with nothing to do" %
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
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman/free_space':
            if self.creating_partition:
                self.preseed_script(question, menu_options, 'new')
                return True
            else:
                raise AssertionError("Arrived at %s unexpectedly" % question)

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
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman-partitioning/new_partition_type':
            if self.creating_partition:
                if self.creating_partition['type'] == PARTITION_TYPE_PRIMARY:
                    self.preseed(question, 'Primary', seen=False)
                else:
                    self.preseed(question, 'Logical', seen=False)
                return True
            else:
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman-partitioning/new_partition_place':
            if self.creating_partition:
                if (self.creating_partition['place'] ==
                    PARTITION_PLACE_BEGINNING):
                    self.preseed(question, 'Beginning', seen=False)
                else:
                    self.preseed(question, 'End', seen=False)
                return True
            else:
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman/active_partition':
            if self.building_cache:
                state = self.__state[-1]
                partition = self.partition_cache[state[1]]

                if state[0] == question:
                    state[2] += 1
                    if state[2] < len(partition['active_partition_build']):
                        # Move on to the next item.
                        visit = partition['active_partition_build']
                        self.preseed(question, visit[state[2]][2], seen=False)
                        return True
                    else:
                        # Finished building the cache for this submenu; go
                        # back to the previous one.
                        self.thaw_choices('active_partition')
                        try:
                            del partition['active_partition_build']
                        except KeyError:
                            pass
                        self.__state.pop()
                        self.maybe_thaw_choose_partition()
                        return False

                assert state[0] == 'partman/choose_partition'

                with misc.raised_privileges():
                    parted = parted_server.PartedServer()

                    parted.select_disk(partition['dev'])
                    for entry in ('method',
                                  'filesystem', 'detected_filesystem',
                                  'acting_filesystem',
                                  'existing', 'formatable',
                                  'mountpoint'):
                        if parted.has_part_entry(partition['id'], entry):
                            partition[entry] = \
                                parted.readline_part_entry(partition['id'],
                                                           entry)

                partition['method_choices'] = []
                for use in self.use_as(state[1],
                                       partition['parted']['fs'] == 'free'):
                    partition['method_choices'].append(use)

                partition['mountpoint_choices'] = []
                if 'method' in partition and 'acting_filesystem' in partition:
                    filesystem = partition['acting_filesystem']
                    for mpc in self.default_mountpoint_choices(filesystem):
                        partition['mountpoint_choices'].append(mpc)

                visit = []
                for (script, arg, option) in menu_options:
                    if arg == 'format':
                        partition['can_activate_format'] = True
                    elif arg == 'resize':
                        visit.append((script, arg,
                                      self.translate_to_c(question, option)))
                        partition['can_resize'] = True
                if visit:
                    partition['active_partition_build'] = visit
                    self.__state.append([question, state[1], 0])
                    self.preseed(question, visit[0][2], seen=False)
                    self.freeze_choices('active_partition')
                    return True
                else:
                    # Back up to the previous menu.
                    self.thaw_choices('active_partition')
                    self.maybe_thaw_choose_partition()
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
                raise AssertionError("Arrived at %s unexpectedly" % question)

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
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman-partitioning/new_size':
            if self.autopartition_question is not None:
                if self.auto_state is not None:
                    if 'resize' not in self.extra_options:
                        self.extra_options['resize'] = {}
                    p_id = self.translate_to_c(self.autopartition_question,
                                               self.auto_state[1])
                    p_id = p_id.rsplit('//')[1]
                    disk = self.translate_to_c(self.autopartition_question, self.auto_state[1])
                    disk = re.search('/var/lib/partman/devices/(.*)//', disk).group(1)
                    with misc.raised_privileges():
                        parted = parted_server.PartedServer()
                        parted.select_disk(disk)
                        size = int(parted.partition_info(p_id)[2])
                        fs   = parted.partition_info(p_id)[4]
                    self.extra_options['resize'][disk] = \
                        (self.auto_state[1], self.resize_min_size, self.resize_max_size,
                            self.resize_pref_size, self.resize_path, size, fs)
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
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman-target/choose_method':
            if self.creating_partition or self.editing_partition:
                if self.creating_partition:
                    request = self.creating_partition
                else:
                    request = self.editing_partition

                self.preseed_script(question, menu_options,
                                    None, request['method'])
                return True
            else:
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question in ('partman-basicfilesystems/mountpoint',
                          'partman-basicfilesystems/fat_mountpoint',
                          'partman-uboot/mountpoint'):
            if self.creating_partition or self.editing_partition:
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
                raise AssertionError("Arrived at %s unexpectedly" % question)

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
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question.startswith('partman/confirm'):
            self.db.set('ubiquity/partman-confirm', question[8:])
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
                return plugin.Plugin.error(self, priority, question)
            else:
                return True

        elif question == 'partman/installation_medium_mounted':
            self.ui.installation_medium_mounted(
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

        return plugin.Plugin.run(self, priority, question)

    def ok_handler(self):
        if self.current_question.endswith('automatically_partition'):
            (autopartition_choice, self.extra_choice) = \
                self.ui.get_autopartition_choice()
            self.preseed_as_c(self.current_question, autopartition_choice,
                              seen=False)
            # Don't exit partman yet.
        else:
            self.finish_partitioning = True
        self.succeeded = True
        self.exit_ui_loops()

    def exit_ui_loops(self):
        if self.install_bootloader:
            self.preseed('grub-installer/bootdev', self.ui.get_grub_choice())

        plugin.Plugin.exit_ui_loops(self)

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
                       method=None, mountpoint=None, fmt=None):
        assert self.current_question == 'partman/choose_partition'
        self.editing_partition = {
            'devpart': devpart,
            'size': size,
            'method': method,
            'mountpoint': mountpoint,
            'format': fmt
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

    def progress_start(self, progress_min, progress_max, progress_title):
        if (progress_title != 'partman/text/please_wait' and
        hasattr(self.ui, 'progress_start')):
            self.ui.progress_start(self.description(progress_title))
        else:
            self.local_progress = True
            plugin.Plugin.progress_start(self, progress_min, progress_max, progress_title)

    def progress_info(self, progress_title, progress_info):
        if (progress_info != 'partman-partitioning/progress_resizing' and
        hasattr(self.ui, 'progress_info')):
            try:
                self.ui.progress_info(self.description(progress_info))
            except debconf.DebconfError:
                pass
            # We provide no means of cancelling the progress message,
            # so always return True.
            return True
        else:
            plugin.Plugin.progress_info(self, progress_title, progress_info)

    def progress_stop(self):
        if not self.local_progress and hasattr(self.ui, 'progress_stop'):
            self.ui.progress_stop()
        else:
            plugin.Plugin.progress_stop(self)
            self.local_progress = False

    def maybe_update_grub(self):
        if self.install_bootloader:
            grub_bootdev=self.db.get("grub-installer/bootdev")
            if grub_bootdev and grub_bootdev in (part[0] for part in misc.grub_options()):
                default = grub_bootdev
            else:
                default = misc.grub_default()
            self.ui.set_grub_options(default)

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
