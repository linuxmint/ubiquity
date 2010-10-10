# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005 Junta de Andalucía
# Copyright (C) 2005, 2006, 2007, 2008 Canonical Ltd.
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

import sys
import os
import syslog

import debconf
from ubiquity.debconfcommunicator import DebconfCommunicator
from ubiquity.misc import drop_privileges, execute_root
from ubiquity import i18n
from ubiquity import plugin_manager

# Lots of intentionally unused arguments here (abstract methods).
__pychecker__ = 'no-argsused'

class Controller:
    def __init__(self, wizard):
        self._wizard = wizard
        self.dbfilter = None
        self.oem_config = wizard.oem_config
        self.oem_user_config = wizard.oem_user_config

        # For summary and install.
        self.get_grub = wizard.get_grub
        self.set_grub = wizard.set_grub
        self.get_popcon = wizard.get_popcon
        self.set_popcon = wizard.set_popcon
        self.set_proxy_host = wizard.set_proxy_host
        self.set_proxy_port = wizard.set_proxy_port
        self.get_proxy = wizard.get_proxy

    def translate(self, lang=None, just_me=True, not_me=False, reget=False):
        pass
    def allow_go_forward(self, allowed):
        pass
    def allow_go_backward(self, allowed):
        pass
    def allow_change_step(self, allowed):
        pass
    def allowed_change_step(self):
        pass
    def go_forward(self):
        pass
    def go_backward(self):
        pass
    def toggle_top_level(self):
        pass

class Component:
    def __init__(self):
        self.module = None
        self.controller = None
        self.filter_class = None
        self.ui_class = None
        self.ui = None

