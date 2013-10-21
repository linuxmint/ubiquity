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

from collections import namedtuple, OrderedDict
import os
import re
import shutil
import signal

import debconf

from ubiquity import misc, osextras, parted_server, plugin, validation
from ubiquity.install_misc import archdetect


NAME = 'partman'
AFTER = 'prepare'
WEIGHT = 11
# Not useful in oem-config.
OEM = False

PartitioningOption = namedtuple('PartitioningOption', ['title', 'desc'])
Partition = namedtuple('Partition', ['device', 'size', 'id', 'filesystem'])

# List of file system types that reserve extra space for grub.  Found by
# grepping for "reserved_first_sector = 1" in the grub2 source as per
# https://bugs.launchpad.net/ubuntu/+source/ubiquity/+bug/959724
# Only those file systems that set this to 1 can have the boot loader
# installed on them.  This is that list, with values taken from the .name
# entry in the matching structs.
FS_RESERVED_FIRST_SECTOR = {
    'btrfs',
    'ext2',
    'fat',
    'hfsplus',
    'nilfs2',
    'ntfs',
    # Add a few ext variants that aren't explicitly described in grub2.
    'ext3',
    'ext4',
    # Add a few fat variants.
    'fat16',
    'fat32',
    # Others?
}


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

    def show_bootloader_options(self):
        """Show the boot loader options."""
        pass

    def get_grub_choice(self):
        return misc.grub_default()

    def get_crypto_keys(self):
        pass


