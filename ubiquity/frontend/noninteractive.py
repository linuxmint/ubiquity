# -*- coding: utf-8 -*-
#
# «noninteractive» - Non-interactive user interface
#
# Copyright (C) 2007, 2008 Canonical Ltd.
#
# Authors:
#
# - Evan Dandrea <evand@ubuntu.com>
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or at your option)
# any later version.
#
# Ubiquity is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with Ubiquity; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import syslog

import gobject

import getpass
import os
import sys
import signal

from ubiquity import filteredcommand, i18n
from ubiquity.misc import *
from ubiquity.components import console_setup, language, timezone, usersetup, \
                                partman, partman_commit, \
                                summary, install, migrationassistant
import ubiquity.progressposition
from ubiquity.frontend.base import BaseFrontend
import debconf

class Wizard(BaseFrontend):

    def __init__(self, distro):
        BaseFrontend.__init__(self, distro)

        self.installing = False
        self.progress_position = ubiquity.progressposition.ProgressPosition()
        self.fullname = ''
        self.username = ''
        self.password = ''
        self.verifiedpassword = ''
        self.progress_val = 0
        self.progress_info = ''
        self.auto_login = False
        self.encrypt_home = False
        self.mainloop = gobject.MainLoop()

        dbfilter = language.Language(self, self.debconf_communicator())
        dbfilter.cleanup()
        dbfilter.db.shutdown()

        if self.oem_config:
            execute_root('apt-install', 'oem-config-gtk')

    def run(self):
        """Main entry point."""
        # Is this even needed anymore now that Ubiquity elevates its
        # privileges?
        if os.getuid() != 0:
            print 'This installer must be run with administrative ' \
                'privileges, and cannot continue without them.'
            sys.exit(1)

        if 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
            pages = [language.Language, timezone.Timezone,
                console_setup.ConsoleSetup, partman.Partman,
                migrationassistant.MigrationAssistant, usersetup.UserSetup,
                summary.Summary]
        else:
            pages = [language.Language, timezone.Timezone,
                console_setup.ConsoleSetup, partman.Partman,
                usersetup.UserSetup, summary.Summary]

        for x in pages:
            self.dbfilter = x(self)
            self.dbfilter.start(auto_process=True)
            self.mainloop.run()
            if self.dbfilter_status:
                sys.exit(1)

        self.installing = True
        self.progress_loop()

    def progress_loop(self):
        """prepare, copy and config the system in the core install process."""

        dbfilter = partman_commit.PartmanCommit(self)
        if dbfilter.run_command(auto_process=True) != 0:
            print '\nUnable to commit the partition table, exiting.'
            return
        
        dbfilter = install.Install(self)
        ret = dbfilter.run_command(auto_process=True)
        if ret != 0:
            if ret == 3:
                # error already handled by Install
                sys.exit(ret)
            elif (os.WIFSIGNALED(ret) and
                  os.WTERMSIG(ret) in (signal.SIGINT, signal.SIGKILL,
                                       signal.SIGTERM)):
                sys.exit(ret)
            elif os.path.exists('/var/lib/ubiquity/install.trace'):
                tbfile = open('/var/lib/ubiquity/install.trace')
                realtb = tbfile.read()
                tbfile.close()
                raise RuntimeError, ("Install failed with exit code %s\n%s" %
                                     (ret, realtb))
        else:
            self.run_success_cmd()
            print 'Installation complete.'
            if self.get_reboot():
                execute("reboot")

    def watch_debconf_fd(self, from_debconf, process_input):
        """Event loop interface to debconffilter.

        A frontend typically provides its own event loop. When a
        debconffiltered command is running, debconffilter must be given an
        opportunity to process input from that command as it arrives. This
        method will be called with from_debconf as a file descriptor reading
        from the filtered command and a process_input callback which should
        be called when input events are received."""
        
        gobject.io_add_watch(from_debconf,
                             gobject.IO_IN | gobject.IO_ERR | gobject.IO_HUP,
                             self.watch_debconf_fd_helper, process_input)


    def watch_debconf_fd_helper (self, source, cb_condition, callback):
        debconf_condition = 0
        if (cb_condition & gobject.IO_IN) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_IN
        if (cb_condition & gobject.IO_ERR) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_ERR
        if (cb_condition & gobject.IO_HUP) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_HUP

        return callback(source, debconf_condition)

    def debconffilter_done(self, dbfilter):
        if BaseFrontend.debconffilter_done(self, dbfilter):
            if self.mainloop.is_running():
                self.mainloop.quit()
            return True
        else:
            return False

    def refresh(self):
        """Take the opportunity to process pending items in the event loop."""
        pass

    def run_main_loop(self):
        """Block until the UI returns control."""
        if self.dbfilter is not None:
            self.dbfilter.ok_handler()
        elif self.mainloop.is_running():
            self.mainloop.quit()
        else:
            self.mainloop.run()

    def quit_main_loop(self):
        """Return control blocked in run_main_loop."""
        if not self.dbfilter and self.mainloop.is_running():
            self.mainloop.quit()
    
    def set_page(self, page):
        # There's no need to do anything here as there's no interface to speak
        # of.
        pass

    # Progress bar handling.

    def debconf_progress_start(self, progress_min, progress_max,
                               progress_title):
        """Start a progress bar. May be nested."""
        return

    def debconf_progress_set(self, progress_val):
        """Set the current progress bar's position to progress_val."""
        self.progress_val = progress_val
        print '%d%%: %s' % (self.progress_val, self.progress_info)
        return True

    def debconf_progress_step(self, progress_inc):
        """Increment the current progress bar's position by progress_inc."""
        return True

    def debconf_progress_info(self, progress_info):
        """Set the current progress bar's message to progress_info."""
        self.progress_info = progress_info
        print '%d%%: %s' % (self.progress_val, self.progress_info)
        return True

    def debconf_progress_stop(self):
        """Stop the current progress bar."""
        return

    def debconf_progress_region(self, region_start, region_end):
        """Confine nested progress bars to a region of the current bar."""
        pass

    def debconf_progress_cancellable(self, cancellable):
        """Control whether the current progress bar may be cancelled."""
        pass

    # Interfaces with various components. If a given component is not used
    # then its abstract methods may safely be left unimplemented.

    # ubiquity.components.language

    def set_language_choices(self, choices, choice_map):
        """Called with language choices and a map to localised names."""
        # FIXME needed?
        self.language_choice_map = dict(choice_map)

    def set_language(self, language):
        """Set the current selected language."""
        self.language = language

    def get_language(self):
        """Get the current selected language."""
        return self.language
    
    # ubiquity.components.timezone

    def set_timezone(self, timezone):
        """Set the current selected timezone."""
        self.timezone = timezone

    def get_timezone(self):
        """Get the current selected timezone."""
        return self.timezone

    # ubiquity.components.console_setup

    def set_keyboard_choices(self, choices):
        """Set the available keyboard layout choices."""
        pass

    def set_keyboard(self, layout):
        """Set the current keyboard layout."""
        self.current_layout = layout

    def get_keyboard(self):
        """Get the current keyboard layout."""
        return self.current_layout

    def set_keyboard_variant_choices(self, choices):
        """Set the available keyboard variant choices."""
        pass

    def set_keyboard_variant(self, variant):
        """Set the current keyboard variant."""
        self.keyboard_variant = variant

    def get_keyboard_variant(self):
        #print '*** get_keyboard_variant'
        return self.keyboard_variant

    # ubiquity.components.partman

    def set_disk_layout(self, layout):
        pass

    def set_autopartition_choices(self, choices, extra_options,
                                  resize_choice, manual_choice,
                                  biggest_free_choice):
        """Set available autopartitioning choices."""
        BaseFrontend.set_autopartition_choices(self, choices, extra_options,
            resize_choice, manual_choice, biggest_free_choice)

    def get_autopartition_choice(self):
        """Get the selected autopartitioning choice."""
        #print '*** get_autopartition_choice'

    # ubiquity.components.partman_commit

    def return_to_partitioning(self):
        """Return to partitioning following a commit error."""
        print '\nCommit failed on partitioning.  Exiting.'
        sys.exit(1)

    # ubiquity.components.migrationassistant

    # FIXME: Needed by m-a, but is it really necessary?
    def allow_go_forward(self, allow):
        pass

    def ma_set_choices(self, choices):
        """Set the available migration-assistant choices."""
        self.ma_choices = choices

    def ma_get_choices(self):
        """Get the selected migration-assistant choices."""
        return (self.ma_choices, {})

    def ma_user_error(self, error, user):
        """The selected migration-assistant username was bad."""
        print '\nError: %s: %s' % (user, error)

    def ma_password_error(self, error, user):
        """The selected migration-assistant password was bad."""
        print '\nError: %s: %s' % (user, error)

    # ubiquity.components.usersetup

    def set_fullname(self, value):
        """Set the user's full name."""
        self.fullname = value

    def get_fullname(self):
        """Get the user's full name."""
        if self.oem_config:
            return 'OEM Configuration (temporary user)'
        return self.fullname

    def set_username(self, value):
        """Set the user's Unix user name."""
        self.username = value

    def get_username(self):
        """Get the user's Unix user name."""
        if self.oem_config:
            return 'oem'
        return self.username

    def get_password(self):
        """Get the user's password."""
        return self.dbfilter.db.get('passwd/user-password') #self.password

    def get_verified_password(self):
        """Get the user's password confirmation."""
        return self.dbfilter.db.get('passwd/user-password-again') #self.verifiedpassword

    def set_auto_login(self, value):
        self.auto_login = value

    def get_auto_login(self):
        return self.auto_login
    
    def set_encrypt_home(self, value):
        self.encrypt_home = value

    def get_encrypt_home(self):
        return self.encrypt_home

    def username_error(self, msg):
        """The selected username was bad."""
        print '\nusername error: %s' % msg
        self.username = raw_input('Username: ')

    def password_error(self, msg):
        """The selected password was bad."""
        print '\nBad password: %s' % msg
        self.password = getpass.getpass('Password: ')
        self.verifiedpassword = getpass.getpass('Password again: ')

    # typically part of the usersetup UI but actually called from
    # ubiquity.components.install
    def get_hostname(self):
        """Get the selected hostname."""
        #We set a default in install.py in case it isn't preseeded
        #but when we preseed, we are looking for None anyhow.
        return None

    # ubiquity.components.summary

    def set_summary_text(self, text):
        """Set text to be displayed in the installation summary."""
        pass

    def set_summary_device(self, device):
        """Set the GRUB device. A hack until we have something better."""
        if device is not None:
            if not device.startswith('(') and not device.startswith('/dev/'):
                device = '/dev/%s' % device
        self.summary_device = device

    # called from ubiquity.components.install
    def get_grub(self):
        # Always return true as there's no UI to disable it.
        # FIXME: Better to grab grub-installer/skip out of debconf?
        return True

    def get_summary_device(self):
        """Get the selected GRUB device."""
        return self.summary_device

    def set_popcon(self, participate):
        """Set whether to participate in popularity-contest."""
        self.popcon = participate

    # called from ubiquity.components.install
    def get_popcon(self):
        """Get whether to participate in popularity-contest."""
        return self.popcon

    # General facilities for components.

    def error_dialog(self, title, msg, fatal=True):
        """Display an error message dialog."""
        print '\n%s: %s' % (title, msg)

    def question_dialog(self, title, msg, options, use_templates=True):
        """Ask a question."""
        self._abstract('question_dialog')