class BaseFrontend:
    """Abstract ubiquity frontend.

    This class consists partly of facilities shared among frontends, and
    partly of documentation of what methods a frontend must implement. A
    frontend must implement all methods whose bodies are declared using
    self._abstract() here, and may want to extend others."""

    # Core infrastructure.

    def __init__(self, distro):
        """Frontend initialisation."""
        self.distro = distro
        self.db = None
        self.dbfilter = None
        self.dbfilter_status = None
        self.resize_choice = None
        self.manual_choice = None
        self.grub_en = None
        self.popcon = None
        self.locale = None
        self.http_proxy_host = None
        self.http_proxy_port = 8080

        # Drop privileges so we can run the frontend as a regular user, and
        # thus talk to a11y applications running as a regular user.
        drop_privileges()

        self.start_debconf()

        self.oem_user_config = False
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
          self.oem_user_config = True

        try:
            self.custom_title = self.db.get('ubiquity/custom_title_text')
        except debconf.DebconfError:
            self.custom_title = False

        self.oem_config = False
        if not self.oem_user_config:
            try:
                if self.db.get('oem-config/enable') == 'true':
                    self.oem_config = True
                    # It seems unlikely that anyone will need
                    # migration-assistant in the OEM installation process. If it
                    # turns out that they do, just delete the following two
                    # lines.
                    if 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
                        del os.environ['UBIQUITY_MIGRATION_ASSISTANT']
            except debconf.DebconfError:
                pass

            if self.oem_config:
                try:
                    self.db.set('passwd/auto-login', 'true')
                    self.db.set('passwd/auto-login-backup', 'oem')
                except debconf.DebconfError:
                    pass

        # set commands
        # Note that this will never work if the database is locked, so you
        # cannot trap that particular error using failure_command.
        self.automation_error_cmd = ''
        self.error_cmd = ''
        self.success_cmd = ''
        try:
            self.automation_error_cmd = self.db.get(
                'ubiquity/automation_failure_command')
            self.error_cmd = self.db.get('ubiquity/failure_command')
            self.success_cmd = self.db.get('ubiquity/success_command')
        except debconf.DebconfError:
            pass

        # Load plugins
        plugins = plugin_manager.load_plugins()
        modules = plugin_manager.order_plugins(plugins)
        self.modules = []
        for mod in modules:
            if mod.NAME == 'migrationassistant' and \
                'UBIQUITY_MIGRATION_ASSISTANT' not in os.environ:
                    continue
            comp = Component()
            comp.module = mod
            if hasattr(mod, 'Page'):
                comp.filter_class = mod.Page
            self.modules.append(comp)

        if not self.modules:
            raise ValueError, 'No valid steps.'

        if 'SUDO_USER' in os.environ:
            os.environ['SCIM_USER'] = os.environ['SUDO_USER']
            os.environ['SCIM_HOME'] = os.path.expanduser(
                '~%s' % os.environ['SUDO_USER'])

    def _abstract(self, method):
        raise NotImplementedError("%s.%s does not implement %s" %
                                  (self.__class__.__module__,
                                   self.__class__.__name__, method))

    def run(self):
        """Main entry point."""
        self._abstract('run')

    def get_string(self, name, lang=None, prefix=None):
        """Get the string name in the given lang or a default."""
        if lang is None:
            lang = self.locale
        if lang is None and 'LANG' in os.environ:
            lang = os.environ['LANG']
        return i18n.get_string(name, lang, prefix)

    def watch_debconf_fd(self, from_debconf, process_input):
        """Event loop interface to debconffilter.

        A frontend typically provides its own event loop. When a
        debconffiltered command is running, debconffilter must be given an
        opportunity to process input from that command as it arrives. This
        method will be called with from_debconf as a file descriptor reading
        from the filtered command and a process_input callback which should
        be called when input events are received."""

        self._abstract('watch_debconf_fd')

    def debconffilter_done(self, dbfilter):
        """Called when an asynchronous debconffiltered command exits.

        Returns True if the exiting command is self.dbfilter; frontend
        implementations may wish to do something special (such as exiting
        their main loop) in this case."""

        if dbfilter is None:
            name = 'None'
            self.dbfilter_status = None
        else:
            name = dbfilter.__module__
            if dbfilter.status:
                self.dbfilter_status = (name, dbfilter.status)
            else:
                self.dbfilter_status = None
        if self.dbfilter is None:
            currentname = 'None'
        else:
            currentname = self.dbfilter.__module__
        syslog.syslog(syslog.LOG_DEBUG,
                      "debconffilter_done: %s (current: %s)" %
                      (name, currentname))
        if dbfilter == self.dbfilter:
            self.dbfilter = None
            return True
        else:
            return False

    def refresh(self):
        """Take the opportunity to process pending items in the event loop."""
        pass

    def run_main_loop(self):
        """Block until the UI returns control."""
        pass

    def quit_main_loop(self):
        """Return control blocked in run_main_loop."""
        pass

    def post_mortem(self, exctype, excvalue, exctb):
        """Drop into the debugger if possible."""
        self.run_error_cmd()

        # Did the user request this?
        if 'UBIQUITY_DEBUG_PDB' not in os.environ:
            return
        # We must not be in interactive mode; if we are, there's no point.
        if hasattr(sys, 'ps1'):
            return
        # stdin and stdout must point to a terminal. (stderr is redirected
        # in debug mode!)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return
        # SyntaxErrors can't meaningfully be debugged.
        if issubclass(exctype, SyntaxError):
            return

        import pdb
        pdb.post_mortem(exctb)
        sys.exit(1)

    def set_page(self, page):
        """A question has been asked.  Set the interface to the appropriate
        page given the component, page."""
        self._abstract('set_page')

    # Debconf interaction. We cannot talk to debconf normally here, as
    # running a normal frontend would interfere with pretending to be a
    # frontend for components, but we can start up a debconf-communicate
    # instance on demand.

    def debconf_communicator(self):
        return DebconfCommunicator('ubiquity', cloexec=True)

    def start_debconf(self):
        """Start debconf-communicator if it isn't already running."""
        if self.db is None:
            self.db = self.debconf_communicator()

    def stop_debconf(self):
        """Stop debconf-communicator if it's running."""
        if self.db is not None:
            self.db.shutdown()
            self.db = None

    def debconf_operation(self, command, *params):
        self.start_debconf()
        return getattr(self.db, command)(*params)

    # Progress bar handling.

    def debconf_progress_start(self, progress_min, progress_max,
                               progress_title):
        """Start a progress bar. May be nested."""
        self._abstract('debconf_progress_start')

    def debconf_progress_set(self, progress_val):
        """Set the current progress bar's position to progress_val."""
        self._abstract('debconf_progress_set')

    def debconf_progress_step(self, progress_inc):
        """Increment the current progress bar's position by progress_inc."""
        self._abstract('debconf_progress_step')

    def debconf_progress_info(self, progress_info):
        """Set the current progress bar's message to progress_info."""
        self._abstract('debconf_progress_info')

    def debconf_progress_stop(self):
        """Stop the current progress bar."""
        self._abstract('debconf_progress_stop')

    def debconf_progress_region(self, region_start, region_end):
        """Confine nested progress bars to a region of the current bar."""
        self._abstract('debconf_progress_region')

    def debconf_progress_cancellable(self, cancellable):
        """Control whether the current progress bar may be cancelled."""
        pass

    # Interfaces with various components. If a given component is not used
    # then its abstract methods may safely be left unimplemented.

    # ubiquity.components.summary

    def set_grub(self, enable):
        """Sets whether we will be installing GRUB."""
        self.grub_en = enable

    # called from ubiquity.components.install
    def get_grub(self):
        """Returns whether we will be installing GRUB."""
        return self.grub_en

    def get_popcon(self):
        return self.popcon

    def set_popcon(self, participate):
        """Set whether to participate in popularity-contest."""
        self.popcon = participate

    def set_proxy_host(self, host):
        """Set the HTTP proxy host."""
        self.http_proxy_host = host

    def set_proxy_port(self, port):
        """Set the HTTP proxy port."""
        self.http_proxy_port = port

    # called from ubiquity.components.install
    def get_proxy(self):
        """Get the selected HTTP proxy."""
        if self.http_proxy_host:
            return 'http://%s:%s/' % (self.http_proxy_host,
                                      self.http_proxy_port)
        else:
            return None

    def set_reboot(self, reboot):
        """Set whether to reboot automatically when the install completes."""
        self.reboot_after_install = reboot

    def get_reboot(self):
        return self.reboot_after_install

    def get_reboot_seen(self):
        reboot_seen = 'false'
        try:
            reboot_seen = self.debconf_operation('fget', 'ubiquity/reboot',
                'seen')
        except debconf.DebconfError:
            pass
        if reboot_seen == 'false':
            return False
        else:
            return True

    # General facilities for components.

    def error_dialog(self, title, msg, fatal=True):
        """Display an error message dialog."""
        self._abstract('error_dialog')

    def question_dialog(self, title, msg, options, use_templates=True):
        """Ask a question."""
        self._abstract('question_dialog')

    def run_automation_error_cmd(self):
        if self.automation_error_cmd != '':
            execute_root('sh', '-c', self.automation_error_cmd)

    def run_error_cmd(self):
        if self.error_cmd != '':
            execute_root('sh', '-c', self.error_cmd)

    def run_success_cmd(self):
        if self.success_cmd != '':
            self.debconf_progress_info(
                self.get_string('ubiquity/install/success_command'))
            execute_root('sh', '-c', self.success_cmd)

    def slideshow_get_available_locale(self, slideshow_dir, locale):
        # Returns the ideal locale for the given slideshow, based on the
        # given locale, or 'c' if an ideal one is not available.
        # For example, with locale=en_CA, this returns en if en_CA is not
        # available. If en is not available this would return c.

        slides_dir = '%s/slides' % slideshow_dir
        locale_choice = 'c'

        if os.path.exists('%s/loc.%s' % (slides_dir, locale)):
            locale_choice = locale
        else:
            ll_cc = locale.split('.')[0]
            ll = ll_cc.split('_')[0]
            if os.path.exists('%s/loc.%s' % (slides_dir, ll_cc)):
                locale_choice = ll_cc
            elif os.path.exists('%s/loc.%s' % (slides_dir, ll)):
                locale_choice = ll

        return locale_choice