class PageGtk(PageBase):
    plugin_title = 'ubiquity/text/part_auto_heading_label'
    plugin_is_install = True

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        from gi.repository import Gtk
        from ubiquity.gtkwidgets import Builder
        builder = Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepPartAsk.ui'))
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepPartAuto.ui'))
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepPartAdvanced.ui'))
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepPartCrypto.ui'))
        builder.connect_signals(self)

        self.page_ask = builder.get_object('stepPartAsk')
        self.page_auto = builder.get_object('stepPartAuto')
        self.page_advanced = builder.get_object('stepPartAdvanced')
        self.page_crypto = builder.get_object('stepPartCrypto')

        # Get all objects + add internal child(s)
        all_widgets = builder.get_object_ids()
        all_widgets.update(['partition_dialog_okbutton'])
        for wdg in all_widgets:
            setattr(self, wdg, builder.get_object(wdg))

        # Crypto page
        self.password_strength_pages = {
            'empty': 0,
            'too_short': 1,
            'weak': 2,
            'fair': 3,
            'good': 4,
            'strong': 5,
        }
        self.password_match_pages = {
            'empty': 0,
            'mismatch': 1,
            'ok': 2,
        }

        self.partition_bars = {}
        self.segmented_bar_vbox = None
        self.resize_min_size = None
        self.resize_max_size = None
        self.resize_pref_size = None
        self.resize_path = ''
        self.auto_colors = ['3465a4', '73d216', 'f57900']
        self.extra_options = {}

        self.partition_mount_combo.get_child().set_activates_default(True)

        self.plugin_optional_widgets = [self.page_auto, self.page_advanced,
                                        self.page_crypto]
        self.current_page = self.page_ask

        # Set some parameters that do not change between runs of the plugin
        release = misc.get_release()
        self.partitionbox.set_property('title', release.name)

        # New partition
        self.resizewidget.get_child2().get_child().set_property(
            'title', release.name)

        # Annoyingly, you can't set packing properties for cell renderers
        # in Glade.
        cell = Gtk.CellRendererText()
        self.part_auto_select_drive.pack_start(cell, False)
        self.part_auto_select_drive.add_attribute(cell, 'text', 0)
        cell = Gtk.CellRendererText()
        cell.set_property('xalign', 1.0)
        cell.set_property('sensitive', False)
        self.part_auto_select_drive.pack_start(cell, True)
        self.part_auto_select_drive.add_attribute(cell, 'markup', 1)
        self.plugin_widgets = self.page_ask

        # Annoyngly, the inline toolbar has custom background, which
        # I do not know how to remove =(
        partition_toolbar_style = self.partition_toolbar.get_style_context()
        partition_toolbar_style.add_class(Gtk.STYLE_CLASS_INLINE_TOOLBAR)
        for wdg in self.partition_toolbar.get_children():
            self.partition_toolbar.child_set_property(wdg, 'homogeneous',
                                                      False)

        # GtkBuilder signal mapping is broken (LP: #852054).
        self.part_auto_hidden_label.connect(
            'activate-link', self.part_auto_hidden_label_activate_link)

        # Define a list to save grub imformation
        self.grub_options = []

    def plugin_get_current_page(self):
        if self.current_page == self.page_ask:
            self.plugin_is_install = self.part_ask_option_is_install()
        else:
            self.plugin_is_install = True
        return self.current_page

    def configure_wubi_and_reboot(self):
        self.controller.allow_change_step(False)
        device = self.extra_options['wubi']
        import tempfile
        import subprocess
        mount_path = tempfile.mkdtemp()
        try:
            subprocess.check_call(['mount', device, mount_path])
            startup = misc.windows_startup_folder(mount_path)
            shutil.copy('/cdrom/wubi.exe', startup)
        except subprocess.CalledProcessError:
            pass
        finally:
            subprocess.call(['umount', '-l', mount_path])
            if os.path.exists(mount_path):
                os.rmdir(mount_path)
            self.controller._wizard.do_reboot()

    def set_page_title(self, title):
        self.controller._wizard.page_title.set_markup(
            '<span size="xx-large">%s</span>' % title)

    def move_crypto_widgets(self, auto=True):
        from gi.repository import Gtk
        parent = self.password_grid.get_parent()
        if auto:
            new_parent = self.crypto_grid
            crypto_widgets = [
                ('crypto_label', 'crypto_description_2', 'bottom', 1, 1),
                ('password_grid', 'crypto_label', 'right', 1, 2)]
        else:
            new_parent = self.partition_dialog_grid
            crypto_widgets = [
                ('password_grid', 'partition_mount_combo', 'bottom', 1,
                 2),
                ('crypto_label', 'password_grid', 'left', 1, 1)]
        if parent == new_parent:
            return
        crypto_widgets += [
            ('verified_crypto_label', 'crypto_label', 'bottom', 1, 1),
            ('crypto_warning', 'verified_crypto_label', 'bottom', 2, 1),
            ('crypto_extra_label', 'crypto_warning', 'bottom', 1, 1),
            ('crypto_overwrite_space', 'crypto_extra_label', 'right', 1, 1),
            ('crypto_extra_time', 'crypto_overwrite_space', 'bottom', 1, 1)]
        for widget, sibling, direction, width, height in crypto_widgets:
            widget = getattr(self, widget)
            if isinstance(sibling, str):
                sibling = getattr(self, sibling)
            direction = getattr(Gtk.PositionType, direction.upper())
            parent = widget.get_parent()
            if parent is not None:
                parent.remove(widget)
            new_parent.attach_next_to(widget, sibling, direction,
                                      width, height)
            widget.show()

    def plugin_on_next_clicked(self):
        reuse = self.reuse_partition.get_active()
        replace = self.replace_partition.get_active()
        resize = self.resize_use_free.get_active()
        custom = self.custom_partitioning.get_active()
        use_device = self.use_device.get_active()
        biggest_free = 'biggest_free' in self.extra_options
        crypto = self.use_crypto.get_active()
        disks = self.extra_options.get('use_device', [])
        if disks:
            disks = disks[1]
        one_disk = len(disks) == 1

        if custom:
            self.set_page_title(self.custom_partitioning.get_label())
            self.current_page = self.page_advanced
            self.move_crypto_widgets(auto=False)
            self.controller.go_to_page(self.current_page)
            self.controller.toggle_next_button('install_button')
            self.plugin_is_install = True
            return False

        # Setting the model early on, because if there is only one
        # disk, we switch to install interface staight away and it
        # queries the model to get the disk
        if self.current_page == self.page_ask:
            m = self.part_auto_select_drive.get_model()
            m.clear()
            if use_device:
                for disk in disks:
                    m.append([disk, ''])
                self.part_auto_select_drive.set_active(0)

        # Currently we support crypto only in use_disk
        # TODO dmitrij.ledkov 2012-07-25 no way to go back and return
        # to here? This needs to be addressed in the design document.
        if crypto and use_device and self.current_page == self.page_ask:
            self.set_page_title(
                self.controller.get_string('ubiquity/text/crypto_label'))
            self.current_page = self.page_crypto
            self.move_crypto_widgets()
            self.show_encryption_passphrase(crypto)
            self.controller.go_to_page(self.current_page)
            self.controller.toggle_next_button('install_button')
            self.plugin_is_install = one_disk
            self.info_loop(None)
            return True

        if (self.current_page == self.page_crypto and
                not self.get_crypto_keys()):
            # Stop until encryption keys are setup
            self.controller.allow_go_forward(False)
            return True

        # Do we have all that we need from the user?
        done_partitioning = (
            (resize and biggest_free) or
            (use_device and one_disk) or
            reuse or replace)

        # Looks like not... go to disk space allocation page
        if (self.current_page in [self.page_ask, self.page_crypto]
                and not done_partitioning):
            if resize:
                self.set_page_title(self.resize_use_free.get_label())
                if 'wubi' in self.extra_options:
                    self.configure_wubi_and_reboot()
                    return True
                extra_resize = self.extra_options['resize']
                disk_ids = list(extra_resize.keys())
                # FIXME: perhaps it makes more sense to store the disk
                # description.
                for disk in disks:
                    key = disks[disk][0].rsplit('/', 1)[1]
                    if key in disk_ids:
                        min_size = extra_resize[key][1]
                        part_size = extra_resize[key][5]
                        m.append([disk, '<small>%s</small>' %
                                  misc.format_size(part_size - min_size)])
                self.part_auto_select_drive.set_active(0)
                self.initialize_resize_mode()

            if use_device:
                self.set_page_title(self.use_device.get_label())
                self.initialize_use_disk_mode()

            self.current_page = self.page_auto
            self.controller.go_to_page(self.current_page)
            self.controller.toggle_next_button('install_button')
            self.plugin_is_install = True
            return True

        # Return control to partman, which will call
        # get_autopartition_choice and start partitioninging the device.
        self.controller.switch_to_install_interface()
        return False

    def plugin_on_back_clicked(self):
        if self.current_page in [self.page_auto, self.page_crypto]:
            title = self.controller.get_string(self.plugin_title)
            self.controller._wizard.page_title.set_markup(
                '<span size="xx-large">%s</span>' % title)
            self.current_page = self.page_ask
            self.controller.go_to_page(self.current_page)
            # If we arrived at a second partitioning page, then the option
            # selected on the first page would not cause the forward button to
            # be marked as Install Now.
            self.controller.allow_go_forward(True)
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

    def on_crypto_lvm_toggled(self, w):
        if self.use_crypto.get_active():
            if w == self.use_crypto:
                self.use_lvm.set_active(True)
            if w == self.use_lvm and not w.get_active():
                self.use_crypto.set_active(False)

    # Automatic partitioning page

    def get_current_disk_partman_id(self):
        i = self.part_auto_select_drive.get_active_iter()
        if not i:
            return None
        m = self.part_auto_select_drive.get_model()
        val = misc.utf8(m.get_value(i, 0), errors='replace')

        partman_id = self.extra_options['use_device'][1][val][0]
        disk_id = partman_id.rsplit('/', 1)[1]
        return disk_id

    def set_part_auto_hidden_label(self):
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

    def part_ask_option_is_install(self):
        if (self.reuse_partition.get_active() or
                self.replace_partition.get_active()):
            return True
        elif (self.resize_use_free.get_active() and
                'biggest_free' in self.extra_options):
            return True
        elif (self.use_device.get_active() and
              len(self.extra_options['use_device'][1]) == 1):
            return True
        else:
            return False

    def part_ask_option_changed(self, unused_widget):
        '''The user has selected one of the automatic partitioning options.'''
        about_to_install = self.part_ask_option_is_install()

        if 'wubi' in self.extra_options and self.resize_use_free.get_active():
            self.controller.toggle_next_button('restart_to_continue')
        else:
            if about_to_install:
                self.controller.toggle_next_button('install_button')
            else:
                self.controller.toggle_next_button()
            self.plugin_is_install = about_to_install

        # Supporting crypto and lvm in new installs only for now
        use_device = self.use_device.get_active()
        self.use_lvm.set_sensitive(use_device)
        self.use_crypto.set_sensitive(use_device)

    def initialize_resize_mode(self):
        disk_id = self.get_current_disk_partman_id()
        if not disk_id:
            return

        (resize_min_size, resize_max_size, resize_pref_size,
         resize_path, size, fs) = self.extra_options['resize'][disk_id][1:]

        # Make sure we always have enough space to install using the
        # same install_size as everywhere else in ubiquity
        real_max_size = size - misc.install_size()
        if real_max_size < resize_max_size:
            resize_max_size = real_max_size

        self.resizewidget.set_property('min_size', int(resize_min_size))
        self.resizewidget.set_property('max_size', int(resize_max_size))

        title = misc.find_in_os_prober(resize_path)
        icon = self.resizewidget.get_child1().get_child()
        if not title:
            # This is most likely a partition with some files on it.
            title = self.controller.get_string('ubiquity/text/part_auto_files')
            title = title.replace('${SIZE}', misc.format_size(resize_min_size))
            icon.set_property('icon-name', 'folder')
        else:
            if 'windows' in title.lower():
                PATH = (
                    os.environ.get('UBIQUITY_PATH', False) or
                    '/usr/share/ubiquity')
                icon.logo.set_from_file(os.path.join(
                    PATH, 'pixmaps', 'windows_square.png'))
            elif 'buntu' in title.lower():
                icon.set_property('icon-name', 'distributor-logo')
            else:
                icon.set_property('icon-name', 'block-device')

        # TODO See if we can get the filesystem label first in misc.py,
        # caching lookups.
        extra = '%s (%s)' % (resize_path, fs)

        self.resizewidget.get_child1().get_child().set_property('title', title)
        self.resizewidget.get_child1().get_child().set_property('extra', extra)
        self.resizewidget.set_property('part_size', size)
        self.resizewidget.set_pref_size(int(resize_pref_size))

        # Set the extra field of the partition being created via resizing.
        try:
            dev, partnum = re.search(r'(.*\D)(\d+)$', resize_path).groups()
            dev = '%s%d' % (dev, int(partnum) + 1)
        except Exception as e:
            dev = 'unknown'
            self.debug('Could not determine new partition number: %s', e)
            self.debug('extra_options: %s' % str(self.extra_options))
        extra = '%s (%s)' % (dev, self.default_filesystem)
        self.resizewidget.get_child2().get_child().set_property('extra', extra)

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
        val = misc.utf8(m.get_value(i, 0), errors='replace')
        size = self.extra_options['use_device'][1][val][1]
        self.partitionbox.set_size(size)

    def part_auto_select_drive_changed(self, unused_widget):
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
        return True

    def show_bootloader_options(self):
        self.bootloader_grid.show()

    def set_grub_options(self, default, grub_installable):
        from gi.repository import Gtk, GObject
        self.grub_options = misc.grub_options()
        l = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING)
        self.grub_device_entry.set_model(l)
        selected = False
        for opt in self.grub_options:
            path = opt[0]
            if grub_installable.get(path, False):
                i = l.append(opt)
                if path == default:
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
            disk = self.get_current_disk_partman_id()
            if isinstance(disk, str) and disk:
                disk_path = disk.replace("=", "/")
                if os.path.exists(disk_path):
                    return misc.grub_default(boot=disk_path)

            return misc.grub_default()

    def set_autopartition_heading(self, heading):
        self.part_ask_heading.set_label(heading)

    def plugin_set_online_state(self, state):
        self.reuse_partition.set_sensitive(state)
        self.reuse_partition_desc.set_sensitive(state)

    def set_autopartition_options(self, options, extra_options):
        # TODO Need to select a radio button when resize isn't around.
        self.extra_options = extra_options
        fmt = '<span size="small">%s</span>'
        option_to_widget = (
            ("resize", "resize_use_free"),
            ("reuse", "reuse_partition"),
            ("replace", "replace_partition"),
            ("use_device", "use_device"),
            ("manual", "custom_partitioning"),
            ("some_device_crypto", "use_crypto"),
            ("some_device_lvm", "use_lvm"),
        )

        if 'some_device_crypto' in extra_options:
            title = self.controller.get_string(
                'ubiquity/text/use_crypto')
            desc = self.controller.get_string('ubiquity/text/use_crypto_desc')
            options['some_device_crypto'] = PartitioningOption(title, desc)

        if 'some_device_lvm' in extra_options:
            title = self.controller.get_string('ubiquity/text/use_lvm')
            desc = self.controller.get_string('ubiquity/text/use_lvm_desc')
            options['some_device_lvm'] = PartitioningOption(title, desc)

        ticked = False
        for option, name in option_to_widget:
            opt_widget = getattr(self, name)
            opt_desc = getattr(self, name + '_desc')

            if option in options:
                opt_widget.show()
                opt_desc.show()
                opt_widget.set_label(options[option].title)
                opt_desc.set_markup(fmt % options[option].desc)
                if not ticked and opt_widget.get_sensitive():
                    opt_widget.set_active(True)
                    ticked = True
            else:
                opt_widget.hide()
                opt_desc.hide()

        # Process the default selection
        self.part_ask_option_changed(None)

        # Make sure we're on the autopartitioning page.
        self.current_page = self.page_ask

    def get_autopartition_choice(self):
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
            def choose_recipe():
                # TODO dmitrij.ledkov 2012-07-23: RAID recipe?

                have_lvm = 'some_device_lvm' in self.extra_options
                want_lvm = self.use_lvm.get_active()

                have_crypto = 'some_device_crypto' in self.extra_options
                want_crypto = self.use_crypto.get_active()

                if not ((want_crypto and have_crypto) or
                        (want_lvm and have_lvm)):
                    return self.extra_options['use_device'][0]

                if want_crypto:
                    return self.extra_options['some_device_crypto']

                if want_lvm:
                    return self.extra_options['some_device_lvm']

                # Something went horribly wrong, we should have returned
                # earlier
                return None

            i = self.part_auto_select_drive.get_active_iter()
            m = self.part_auto_select_drive.get_model()
            disk = m.get_value(i, 0)
            choice = choose_recipe()
            # Is the encoding necessary?
            return choice, misc.utf8(disk, errors='replace')

        else:
            raise AssertionError("Couldn't get autopartition choice")

    # Advanced partitioning page

    def show_page_advanced(self):
        self.current_page = self.page_advanced

    def progress_start(self, progress_title):
        self.partition_list_buttonbox.set_sensitive(False)
        self.part_advanced_recalculating_label.set_text(progress_title)
        self.part_advanced_recalculating_label.show()
        self.part_advanced_recalculating_spinner.show()
        self.part_advanced_recalculating_spinner.start()

    def progress_info(self, progress_info):
        self.part_advanced_recalculating_label.set_text(progress_info)

    def progress_stop(self):
        self.partition_list_buttonbox.set_sensitive(True)
        self.part_advanced_recalculating_spinner.stop()
        self.part_advanced_recalculating_spinner.hide()
        self.part_advanced_recalculating_label.hide()

    def partman_column_name(self, unused_column, cell, model, iterator,
                            user_data):
        if not model[iterator][1]:
            return

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

    def partman_column_type(self, unused_column, cell, model, iterator,
                            user_data):
        if not model[iterator][1]:
            return

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
    def partman_column_mountpoint(self, unused_column, cell, model, iterator,
                                  user_data):
        if not model[iterator][1]:
            return

        partition = model[iterator][1]
        mountpoint = self.controller.dbfilter.get_current_mountpoint(partition)
        if mountpoint is None:
            mountpoint = ''
        cell.set_property('text', mountpoint)

    def partman_column_format(self, unused_column, cell, model, iterator,
                              user_data):
        if not model[iterator][1]:
            return

        partition = model[iterator][1]
        if 'id' not in partition:
            cell.set_property('visible', False)
            cell.set_property('active', False)
            cell.set_property('activatable', False)
        elif 'method' in partition:
            cell.set_property('visible', True)
            cell.set_property('active', partition['method'] == 'format')
            cell.set_property(
                'activatable', 'can_activate_format' in partition)
        else:
            cell.set_property('visible', True)
            cell.set_property('active', False)
            cell.set_property('activatable', False)

    @plugin.only_this_page
    def partman_column_format_toggled(self, unused_cell, path, user_data):
        if not self.controller.allowed_change_step():
            return
        model = user_data
        devpart = model[path][0]
        partition = model[path][1]
        if 'id' not in partition or 'method' not in partition:
            return
        self.controller.allow_change_step(False)
        self.controller.dbfilter.edit_partition(devpart, fmt='dummy')

    def partman_column_size(self, unused_column, cell, model, iterator,
                            user_data):
        if not model[iterator][1]:
            return

        partition = model[iterator][1]
        if 'id' not in partition:
            cell.set_property('text', '')
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['parted']['size']) / 1000000
            cell.set_property('text', '%d MB' % size_mb)

    def partman_column_used(self, unused_column, cell, model, iterator,
                            user_data):
        if not model[iterator][1]:
            return

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

    def partman_column_syst(self, unused_column, cell, model, iterator,
                            user_data):
        cell.set_property('text', '')
        if not (model[iterator][1] and 'id' in model[iterator][1]):
            return
        partition = model[iterator][1]['parted']
        if (partition['fs'] not in ('free', 'linux-swap') and
                partition['type'] != 'unusable'):
            for opt in self.grub_options:
                if partition['path'] in opt:
                    cell.set_property('text', '%s' % opt[1])
                    break

    @plugin.only_this_page
    def partman_popup(self, widget, event):
        from gi.repository import Gtk
        if not self.controller.allowed_change_step():
            return

        model, iterator = widget.get_selection().get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]

        partition_list_menu = Gtk.Menu()
        actions = [action for action in
                   self.controller.dbfilter.get_actions(devpart, partition)]
        actions.append('separator')
        actions.append('undo')
        for action in self.controller.dbfilter.get_actions(devpart, partition):
            if action == 'separator' and partition_list_menu.get_children():
                partition_list_menu.append(Gtk.SeparatorMenuItem())
            widget = 'partition_button_%s' % action
            signal_callback = getattr(self,
                                      'on_partition_list_%s_activate' % action)
            new_item = Gtk.MenuItem(self.controller.get_string(widget))
            new_item.connect('activate', signal_callback)
            partition_list_menu.append(new_item)

        partition_list_menu.show_all()

        if event:
            button = event.button
            time = event.get_time()
        else:
            button = 0
            time = 0
        partition_list_menu.popup(None, None, None, None, button, time)

    def show_encryption_passphrase(self, show_hide):
        self.crypto_overwrite_space.set_active(False)
        self.password.set_text('')
        self.verified_password.set_text('')

        if show_hide:
            action = 'show'
            self.info_loop(None)
        else:
            action = 'hide'
            self.controller.allow_go_forward(True)
            self.partition_dialog_okbutton.set_sensitive(True)

        for widget in ['password_grid', 'crypto_label', 'crypto_warning',
                       'verified_crypto_label', 'crypto_extra_label',
                       'crypto_overwrite_space', 'crypto_extra_time']:
            getattr(getattr(self, widget), action)()

    @plugin.only_this_page
    def partman_dialog(self, devpart, partition, create=True):
        from gi.repository import Gtk, GObject
        if not self.controller.allowed_change_step():
            return

        self.partition_dialog_grid.show_all()
        if create:
            self.partition_edit_format_checkbutton.hide()
            self.partition_create_place_beginning.set_active(True)
        else:
            self.partition_create_place_label.hide()
            self.partition_create_place_beginning.hide()
            self.partition_create_place_end.hide()
            self.partition_create_type_label.hide()
            self.partition_create_type_primary.hide()
            self.partition_create_type_logical.hide()

        title = 'partition_dialog' if create else 'partition_edit_dialog'
        self.partition_dialog.set_title(self.controller.get_string(title))

        # TODO cjwatson 2006-11-01: Because partman doesn't use a question
        # group for these, we have to figure out in advance whether each
        # question is going to be asked.
        if create and partition['parted']['type'] == 'pri/log':
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

        # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
        # partman expects.
        min_size_mb = 0
        cur_size_mb = 0
        max_size_mb = 0
        if create:
            max_size_mb = int(partition['parted']['size']) / 1000000
            cur_size_mb = max_size_mb
        else:
            current_size = None
            if ('can_resize' not in partition or not partition['can_resize'] or
                    'resize_min_size' not in partition or
                    'resize_max_size' not in partition):
                self.partition_size_label.hide()
                self.partition_size_grid.hide()
            else:
                min_size_mb = int(partition['resize_min_size']) / 1000000
                cur_size_mb = int(partition['parted']['size']) / 1000000
                max_size_mb = int(partition['resize_max_size']) / 1000000
                # Bad things happen if the current size is out of bounds.
                min_size_mb = min(min_size_mb, cur_size_mb)
                max_size_mb = max(cur_size_mb, max_size_mb)
        if max_size_mb is not 0:
            self.partition_size_spinbutton.set_adjustment(
                Gtk.Adjustment(value=max_size_mb, upper=max_size_mb,
                               step_increment=1, page_increment=100))
            self.partition_size_spinbutton.set_value(cur_size_mb)
            current_size = str(self.partition_size_spinbutton.get_value())
        self.partition_use_combo.clear()
        renderer = Gtk.CellRendererText()
        self.partition_use_combo.pack_start(renderer, True)
        if create:
            self.partition_use_combo.add_attribute(renderer, 'text', 2)
            list_store = Gtk.ListStore(GObject.TYPE_STRING,
                                       GObject.TYPE_STRING,
                                       GObject.TYPE_STRING)
            for method, name, description in (
                    self.controller.dbfilter.use_as(
                        devpart, True, ['crypto'])):
                list_store.append([method, name, description])
        else:
            self.partition_use_combo.add_attribute(renderer, 'text', 1)
            list_store = Gtk.ListStore(GObject.TYPE_STRING,
                                       GObject.TYPE_STRING)
            for script, arg, option in partition['method_choices']:
                list_store.append([arg, option])
        self.partition_use_combo.set_model(list_store)
        if create:
            if list_store.get_iter_first():
                self.partition_use_combo.set_active(0)
        else:
            current_method = self.controller.dbfilter.get_current_method(
                partition)
            if current_method:
                iterator = list_store.get_iter_first()
                while iterator:
                    if list_store[iterator][0] == current_method:
                        self.partition_use_combo.set_active_iter(iterator)
                        break
                    iterator = list_store.iter_next(iterator)

            if 'id' not in partition:
                self.partition_edit_format_checkbutton.hide()
                current_format = False
            elif 'method' in partition:
                self.partition_edit_format_checkbutton.show()
                self.partition_edit_format_checkbutton.set_sensitive(
                    'can_activate_format' in partition)
                current_format = (partition['method'] == 'format')
            else:
                self.partition_edit_format_checkbutton.show()
                self.partition_edit_format_checkbutton.set_sensitive(False)
                current_format = False
            self.partition_edit_format_checkbutton.set_active(current_format)
        list_store = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING)
        if create:
            all_choices = self.controller.dbfilter.default_mountpoint_choices()
        elif 'mountpoint_choices' in partition:
            all_choices = partition['mountpoint_choices']
        else:
            all_choices = []
        for mp, choice_c, choice in all_choices:
            list_store.append([mp, choice])
        self.partition_mount_combo.set_model(list_store)
        if self.partition_mount_combo.get_entry_text_column() == -1:
            self.partition_mount_combo.set_entry_text_column(0)
        current_mountpoint = None
        if not create:
            current_mountpoint = \
                self.controller.dbfilter.get_current_mountpoint(partition)
        if current_mountpoint is None:
            current_mountpoint = ''
        elif not create:
            iterator = list_store.get_iter_first()
            while iterator:
                if list_store[iterator][0] == current_mountpoint:
                    self.partition_mount_combo.set_active_iter(iterator)
                    break
                iterator = list_store.iter_next(iterator)
        self.partition_mount_combo.get_child().set_text(current_mountpoint)
        self.partition_dialog.show()
        response = self.partition_dialog.run()
        self.partition_dialog.hide()

        if create and (response == Gtk.ResponseType.OK):
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

            method_iter = self.partition_use_combo.get_active_iter()
            if method_iter is None:
                method = None
            else:
                model = self.partition_use_combo.get_model()
                method = model.get_value(method_iter, 1)

            mount_combo = self.partition_mount_combo
            mountpoint = mount_combo.get_child().get_text()

            self.controller.allow_change_step(False)
            self.controller.dbfilter.create_partition(
                devpart,
                str(self.partition_size_spinbutton.get_value()),
                prilog, place, method, mountpoint)

        if not create and (response == Gtk.ResponseType.OK):
            size = None
            if current_size is not None:
                size = str(self.partition_size_spinbutton.get_value())

            method_iter = self.partition_use_combo.get_active_iter()
            if method_iter is None:
                method = None
            else:
                model = self.partition_use_combo.get_model()
                method = model.get_value(method_iter, 0)

            fmt = self.partition_edit_format_checkbutton.get_active()

            mountpoint = self.partition_mount_combo.get_child().get_text()

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

    def plugin_translate(self, lang):
        symbolic_widgets = ['partition_button_new', 'partition_button_delete']
        for widget_name in symbolic_widgets:
            widget = getattr(self, widget_name)
            text = widget.get_label()
            if len(text) == 0:
                continue
            a11y = widget.get_accessible()
            a11y.set_name(text)
            widget.set_label('')

    @plugin.only_this_page
    def on_partition_use_combo_changed(self, combobox):
        model = combobox.get_model()
        iterator = combobox.get_active_iter()
        maybe_crypto = bool(iterator and model[iterator][0] == 'crypto')
        self.show_encryption_passphrase(maybe_crypto)
        # If the selected method isn't a filesystem, then selecting a mount
        # point makes no sense. TODO cjwatson 2007-01-31: Unfortunately we
        # have to hardcode the list of known filesystems here.
        known_filesystems = ('ext4', 'ext3', 'ext2', 'filesystem',
                             'btrfs', 'jfs', 'xfs',
                             'fat16', 'fat32', 'ntfs', 'uboot')
        show = bool(iterator and model[iterator][0] in known_filesystems)
        self.partition_mount_combo.set_visible(show)
        self.partition_mount_label.set_visible(show)
        self.partition_edit_format_checkbutton.set_sensitive(show)
        mount_model = self.partition_mount_combo.get_model()
        if show and mount_model:
            self.partition_dialog_okbutton.set_sensitive(True)
            fs = model[iterator][1]
            mount_model.clear()
            for mp, choice_c, choice in \
                    self.controller.dbfilter.default_mountpoint_choices(fs):
                mount_model.append([mp, choice])

    def on_partition_list_treeview_button_press_event(self, widget, event):
        from gi.repository import Gdk
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            path_at_pos = widget.get_path_at_pos(int(event.x), int(event.y))
            if path_at_pos is not None:
                selection = widget.get_selection()
                selection.unselect_all()
                selection.select_path(path_at_pos[0])

            self.partman_popup(widget, event)
            return True

    @plugin.only_this_page
    def on_partition_list_treeview_key_press_event(self, widget, event):
        from gi.repository import Gdk
        if event.type != Gdk.EventType.KEY_PRESS:
            return False

        if event.keyval == Gdk.KEY_Delete:
            devpart, partition = self.partition_list_get_selection()
            dbfilter = self.controller.dbfilter
            for action in dbfilter.get_actions(devpart, partition):
                if action == 'delete':
                    self.on_partition_list_delete_activate(widget)
                    return True

        return False

    def on_partition_list_treeview_popup_menu(self, widget):
        self.partman_popup(widget, None)
        return True

    @plugin.only_this_page
    def on_partition_list_treeview_selection_changed(self, selection):
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
            for p in self.partition_bars.values():
                p.hide()
            self.partition_bars[dev].show()
        for action in self.controller.dbfilter.get_actions(devpart, partition):
            button_name = 'partition_button_%s' % action
            getattr(self, button_name).set_sensitive(True)
        self.partition_button_undo.set_sensitive(True)

    @plugin.only_this_page
    def on_partition_list_treeview_row_activated(self, treeview,
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
                self.partman_dialog(devpart, partition)
        elif partition.get('locked', False):
            return
        else:
            self.partman_dialog(devpart, partition, create=False)

    def partition_list_get_selection(self):
        model, iterator = (
            self.partition_list_treeview.get_selection().get_selected())
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]
        return (devpart, partition)

    @plugin.only_this_page
    def on_partition_list_new_label_activate(self, unused_widget):
        if not self.controller.allowed_change_step():
            return
        self.controller.allow_change_step(False)
        devpart, partition = self.partition_list_get_selection()
        self.controller.dbfilter.create_label(devpart)

    def on_partition_list_new_activate(self, unused_widget):
        devpart, partition = self.partition_list_get_selection()
        self.partman_dialog(devpart, partition)

    def on_partition_list_edit_activate(self, unused_widget):
        devpart, partition = self.partition_list_get_selection()
        self.partman_dialog(devpart, partition, create=False)

    @plugin.only_this_page
    def on_partition_list_delete_activate(self, unused_widget):
        if not self.controller.allowed_change_step():
            return
        self.controller.allow_change_step(False)
        devpart, partition = self.partition_list_get_selection()
        self.controller.dbfilter.delete_partition(devpart)

    @plugin.only_this_page
    def on_partition_list_undo_activate(self, unused_widget):
        if not self.controller.allowed_change_step():
            return
        self.controller.allow_change_step(False)
        self.controller.dbfilter.undo()

    def update_partman(self, disk_cache, partition_cache, cache_order):
        from gi.repository import Gtk, GObject
        from ubiquity import segmented_bar
        if self.partition_bars:
            for p in list(self.partition_bars.values()):
                self.segmented_bar_vbox.remove(p)
                del p

        partition_tree_model = self.partition_list_treeview.get_model()
        if partition_tree_model is None:
            partition_tree_model = Gtk.ListStore(GObject.TYPE_STRING,
                                                 GObject.TYPE_PYOBJECT)

            cell_name = Gtk.CellRendererText()
            column_name = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_device'),
                cell_name)
            column_name.set_cell_data_func(cell_name, self.partman_column_name)
            column_name.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            self.partition_list_treeview.append_column(column_name)

            cell_type = Gtk.CellRendererText()
            column_type = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_type'), cell_type)
            column_type.set_cell_data_func(cell_type, self.partman_column_type)
            column_type.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            self.partition_list_treeview.append_column(column_type)

            cell_mountpoint = Gtk.CellRendererText()
            column_mountpoint = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_mountpoint'),
                cell_mountpoint)
            column_mountpoint.set_cell_data_func(
                cell_mountpoint, self.partman_column_mountpoint)
            column_mountpoint.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            self.partition_list_treeview.append_column(column_mountpoint)

            cell_format = Gtk.CellRendererToggle()
            column_format = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_format'),
                cell_format)
            column_format.set_cell_data_func(
                cell_format, self.partman_column_format)
            column_format.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            cell_format.connect("toggled", self.partman_column_format_toggled,
                                partition_tree_model)
            self.partition_list_treeview.append_column(column_format)

            cell_size = Gtk.CellRendererText()
            column_size = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_size'), cell_size)
            column_size.set_cell_data_func(cell_size, self.partman_column_size)
            column_size.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            self.partition_list_treeview.append_column(column_size)

            cell_used = Gtk.CellRendererText()
            column_used = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_used'), cell_used)
            column_used.set_cell_data_func(cell_used, self.partman_column_used)
            column_used.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            self.partition_list_treeview.append_column(column_used)

            cell_syst = Gtk.CellRendererText()
            column_syst = Gtk.TreeViewColumn(
                self.controller.get_string('partition_column_syst'), cell_syst)
            column_syst.set_cell_data_func(cell_syst, self.partman_column_syst)
            column_syst.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            self.partition_list_treeview.append_column(column_syst)

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
            sw = Gtk.ScrolledWindow()
            sw.set_valign(Gtk.Align.FILL)
            self.segmented_bar_vbox = Gtk.Box()
            self.segmented_bar_vbox.set_orientation(Gtk.Orientation.VERTICAL)
            sw.add_with_viewport(self.segmented_bar_vbox)
            sw.get_child().set_shadow_type(Gtk.ShadowType.NONE)
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            sw.show_all()
            self.part_advanced_grid.attach(sw, 0, 0, 1, 1)

        for item in cache_order:
            if item in disk_cache:
                partition_tree_model.append([item, disk_cache[item]])
                dev = disk_cache[item]['device']
                self.partition_bars[dev] = segmented_bar.SegmentedBar()
                partition_bar = self.partition_bars[dev]
                self.segmented_bar_vbox.pack_start(
                    partition_bar, True, True, 0)
                total_size[dev] = 0.0
            else:
                partition_tree_model.append([item, partition_cache[item]])
                cache_parted = partition_cache[item]['parted']
                size = int(cache_parted['size'])
                total_size[dev] = total_size[dev] + size
                fs = cache_parted['fs']
                path = cache_parted['path'].replace('/dev/', '')
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

    def installation_medium_mounted(self, message):
        self.part_advanced_warning_message.set_text(message)
        self.partition_warning_grid.show_all()

    # Crypto Page
    def info_loop(self, unused_widget):
        complete = True
        passw = self.password.get_text()
        vpassw = self.verified_password.get_text()

        if passw != vpassw or not passw:
            complete = False
            self.password_match.set_current_page(
                self.password_match_pages['empty'])
            if passw and (not passw.startswith(vpassw)
                          or len(vpassw) / len(passw) > 0.8):
                self.password_match.set_current_page(
                    self.password_match_pages['mismatch'])
        else:
            self.password_match.set_current_page(
                self.password_match_pages['ok'])

        if passw:
            txt = validation.human_password_strength(passw)[0]
            self.password_strength.set_current_page(
                self.password_strength_pages[txt])
        else:
            self.password_strength.set_current_page(
                self.password_strength_pages['empty'])

        self.controller.allow_go_forward(complete)
        self.partition_dialog_okbutton.set_sensitive(complete)
        return complete

    def get_crypto_keys(self):
        if self.info_loop(None):
            return self.password.get_text()
        else:
            return False


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

    def set_grub_options(self, default, grub_installable):
        options = misc.grub_options()
        self.partMan.setGrubOptions(options, default, grub_installable)

    def get_current_disk_partman_id(self):
        comboText = str(self.partAuto.part_auto_disk_box.currentText())
        if (not comboText or
                comboText not in self.partAuto.extra_options['use_device'][1]):
            return None

        partman_id = self.partAuto.extra_options['use_device'][1][comboText][0]
        disk_id = partman_id.rsplit('/', 1)[1]
        return disk_id

    def get_grub_choice(self):
        choice = self.partMan.getGrubChoice()
        if choice:
            return choice
        else:
            disk = self.get_current_disk_partman_id()
            if isinstance(disk, str) and disk:
                disk_path = disk.replace("=", "/")
                if os.path.exists(disk_path):
                    return misc.grub_default(boot=disk_path)

            return misc.grub_default()

    def set_autopartition_heading(self, heading):
        pass

    def set_autopartition_options(self, options, extra_options):
        use_device = self.controller.dbfilter.some_device_desc
        resize_choice = self.controller.dbfilter.resize_desc
        manual_choice = extra_options['manual']
        lvm_choice = extra_options['some_device_lvm']
        crypto_choice = extra_options['some_device_crypto']

        self.partAuto.setupChoices(None, extra_options,
                                   resize_choice, manual_choice,
                                   None, use_device, lvm_choice, crypto_choice)

        self.current_page = self.page

    def get_autopartition_choice(self):
        return self.partAuto.getChoice()

    def update_partman(self, disk_cache, partition_cache, cache_order):
        self.partMan.update(disk_cache, partition_cache, cache_order)
        # make sure we're on the advanced partitioning page
        self.show_page_advanced()

    def plugin_get_current_page(self):
        return self.current_page

    def get_crypto_keys(self):
        return self.partAuto.password.text()


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
                    with open('/var/run/parted_server.pid') as pidfile:
                        pidline = pidfile.readline()
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
        self.activating_crypto = False
        self.bad_auto_size = False
        self.description_cache = {}
        self.local_progress = False
        self.swap_size = 0

        self.install_bootloader = False
        if (self.db.get('ubiquity/install_bootloader') == 'true' and
                'UBIQUITY_NO_BOOTLOADER' not in os.environ):
            arch, subarch = archdetect()
            if arch in ('amd64', 'i386'):
                self.install_bootloader = True
                self.ui.show_bootloader_options()

        self.installation_size = misc.install_size()

        # TODO: It would be neater to use a wrapper script.
        command = [
            'sh', '-c',
            '/usr/share/ubiquity/activate-dmraid && /bin/partman',
        ]
        questions = [
            '^partman-auto/.*automatically_partition$',
            '^partman-auto/select_disk$',
            '^partman-partitioning/confirm_resize$',
            '^partman-partitioning/confirm_new_label$',
            '^partman-partitioning/new_size$',
            '^partman/choose_partition$',
            '^partman/confirm.*',
            '^partman/free_space$',
            '^partman/active_partition$',
            '^partman-crypto/passphrase.*',
            '^partman-crypto/weak_passphrase$',
            '^partman-crypto/confirm.*',
            '^partman-crypto/mainmenu$',
            '^partman-lvm/confirm.*',
            '^partman-lvm/device_remove_lvm',
            '^partman-partitioning/new_partition_(size|type|place)$',
            '^partman-target/choose_method$',
            ('^partman-basicfilesystems/'
             '(fat_mountpoint|mountpoint|mountpoint_manual)$'),
            '^partman-uboot/mountpoint$',
            '^partman/exception_handler$',
            '^partman/exception_handler_note$',
            '^partman/unmount_active$',
            '^partman/installation_medium_mounted$',
            'type:boolean',
            'ERROR',
            'PROGRESS',
        ]
        environ = {'PARTMAN_NO_COMMIT': '1', 'PARTMAN_SNOOP': '1'}
        return command, questions, environ

    def snoop(self):
        """Read the partman snoop file hack, returning a list of tuples
        mapping from keys to displayed options. (We use a list of tuples
        because this preserves ordering and is reasonably fast to convert to
        a dictionary.)"""

        options = []
        try:
            with open('/var/lib/partman/snoop') as snoop:
                for line in snoop:
                    line = misc.utf8(line.rstrip('\n'), errors='replace')
                    fields = line.split('\t', 1)
                    if len(fields) == 2:
                        (key, option) = fields
                        options.append((key, option))
                        continue
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

    def devpart_disk(self, devpart):
        dev = self.split_devpart(devpart)[0]
        if dev:
            return '%s/%s//' % (parted_server.devices, dev)
        else:
            return None

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
        question = 'partman/method_long/%s' % method
        if method == 'efi':
            question = 'partman-efi/text/efi'
        try:
            return self.description(question)
        except debconf.DebconfError:
            return method

    def filesystem_description(self, filesystem):
        try:
            return self.description('partman/filesystem_long/%s' % filesystem)
        except debconf.DebconfError:
            return filesystem

    def use_as(self, devpart, create, complex_devices=[]):
        """Yields the possible methods that a partition may use.

        If create is True, then only list methods usable on new partitions.
        If complex_devices is a white list of LVM/LUKS/MDAMD devices
        """

        black_list = set(['lvm', 'crypto', 'md'])
        black_list.difference_update(complex_devices)

        # TODO cjwatson 2006-11-01: This is a particular pain; we can't find
        # out the real list of possible uses from partman until after the
        # partition has been created, so we have to partially hardcode this.

        for method in self.subdirectories('/lib/partman/choose_method'):
            if method == 'filesystem':
                for fs in self.scripts('/lib/partman/valid_filesystems'):
                    if fs == 'ntfs':
                        if not create and devpart in self.partition_cache:
                            partition = self.partition_cache[devpart]
                            if partition.get('detected_filesystem') == 'ntfs':
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
            elif method == 'crypto':
                # TODO xnox 2013-04-03 this is a crude way to catch
                # nested crypto devices. Ideally we should transverse
                # parent devices of the devpart and look for
                # $device/crypt_realdev file (this is what partman
                # does). But we don't cache crypt_realdev at the
                # moment.
                if not 'crypt' in devpart:
                    yield (method, method, self.method_description(method))
            elif method == 'biosgrub':
                # TODO cjwatson 2009-09-03: Quick kludge, since only GPT
                # supports this method at the moment. Maybe it would be
                # better to fetch VALID_FLAGS for each partition while
                # building the cache?
                disk = self.devpart_disk(devpart)
                if (disk is not None and disk in self.disk_cache and
                        'label' in self.disk_cache[disk] and
                        self.disk_cache[disk]['label'] == 'gpt'):
                    yield (method, method, self.method_description(method))
            elif method in black_list:
                pass
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

    def build_locked(self, devpart):
        if os.path.exists(os.path.join(devpart, 'locked')):
            self.debug('Partman: %s is locked', devpart)
            self.partition_cache[devpart]['locked'] = True
            return True
        else:
            if 'locked' in self.partition_cache[devpart]:
                del(self.partition_cache[devpart]['locked'])
            return False

    def get_actions(self, devpart, partition):
        if devpart is None and partition is None:
            return
        if 'id' not in partition and partition.get('label', '') != 'loop':
            yield 'new_label'
        if 'can_new' in partition and partition['can_new']:
            yield 'new'
        disk = self.disk_cache.get(
            '/var/lib/partman/devices/%s//' % partition['dev'], {})
        if ('id' in partition and partition['parted']['fs'] != 'free' and
                not partition.get('locked', False)):
            yield 'edit'
            if disk.get('label', '') != 'loop':
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
            elif key == 'SWAPSIZE':
                # Provided in megabytes.
                self.swap_size = int(value) * 1024 * 1024

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
        with open('/lib/partman/%s/no_show_choices' % menu, 'w'):
            pass

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
            elif self.build_free(devpart) or self.build_locked(devpart):
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

        # TODO: verify that ubuntu is the same partition as one of the ones
        #       offered in the reuse options.
        release = misc.get_release()
        if 'reuse' in self.extra_options:
            reuse = self.extra_options['reuse']
            if len(reuse) == 1:
                ubuntu, current_version = misc.find_in_os_prober(
                    reuse[0][1], with_version=True)
                final = current_version in ubuntu
                try:
                    new_version = re.split(
                        ".*([0-9]{2}\.[0-9]{2}).*", release.version)

                    if current_version == '' or len(new_version) < 2:
                        return None

                    new_version = new_version[1]

                except ValueError:
                    return None

                if current_version == new_version and final:
                    # "Windows (or Mac, ...) and the current version of Ubuntu
                    # are present" case
                    q = 'ubiquity/partitioner/ubuntu_reinstall'
                    self.db.subst(q, 'CURDISTRO', ubuntu)
                    title = self.description(q)
                    desc = self.extended_description(q)
                    return PartitioningOption(title, desc)

                if current_version <= new_version:
                    # "Windows (or Mac, ...) and an older version of Ubuntu are
                    # present" case

                    # Only allow reuse with newer install media
                    # also block reuse when invalid version number or codename

                    q = 'ubiquity/partitioner/ubuntu_upgrade'
                    self.db.subst(q, 'CURDISTRO', ubuntu)
                    self.db.subst(
                        q, 'VER', "%s %s" % (release.name, release.version))
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
        ubuntu_systems = [x for x in operating_systems
                          if x.lower().find('buntu') != -1]
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
        if not operating_systems:
            operating_systems = []
        if not ubuntu_systems:
            ubuntu_systems = []
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

        # Irrespective of os_counts
        # We always have the manual partitioner, and it always has the same
        # title and description.
        q = 'ubiquity/partitioner/advanced'
        self.db.subst(q, 'DISTRO', release.name)
        title = self.description(q)
        desc = self.extended_description(q)
        options['manual'] = PartitioningOption(title, desc)

        # Panda board without SD-card does not have use_device options
        # quit here for now
        if 'use_device' not in self.extra_options:
            return options

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
            ubuntu = ubuntu_systems[0]
            if 'replace' in self.extra_options:
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
                self.some_device_lvm_desc = \
                    self.description('partman-auto-lvm/text/choice')
                self.some_device_crypto_desc = \
                    self.description('partman-auto-crypto/text/choice')
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
            ntfs_partitions = []

            with misc.raised_privileges():
                # {'/dev/sda' : ('/dev/sda1', 24973242, '32256-2352430079'),
                # ...
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

                        if partition[4] == 'ntfs':
                            ntfs_partitions.append(partition[5])

                    layout[disk] = ret
                    if try_for_wubi and partition_table_full:
                        if (max_primary is not None and
                                primary_count >= max_primary and
                                ntfs_count > 0):
                            pass
                        else:
                            partition_table_full = False

                # TODO try the wubi check as a partman-auto choice.
                if try_for_wubi and partition_table_full:
                    import tempfile
                    import subprocess
                    mount_path = tempfile.mkdtemp()
                    for device in ntfs_partitions:
                        try:
                            subprocess.check_call(
                                ['mount', device, mount_path])
                            if misc.windows_startup_folder(mount_path):
                                self.extra_options['wubi'] = device
                                break
                        except subprocess.CalledProcessError:
                            pass
                        finally:
                            subprocess.call(['umount', '-l', mount_path])
                    if os.path.exists(mount_path):
                        os.rmdir(mount_path)

                biggest_free = self.find_script(menu_options, 'biggest_free')
                if biggest_free:
                    dev, p_id = self.split_devpart(biggest_free[0][1])
                    parted.select_disk(dev)
                    size = int(parted.partition_info(p_id)[2])
                    key = biggest_free[0][2]
                    if size > self.installation_size:
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

                some_device_lvm = self.find_script(menu_options,
                                                   'some_device_lvm')
                if some_device_lvm:
                    self.extra_options['some_device_lvm'] = \
                        self.some_device_lvm_desc

                some_device_crypto = self.find_script(menu_options,
                                                      'some_device_crypto')
                if some_device_crypto:
                    self.extra_options['some_device_crypto'] = \
                        self.some_device_crypto_desc

            # We always have the manual option.
            self.extra_options['manual'] = self.manual_desc
            self.ui.set_disk_layout(layout)
            self.ui.set_default_filesystem(
                self.db.get('partman/default_filesystem'))

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
                disks = OrderedDict()
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
                self.extra_options['use_device'] = (
                    self.some_device_desc, disks)
                # Back up to autopartitioning question.
                self.succeeded = False
                return False
            else:
                assert self.extra_choice is not None
                self.preseed_as_c(question, self.extra_choice, seen=False)
                self.succeeded = True
                return True

        elif question == 'partman/choose_partition':
            self.autopartition_question = None  # not autopartitioning any more

            if 'manual' not in self.extra_options:
                # Couldn't autopartition hence the partAsk page was skipped.
                self.extra_options['manual'] = self.manual_desc
                options = self.calculate_autopartitioning_options(False, False)
                self.ui.set_autopartition_options(options, self.extra_options)
                if hasattr(self.ui, 'plugin_on_next_clicked'):
                    self.ui.plugin_on_next_clicked()
                # Here be dragons...
                self.preseed('ubiquity/partman-skip-unmount', 'true',
                             seen=False)

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
                            # We don't get a separate notification when a
                            # disk label is changed, only a notification
                            # about the free-space slot covering the whole
                            # disk.  Therefore, clear the corresponding disk
                            # from the disk cache just in case its label has
                            # changed.
                            disk = self.devpart_disk(devpart)
                            if disk and disk in self.disk_cache:
                                del self.disk_cache[disk]

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
                                    label = parted.read_line()[0]
                                finally:
                                    parted.close_dialog()
                                self.disk_cache[arg] = {
                                    'dev': dev,
                                    'device': device,
                                    'label': label
                                }

                    if self.update_partitions is None:
                        self.update_partitions = list(
                            self.partition_cache.keys())
                    else:
                        self.update_partitions = [
                            devpart for devpart in self.update_partitions
                            if devpart in self.partition_cache]

                    # Update the display names of all disks and partitions.
                    for script, arg, option in matches:
                        dev, part_id = self.split_devpart(arg)
                        if not dev:
                            continue
                        parted.select_disk(dev)
                        if part_id:
                            self.partition_cache[arg]['display'] = (
                                '%s__________%s' % (script, arg))
                        else:
                            self.disk_cache[arg]['display'] = (
                                '%s__________%s' % (script, arg))

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
                    self.progress_start(
                        0, len(self.update_partitions),
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
                raise AssertionError(
                    "Deleting partition didn't rebuild cache?")

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

            if self.activating_crypto:
                self.preseed_script(question, menu_options, 'crypto')
                return True

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
                if response == 'ubiquity/text/continue':
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

                # This makes crypto appear in the edit dialog,
                # possibly with frontend not doing anything useful
                # with it.
                partition['method_choices'] = []
                for use in self.use_as(state[1],
                                       partition['parted']['fs'] == 'free',
                                       ['crypto']):
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
                    if response == 'ubiquity/text/continue':
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
                if response == 'ubiquity/text/continue':
                    self.preseed(question, 'true', seen=False)
                else:
                    self.preseed(question, 'false', seen=False)
                return True
            else:
                raise AssertionError("Arrived at %s unexpectedly" % question)

        elif question == 'partman-partitioning/new_size':
            if self.autopartition_question is not None:
                if self.auto_state is not None:
                    p_id = self.translate_to_c(
                        self.autopartition_question, self.auto_state[1])
                    p_id = p_id.rsplit('//')[1]
                    disk = self.translate_to_c(
                        self.autopartition_question, self.auto_state[1])
                    disk = re.search(
                        '/var/lib/partman/devices/(.*)//', disk).group(1)
                    with misc.raised_privileges():
                        parted = parted_server.PartedServer()
                        parted.select_disk(disk)
                        size = int(parted.partition_info(p_id)[2])
                        fs = parted.partition_info(p_id)[4]

                    # The resize path will use the selected size as the amount
                    # of space to create *all* the needed partitions, currently
                    # / and swap. Make sure everything will fit.
                    real_min_size = self.resize_min_size + self.swap_size

                    # The installation is bigger than the minimum value we
                    # would normally present.
                    if real_min_size < self.installation_size:
                        self.resize_min_size = (
                            self.installation_size + self.swap_size)
                        # Readjust the preferred size.
                        self.resize_pref_size = (
                            self.resize_min_size +
                            (self.resize_max_size - self.resize_min_size) / 2)

                    too_big = False
                    if self.resize_min_size > self.resize_max_size:
                        # We wont fit here, so don't use this partition.
                        self.debug('%s is too small', self.resize_path)
                        too_big = True

                    needed_space = self.swap_size + self.installation_size
                    if not too_big and self.resize_max_size > needed_space:
                        if 'resize' not in self.extra_options:
                            self.extra_options['resize'] = {}
                        self.extra_options['resize'][disk] = \
                            (self.auto_state[1], self.resize_min_size,
                             self.resize_max_size, self.resize_pref_size,
                             self.resize_path, size, fs)

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

        elif (question.startswith('partman-lvm/confirm') or
              question.startswith('partman-crypto/confirm') or
              question == 'partman-lvm/device_remove_lvm'):
            self.preseed_bool(question, True, seen=False)
            self.succeeded = True
            return True

        elif question == 'partman-crypto/weak_passphrase':
            self.preseed_bool(question, True, seen=False)
            return True

        elif question.startswith('partman-crypto/passphrase'):
            if not self.ui.get_crypto_keys():
                return False
            self.preseed(question, self.ui.get_crypto_keys())
            return True

        elif question == 'partman-crypto/mainmenu':
            if self.activating_crypto:
                self.activating_crypto = False
                self.preseed_script(question, menu_options, 'finish')
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
            if response == yes:
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
        if self.install_bootloader and not self.is_bootdev_preseeded():
            self.preseed('grub-installer/bootdev', self.ui.get_grub_choice())

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

    def is_bootdev_preseeded(self):
        return (self.is_automatic and
                self.db.fget('grub-installer/bootdev', 'seen') == 'true')

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
        self.activating_crypto = method == 'crypto'
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
        self.activating_crypto = method == 'crypto'
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
            plugin.Plugin.progress_start(
                self, progress_min, progress_max, progress_title)

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
        if not self.install_bootloader:
            return
        paths = [part[0] for part in misc.grub_options()]
        # Get the default boot device.
        if self.is_bootdev_preseeded():
            grub_bootdev = self.db.get("grub-installer/bootdev")
        else:
            grub_bootdev = self.ui.get_grub_choice()
        if grub_bootdev and grub_bootdev in paths:
            default = grub_bootdev
        else:
            default = misc.grub_default()
        # Create a reverse mapping from grub options device path to the file
        # system type being installed on that option.  Then later we'll make
        # sure that grub can actually be installed on that path's file system.
        fstype_by_path = {}
        for key, value in self.partition_cache.items():
            path = value.get('parted', {}).get('path')
            fstype = value.get('parted', {}).get('fs', 'free')
            if path is not None:
                # Duplicate paths should not be possible, but if we find one,
                # the first one (<wink>, i.e. random) wins.
                if path in fstype_by_path:
                    self.debug('already found path %s with type %s',
                               path, fstype_by_path[path])
                else:
                    fstype_by_path[path] = fstype
        if default.startswith('/'):
            default = os.path.realpath(default)
        # Now, create a dictionary mapping boot device path to a flag
        # indicating whether grub can or cannot be installed on that path's
        # file system.  Use 'free' as a default since grub can never be
        # installed on free space.
        grub_installable = {}
        for path in paths:
            fstype = fstype_by_path.get(path, 'free')
            can_install = fstype in FS_RESERVED_FIRST_SECTOR
            grub_installable[path] = can_install
            self.debug('device path: %s, fstype: %s, grub installable? %s',
                       path, fstype, 'yes' if can_install else 'no')
        # Let grub offer to install to all the disk devices.
        for key, value in self.disk_cache.items():
            device = value.get('device')
            if device is not None:
                grub_installable[device] = True
                self.debug('device path: %s grub installable? yes', device)
        self.ui.set_grub_options(default, grub_installable)

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
