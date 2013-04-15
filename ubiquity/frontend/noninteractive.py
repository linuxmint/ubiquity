# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# «noninteractive» - Non-interactive user interface
#
# Copyright (C) 2007, 2008 Canonical Ltd.
#
# Authors:
#
# - Evan Dandrea <ev@ubuntu.com>
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

from __future__ import print_function

import os
import signal
import sys

from gi.repository import GLib

from ubiquity import filteredcommand, i18n, misc
from ubiquity.components import install, plugininstall, partman_commit
import ubiquity.frontend.base
from ubiquity.frontend.base import BaseFrontend
from ubiquity.plugin import Plugin
import ubiquity.progressposition


class Wizard(BaseFrontend):
    def __init__(self, distro):
        BaseFrontend.__init__(self, distro)

        with misc.raised_privileges():
            self.console = open('/dev/console', 'w')
        if not self.console:
            self.console = sys.stdout  # better than crashing
        self.installing = False
        self.progress_position = ubiquity.progressposition.ProgressPosition()
        self.progress_val = 0
        self.progress_info = ''
        self.mainloop = GLib.MainLoop()

        self.pages = []
        for mod in self.modules:
            if hasattr(mod.module, 'PageNoninteractive'):
                mod.controller = ubiquity.frontend.base.Controller(self)
                mod.ui_class = mod.module.PageNoninteractive
                mod.ui = mod.ui_class(mod.controller)
                self.pages.append(mod)

        i18n.reset_locale(self)

        if self.oem_config:
            misc.execute_root('apt-install', 'oem-config-gtk')

    def run(self):
        """Main entry point."""
        # Is this even needed anymore now that Ubiquity elevates its
        # privileges?
        if os.getuid() != 0:
            print('This installer must be run with administrative '
                  'privileges, and cannot continue without them.',
                  file=self.console)
            sys.exit(1)

        for x in self.pages:
            if issubclass(x.filter_class, Plugin):
                ui = x.ui
            else:
                ui = None
            self.start_debconf()
            self.dbfilter = x.filter_class(self, ui=ui)
            self.dbfilter.start(auto_process=True)
            self.mainloop.run()
            if self.dbfilter_status:
                sys.exit(1)

        self.installing = True
        self.progress_loop()

    def progress_loop(self):
        """Prepare, copy and configure the system."""
        self.start_debconf()
        dbfilter = partman_commit.PartmanCommit(self)
        if dbfilter.run_command(auto_process=True) != 0:
            print('\nUnable to commit the partition table, exiting.',
                  file=self.console)
            return

        self.start_debconf()
        dbfilter = install.Install(self)
        ret = dbfilter.run_command(auto_process=True)
        if ret == 0:
            dbfilter = plugininstall.Install(self)
            ret = dbfilter.run_command(auto_process=True)
        if ret == 0:
            self.run_success_cmd()
            print('Installation complete.', file=self.console)
            if self.get_reboot():
                misc.execute("reboot")
        if ret != 0:
            if ret == 3:
                # error already handled by Install
                sys.exit(ret)
            elif (os.WIFSIGNALED(ret) and
                  os.WTERMSIG(ret) in (signal.SIGINT, signal.SIGKILL,
                                       signal.SIGTERM)):
                sys.exit(ret)
            elif os.path.exists('/var/lib/ubiquity/install.trace'):
                with open('/var/lib/ubiquity/install.trace') as tbfile:
                    realtb = tbfile.read()
                raise RuntimeError("Install failed with exit code %s\n%s" %
                                  (ret, realtb))

    def watch_debconf_fd(self, from_debconf, process_input):
        """Event loop interface to debconffilter.

        A frontend typically provides its own event loop. When a
        debconffiltered command is running, debconffilter must be given an
        opportunity to process input from that command as it arrives. This
        method will be called with from_debconf as a file descriptor reading
        from the filtered command and a process_input callback which should
        be called when input events are received."""

        GLib.io_add_watch(from_debconf,
                          GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP,
                          self.watch_debconf_fd_helper, process_input)

    def watch_debconf_fd_helper(self, source, cb_condition, callback):
        debconf_condition = 0
        if (cb_condition & GLib.IO_IN) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_IN
        if (cb_condition & GLib.IO_ERR) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_ERR
        if (cb_condition & GLib.IO_HUP) != 0:
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
        return True

    # Progress bar handling.

    def debconf_progress_start(self, progress_min, progress_max,
                               progress_title):
        """Start a progress bar. May be nested."""
        return

    def debconf_progress_set(self, progress_val):
        """Set the current progress bar's position to progress_val."""
        self.progress_val = progress_val
        print('%d%%: %s' % (self.progress_val, self.progress_info),
              file=self.console)
        return True

    def debconf_progress_step(self, progress_inc):
        """Increment the current progress bar's position by progress_inc."""
        return True

    def debconf_progress_info(self, progress_info):
        """Set the current progress bar's message to progress_info."""
        self.progress_info = progress_info
        print('%d%%: %s' % (self.progress_val, self.progress_info),
              file=self.console)
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

    # ubiquity.components.partman_commit

    def return_to_partitioning(self):
        """Return to partitioning following a commit error."""
        print('\nCommit failed on partitioning.  Exiting.', file=self.console)
        sys.exit(1)

    # General facilities for components.

    def error_dialog(self, title, msg, fatal=True):
        """Display an error message dialog."""
        print('\n%s: %s' % (title, msg), file=self.console)

    def question_dialog(self, unused_title, unused_msg, unused_options,
                        use_templates=True):
        """Ask a question."""
        self._abstract('question_dialog')
