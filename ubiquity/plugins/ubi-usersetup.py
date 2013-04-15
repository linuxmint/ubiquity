# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# «usersetup» - User creation plugin.
#
# Copyright (C) 2005, 2006, 2007, 2008, 2009, 2010 Canonical Ltd.
#
# Authors:
#
# - Colin Watson <cjwatson@ubuntu.com>
# - Evan Dandrea <ev@ubuntu.com>
# - Roman Shtylman <shtylman@gmail.com>
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

from __future__ import print_function

import os
import re

import debconf

from ubiquity import misc, plugin, validation


NAME = 'usersetup'
AFTER = 'console_setup'
WEIGHT = 10


def check_hostname(hostname):
    """Returns a list of reasons why the hostname is invalid."""
    errors = []
    for result in validation.check_hostname(misc.utf8(hostname)):
        if result == validation.HOSTNAME_LENGTH:
            errors.append('hostname_error_length')
        elif result == validation.HOSTNAME_BADCHAR:
            errors.append('hostname_error_badchar')
        elif result == validation.HOSTNAME_BADHYPHEN:
            errors.append('hostname_error_badhyphen')
        elif result == validation.HOSTNAME_BADDOTS:
            errors.append('hostname_error_baddots')
    return errors


def check_username(username):
    """Returns a list of reasons why the username is invalid."""
    if username:
        if not re.match('[a-z]', username[0]):
            return ['username_error_badfirstchar']
        # Technically both these conditions might hold.  However, the common
        # case seems to be that somebody starts typing their name beginning
        # with an upper-case letter, and it's probably sufficient to just
        # issue the first error in that case.
        elif not re.match('^[-a-z0-9_]+$', username):
            return ['username_error_badchar']
    return []


def make_error_string(controller, errors):
    """Returns a newline-separated string of translated error reasons."""
    return "\n".join([controller.get_string(error) for error in errors])


class PageBase(plugin.PluginUI):
    def __init__(self):
        self.suffix = misc.dmimodel()
        if self.suffix:
            self.suffix = '-%s' % self.suffix
        else:
            if misc.execute("laptop-detect"):
                self.suffix = '-laptop'
            else:
                self.suffix = '-desktop'
        self.allow_password_empty = False

    def set_fullname(self, value):
        """Set the user's full name."""
        raise NotImplementedError('set_fullname')

    def get_fullname(self):
        """Get the user's full name."""
        raise NotImplementedError('get_fullname')

    def set_username(self, value):
        """Set the user's Unix user name."""
        raise NotImplementedError('set_username')

    def get_username(self):
        """Get the user's Unix user name."""
        raise NotImplementedError('get_username')

    def get_password(self):
        """Get the user's password."""
        raise NotImplementedError('get_password')

    def get_verified_password(self):
        """Get the user's password confirmation."""
        raise NotImplementedError('get_verified_password')

    def set_auto_login(self, value):
        """Set whether the user should be automatically logged in."""
        raise NotImplementedError('set_auto_login')

    def get_auto_login(self):
        """Returns true if the user should be automatically logged in."""
        raise NotImplementedError('get_auto_login')

    def set_encrypt_home(self, value):
        """Set whether the home directory should be encrypted."""
        raise NotImplementedError('set_encrypt_home')

    def set_force_encrypt_home(self, value):
        """Forces whether the home directory should be encrypted."""
        raise NotImplementedError('set_force_encrypt_home')

    def get_encrypt_home(self):
        """Returns true if the home directory should be encrypted."""
        raise NotImplementedError('get_encrypt_home')

    def username_error(self, msg):
        """The selected username was bad."""
        raise NotImplementedError('username_error')

    def password_error(self, msg):
        """The selected password was bad."""
        raise NotImplementedError('password_error')

    def hostname_error(self, msg):
        """ The hostname had an error """
        raise NotImplementedError('hostname_error')

    def get_hostname(self):
        """Get the selected hostname."""
        raise NotImplementedError('get_hostname')

    def set_hostname(self, hostname):
        raise NotImplementedError('set_hostname')

    def clear_errors(self):
        pass

    def info_loop(self, *args):
        """Verify user input."""
        pass

    def set_allow_password_empty(self, empty):
        self.allow_password_empty = empty


class PageGtk(PageBase):
    plugin_title = 'ubiquity/text/userinfo_heading_label'

    def __init__(self, controller, *args, **kwargs):
        from gi.repository import Gio, Gtk

        PageBase.__init__(self, *args, **kwargs)
        self.resolver = Gio.Resolver.get_default()
        self.controller = controller
        self.username_changed_id = None
        self.hostname_changed_id = None
        self.username_edited = False
        self.hostname_edited = False
        self.hostname_timeout_id = 0

        builder = Gtk.Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepUserInfo.ui'))
        builder.connect_signals(self)
        self.page = builder.get_object('stepUserInfo')
        self.username = builder.get_object('username')
        self.hostname = builder.get_object('hostname')
        self.fullname = builder.get_object('fullname')
        self.password = builder.get_object('password')
        self.verified_password = builder.get_object('verified_password')
        self.login_auto = builder.get_object('login_auto')
        self.login_encrypt = builder.get_object('login_encrypt')
        self.login_pass = builder.get_object('login_pass')
        self.username_error_label = builder.get_object('username_error_label')
        self.hostname_error_label = builder.get_object('hostname_error_label')
        self.password_error_label = builder.get_object('password_error_label')
        self.login_vbox = builder.get_object('login_vbox')

        self.username_ok = builder.get_object('username_ok')
        self.hostname_ok = builder.get_object('hostname_ok')
        self.fullname_ok = builder.get_object('fullname_ok')
        self.password_ok = builder.get_object('password_ok')
        self.password_strength = builder.get_object('password_strength')

        # Dodgy hack to let us center the contents of the page without it
        # moving as elements appear and disappear, specifically the full name
        # okay check icon and the hostname error messages.
        paddingbox = builder.get_object('paddingbox')

        def func(box):
            box.get_parent().child_set_property(box, 'expand', False)
            box.set_size_request(box.get_allocation().width / 2, -1)

        paddingbox.connect('realize', func)

        # Some signals need to be connected by hand so that we have the
        # handler ids.
        self.username_changed_id = self.username.connect(
            'changed', self.on_username_changed)
        self.hostname_changed_id = self.hostname.connect(
            'changed', self.on_hostname_changed)

        if self.controller.oem_config:
            self.fullname.set_text('OEM Configuration (temporary user)')
            self.fullname.set_editable(False)
            self.fullname.set_sensitive(False)
            self.username.set_text('oem')
            self.username.set_editable(False)
            self.username.set_sensitive(False)
            self.username_edited = True
            self.hostname.set_text('oem%s' % self.suffix)
            self.hostname_edited = True
            self.login_vbox.hide()
            # The UserSetup component takes care of preseeding passwd/user-uid.
            misc.execute_root('apt-install', 'oem-config-gtk',
                                             'oem-config-slideshow-ubuntu')

        self.resolver_ok = True
        self.plugin_widgets = self.page

    def plugin_translate(self, lang):
        # TODO Move back into the frontend as we can check
        # isinstance(LabelledEntry and just call set_label.  We'll need to
        # properly name the debconf keys though (s/inactive_label//)
        user = self.controller.get_string('username_inactive_label', lang)
        full = self.controller.get_string('fullname_inactive_label', lang)
        pasw = self.controller.get_string('password_inactive_label', lang)
        vpas = self.controller.get_string('password_again_inactive_label',
                                          lang)
        self.username.set_placeholder_text(user)
        self.fullname.set_placeholder_text(full)
        self.password.set_placeholder_text(pasw)
        self.verified_password.set_placeholder_text(vpas)

    # Functions called by the Page.

    def set_fullname(self, value):
        self.fullname.set_text(value)

    def get_fullname(self):
        return self.fullname.get_text()

    def set_username(self, value):
        self.username.set_text(value)

    def get_username(self):
        return self.username.get_text()

    def get_password(self):
        return self.password.get_text()

    def get_verified_password(self):
        return self.verified_password.get_text()

    def set_auto_login(self, value):
        self.login_auto.set_active(value)

    def get_auto_login(self):
        return self.login_auto.get_active()

    def set_encrypt_home(self, value):
        self.login_encrypt.set_active(value)

    def set_force_encrypt_home(self, value):
        self.login_vbox.set_sensitive(not value)

    def get_encrypt_home(self):
        return self.login_encrypt.get_active()

    def username_error(self, msg):
        self.username_ok.hide()
        m = '<small><span foreground="darkred"><b>%s</b></span></small>' % msg
        self.username_error_label.set_markup(m)
        self.username_error_label.show()

    def hostname_error(self, msg):
        self.hostname_ok.hide()
        m = '<small><span foreground="darkred"><b>%s</b></span></small>' % msg
        self.hostname_error_label.set_markup(m)
        self.hostname_error_label.show()

    def password_error(self, msg):
        self.password_strength.hide()
        m = '<small><span foreground="darkred"><b>%s</b></span></small>' % msg
        self.password_error_label.set_markup(m)
        self.password_error_label.show()

    def get_hostname(self):
        return self.hostname.get_text()

    def set_hostname(self, value):
        self.hostname.set_text(value)

    def clear_errors(self):
        self.username_error_label.hide()
        self.hostname_error_label.hide()
        self.password_error_label.hide()

    # Callback functions.

    def info_loop(self, widget):
        """check if all entries from Identification screen are filled. Callback
        defined in ui file."""

        if (self.username_changed_id is None or
                self.hostname_changed_id is None):
            return

        if (widget is not None and widget.get_name() == 'fullname' and
                not self.username_edited):
            self.username.handler_block(self.username_changed_id)
            new_username = misc.utf8(widget.get_text().split(' ')[0])
            new_username = new_username.encode('ascii', 'ascii_transliterate')
            new_username = new_username.decode().lower()
            new_username = re.sub('^[^a-z]+', '', new_username)
            new_username = re.sub('[^-a-z0-9_]', '', new_username)
            self.username.set_text(new_username)
            self.username.handler_unblock(self.username_changed_id)
        elif (widget is not None and widget.get_name() == 'username' and
              not self.hostname_edited):
            self.hostname.handler_block(self.hostname_changed_id)
            t = widget.get_text()
            if t:
                self.hostname.set_text(re.sub(r'\W', '', t) + self.suffix)
            self.hostname.handler_unblock(self.hostname_changed_id)

        # Do some initial validation.  We have to process all the widgets so we
        # can know if we can really show the next button.  Otherwise we'd show
        # it on any field being valid.
        complete = True

        if self.fullname.get_text():
            self.fullname_ok.show()
        else:
            self.fullname_ok.hide()

        text = self.username.get_text()
        if text:
            errors = check_username(text)
            if errors:
                self.username_error(make_error_string(self.controller, errors))
                complete = False
            else:
                self.username_ok.show()
                self.username_error_label.hide()
        else:
            self.username_ok.hide()
            self.username_error_label.hide()
            complete = False

        password_ok = validation.gtk_password_validate(
            self.controller,
            self.password,
            self.verified_password,
            self.password_ok,
            self.password_error_label,
            self.password_strength,
            self.allow_password_empty,
        )

        complete = complete and password_ok

        txt = self.hostname.get_text()
        self.hostname_ok.show()
        if txt:
            errors = check_hostname(txt)
            if errors:
                self.hostname_error(make_error_string(self.controller, errors))
                complete = False
                self.hostname_ok.hide()
            else:
                self.hostname_ok.show()
                self.hostname_error_label.hide()
        else:
            complete = False
            self.hostname_ok.hide()
            self.hostname_error_label.hide()

        self.controller.allow_go_forward(complete)

    def on_username_changed(self, widget):
        self.username_edited = (widget.get_text() != '')

    def on_hostname_changed(self, widget):
        self.hostname_edited = (widget.get_text() != '')

        if not self.is_automatic:
            # Let's not call this every time the user presses a key.
            from gi.repository import GLib
            if self.hostname_timeout_id:
                GLib.source_remove(self.hostname_timeout_id)
            self.hostname_timeout_id = GLib.timeout_add(
                300, self.hostname_timeout, widget)

    def lookup_result(self, resolver, result, unused):
        from gi.repository import GLib
        try:
            resolver.lookup_by_name_finish(result)
        except GLib.GError:
            pass
        else:
            # FIXME: i18n
            self.hostname_error('That name already exists on the network.')
            self.hostname_ok.hide()

    def hostname_timeout(self, widget):
        if self.hostname_ok.get_property('visible') and self.resolver_ok:
            hostname = widget.get_text()
            for host in (hostname, '%s.local' % hostname):
                self.resolver.lookup_by_name_async(
                    host, None, self.lookup_result, None)

    def detect_bogus_result(self, hostname='xyzzy_does_not_exist'):
        # bug 760884
        # On networks where DNS fakes a response for unknown hosts,
        # don't display a warning for hostnames that already exist.
        self.resolver.lookup_by_name_async(
            hostname, None, self.bogus_lookup_result, None)

    def bogus_lookup_result(self, resolver, result, unused):
        from gi.repository import GLib
        try:
            resolver.lookup_by_name_finish(result)
        except GLib.GError:
            self.resolver_ok = True
        else:
            self.resolver_ok = False

    def on_authentication_toggled(self, w):
        if w == self.login_auto and w.get_active():
            self.login_encrypt.set_active(False)
        elif w == self.login_encrypt and w.get_active():
            # TODO why is this so slow to activate the login_pass radio button
            # when checking encrypted home?
            self.login_pass.set_active(True)


class PageKde(PageBase):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_user'

    def __init__(self, controller, *args, **kwargs):
        PageBase.__init__(self, *args, **kwargs)
        self.controller = controller

        from PyQt4 import uic
        from PyQt4.QtGui import QPixmap

        self.plugin_widgets = uic.loadUi(
            '/usr/share/ubiquity/qt/stepUserSetup.ui')
        self.page = self.plugin_widgets

        self.username_edited = False
        self.hostname_edited = False

        if self.controller.oem_config:
            self.page.fullname.setText('OEM Configuration (temporary user)')
            self.page.fullname.setReadOnly(True)
            self.page.fullname.setEnabled(False)
            self.page.username.setText('oem')
            self.page.username.setReadOnly(True)
            self.page.username.setEnabled(False)
            self.page.login_pass.hide()
            self.page.login_auto.hide()
            self.page.login_encrypt.hide()
            self.username_edited = True
            self.hostname_edited = True

            self.page.hostname.setText('oem%s' % self.suffix)

            # The UserSetup component takes care of preseeding passwd/user-uid.
            misc.execute_root('apt-install', 'oem-config-kde')

        warningIcon = QPixmap(
            "/usr/share/icons/oxygen/48x48/status/dialog-warning.png")
        self.page.fullname_error_image.setPixmap(warningIcon)
        self.page.username_error_image.setPixmap(warningIcon)
        self.page.password_error_image.setPixmap(warningIcon)
        self.page.hostname_error_image.setPixmap(warningIcon)

        self.clear_errors()

        self.page.fullname.textChanged[str].connect(self.on_fullname_changed)
        self.page.username.textChanged[str].connect(self.on_username_changed)
        self.page.hostname.textChanged[str].connect(self.on_hostname_changed)
        #self.page.password.textChanged[str].connect(self.on_password_changed)
        #self.page.verified_password.textChanged[str].connect(
        #    self.on_verified_password_changed)
        self.page.login_pass.clicked[bool].connect(self.on_login_pass_clicked)
        self.page.login_auto.clicked[bool].connect(self.on_login_auto_clicked)

        self.page.password_debug_warning_label.setVisible(
            'UBIQUITY_DEBUG' in os.environ)

    def on_fullname_changed(self):
        # If the user did not manually enter a username create one for him.
        if not self.username_edited:
            self.page.username.blockSignals(True)
            new_username = str(self.page.fullname.text()).split(' ')[0]
            new_username = new_username.encode('ascii', 'ascii_transliterate')
            new_username = new_username.decode().lower()
            self.page.username.setText(new_username)
            self.on_username_changed()
            self.username_edited = False
            self.page.username.blockSignals(False)

    def on_username_changed(self):
        if not self.hostname_edited:
            self.page.hostname.blockSignals(True)
            self.page.hostname.setText(
                str(self.page.username.text()).strip() + self.suffix)
            self.page.hostname.blockSignals(False)

        self.username_edited = (self.page.username.text() != '')

    def on_password_changed(self):
        pass

    def on_verified_password_changed(self):
        pass

    def on_hostname_changed(self):
        self.hostname_edited = (self.page.hostname.text() != '')

    def set_fullname(self, value):
        self.page.fullname.setText(misc.utf8(value))

    def get_fullname(self):
        return str(self.page.fullname.text())

    def set_username(self, value):
        self.page.username.setText(misc.utf8(value))

    def get_username(self):
        return str(self.page.username.text())

    def get_password(self):
        return str(self.page.password.text())

    def get_verified_password(self):
        return str(self.page.verified_password.text())

    def set_auto_login(self, value):
        return self.page.login_auto.setChecked(value)

    def get_auto_login(self):
        return self.page.login_auto.isChecked()

    def on_login_pass_clicked(self, checked):
        self.page.login_encrypt.setEnabled(checked)

    def on_login_auto_clicked(self, checked):
        self.page.login_encrypt.setChecked(not(checked))
        self.page.login_encrypt.setEnabled(not(checked))

    def set_encrypt_home(self, value):
        self.page.login_encrypt.setChecked(value)

    def set_force_encrypt_home(self, value):
        self.page.login_encrypt.setDisabled(value)
        self.page.login_auto.setDisabled(value)
        self.page.login_pass.setDisabled(value)

    def get_encrypt_home(self):
        return self.page.login_encrypt.isChecked()

    def username_error(self, msg):
        self.page.username_error_reason.setText(msg)
        self.page.username_error_image.show()
        self.page.username_error_reason.show()

    def password_error(self, msg):
        self.page.password_error_reason.setText(msg)
        self.page.password_error_image.show()
        self.page.password_error_reason.show()

    def hostname_error(self, msg):
        self.page.hostname_error_reason.setText(msg)
        self.page.hostname_error_image.show()
        self.page.hostname_error_reason.show()

    def get_hostname(self):
        return str(self.page.hostname.text())

    def set_hostname(self, value):
        self.page.hostname.setText(value)

    def clear_errors(self):
        self.page.fullname_error_image.hide()
        self.page.username_error_image.hide()
        self.page.password_error_image.hide()
        self.page.hostname_error_image.hide()

        self.page.username_error_reason.hide()
        self.page.password_error_reason.hide()
        self.page.hostname_error_reason.hide()


class PageDebconf(PageBase):
    plugin_title = 'ubiquity/text/userinfo_heading_label'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller


class PageNoninteractive(PageBase):
    def __init__(self, controller, *args, **kwargs):
        PageBase.__init__(self, *args, **kwargs)
        self.controller = controller
        self.fullname = ''
        self.username = ''
        self.password = ''
        self.verifiedpassword = ''
        self.auto_login = False
        self.encrypt_home = False
        self.console = self.controller._wizard.console

    def set_fullname(self, value):
        """Set the user's full name."""
        self.fullname = value

    def get_fullname(self):
        """Get the user's full name."""
        if self.controller.oem_config:
            return 'OEM Configuration (temporary user)'
        return self.fullname

    def set_username(self, value):
        """Set the user's Unix user name."""
        self.username = value

    def get_username(self):
        """Get the user's Unix user name."""
        if self.controller.oem_config:
            return 'oem'
        return self.username

    def get_password(self):
        """Get the user's password."""
        return self.controller.dbfilter.db.get('passwd/user-password')

    def get_verified_password(self):
        """Get the user's password confirmation."""
        return self.controller.dbfilter.db.get('passwd/user-password-again')

    def set_auto_login(self, value):
        self.auto_login = value

    def get_auto_login(self):
        return self.auto_login

    def set_encrypt_home(self, value):
        self.encrypt_home = value

    def set_force_encrypt_home(self, value):
        self.set_encrypt_home(value)

    def get_encrypt_home(self):
        return self.encrypt_home

    def username_error(self, msg):
        """The selected username was bad."""
        print('\nusername error: %s' % msg, file=self.console)
        self.username = input('Username: ')

    def password_error(self, msg):
        """The selected password was bad."""
        print('\nBad password: %s' % msg, file=self.console)
        import getpass
        self.password = getpass.getpass('Password: ')
        self.verifiedpassword = getpass.getpass('Password again: ')

    def set_hostname(self, name):
        pass

    def get_hostname(self):
        """Get the selected hostname."""
        # We set a default in install.py in case it isn't preseeded but when we
        # preseed, we are looking for None anyhow.
        return ''

    def clear_errors(self):
        pass


class Page(plugin.Plugin):
    def prepare(self, unfiltered=False):
        if ('UBIQUITY_FRONTEND' not in os.environ or
                os.environ['UBIQUITY_FRONTEND'] != 'debconf_ui'):
            self.preseed_bool('user-setup/allow-password-weak', True)
            if self.ui.get_hostname() == '':
                try:
                    seen = self.db.fget(
                        'netcfg/get_hostname', 'seen') == 'true'
                    if seen:
                        hostname = self.db.get('netcfg/get_hostname')
                        domain = self.db.get('netcfg/get_domain')
                        if hostname and domain:
                            hostname = '%s.%s' % (hostname.rstrip('.'),
                                                  domain.strip('.'))
                        if hostname != '':
                            self.ui.set_hostname(hostname)
                except debconf.DebconfError:
                    pass
            if self.ui.get_fullname() == '':
                try:
                    fullname = self.db.get('passwd/user-fullname')
                    if fullname != '':
                        self.ui.set_fullname(fullname)
                except debconf.DebconfError:
                    pass
            if self.ui.get_username() == '':
                try:
                    username = self.db.get('passwd/username')
                    if username != '':
                        self.ui.set_username(username)
                except debconf.DebconfError:
                    pass
            try:
                auto_login = self.db.get('passwd/auto-login')
                self.ui.set_auto_login(auto_login == 'true')
            except debconf.DebconfError:
                pass
            try:
                encrypt_home = self.db.get('user-setup/force-encrypt-home')
                if not encrypt_home:
                    encrypt_home = self.db.get('user-setup/encrypt-home')
                self.ui.set_encrypt_home(encrypt_home == 'true')
                self.ui.set_force_encrypt_home(encrypt_home == 'true')
            except debconf.DebconfError:
                pass
        try:
            empty = self.db.get('user-setup/allow-password-empty') == 'true'
        except debconf.DebconfError:
            empty = False
        self.ui.set_allow_password_empty(empty)

        # We need to call info_loop as we switch to the page so the next button
        # gets disabled.
        self.ui.info_loop(None)

        # Trigger the bogus DNS server detection
        if (not self.is_automatic and hasattr(self.ui, 'detect_bogus_result')):
            self.ui.detect_bogus_result()

        # We intentionally don't listen to passwd/auto-login or
        # user-setup/encrypt-home because we don't want those alone to force
        # the page to be shown, if they're the only questions not preseeded.
        questions = ['^passwd/user-fullname$', '^passwd/username$',
                     '^passwd/user-password$', '^passwd/user-password-again$',
                     'ERROR']
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            command = ['/usr/lib/ubiquity/user-setup/user-setup-ask-oem']
            environ = {'OVERRIDE_SYSTEM_USER': '1'}
            return command, questions, environ
        else:
            # TODO: It would be neater to use a wrapper script.
            command = [
                'sh', '-c',
                '/usr/lib/ubiquity/user-setup/user-setup-ask /target && '
                '/usr/share/ubiquity/user-setup-encrypted-swap',
            ]
            return command, questions

    def set(self, question, value):
        if question == 'passwd/username':
            if self.ui.get_username() != '':
                self.ui.set_username(value)

    def run(self, priority, question):
        return plugin.Plugin.run(self, priority, question)

    def ok_handler(self):
        self.ui.clear_errors()

        fullname = self.ui.get_fullname()
        username = self.ui.get_username().strip()
        password = self.ui.get_password()
        password_confirm = self.ui.get_verified_password()
        auto_login = self.ui.get_auto_login()
        encrypt_home = self.ui.get_encrypt_home()

        self.preseed('passwd/user-fullname', fullname)
        self.preseed('passwd/username', username)
        # TODO: maybe encrypt these first
        self.preseed('passwd/user-password', password)
        self.preseed('passwd/user-password-again', password_confirm)
        if self.ui.controller.oem_config:
            self.preseed('passwd/user-uid', '29999')
        else:
            self.preseed('passwd/user-uid', '')
        self.preseed_bool('passwd/auto-login', auto_login)
        self.preseed_bool('user-setup/encrypt-home', encrypt_home)

        hostname = self.ui.get_hostname()

        # check if the hostname had errors
        errors = check_hostname(hostname)

        # showing warning message is error is set
        if errors:
            self.ui.hostname_error(
                make_error_string(self.ui.controller, errors))
            self.done = False
            self.enter_ui_loop()
            return

        if hostname is not None and hostname != '':
            hd = hostname.split('.', 1)
            self.preseed('netcfg/get_hostname', hd[0])
            if len(hd) > 1:
                self.preseed('netcfg/get_domain', hd[1])
            else:
                self.preseed('netcfg/get_domain', '')

        plugin.Plugin.ok_handler(self)

    def error(self, priority, question):
        if question.startswith('passwd/username-'):
            self.ui.username_error(self.extended_description(question))
        elif question.startswith('user-setup/password-'):
            self.ui.password_error(self.extended_description(question))
        else:
            self.ui.error_dialog(
                self.description(question),
                self.extended_description(question))
        return plugin.Plugin.error(self, priority, question)


class Install(plugin.InstallPlugin):
    def prepare(self, unfiltered=False):
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            command = ['/usr/lib/ubiquity/user-setup/user-setup-apply']
            environ = {'OVERRIDE_SYSTEM_USER': '1'}
        else:
            command = [
                '/usr/lib/ubiquity/user-setup/user-setup-apply', '/target']
            environ = {}
            if os.path.exists('/var/lib/ubiquity/encrypted-swap'):
                environ['OVERRIDE_ALREADY_ENCRYPTED_SWAP'] = '1'
        return command, [], environ

    def error(self, priority, question):
        self.ui.error_dialog(self.description(question),
                             self.extended_description(question))
        return plugin.InstallPlugin.error(self, priority, question)

    def install(self, target, progress, *args, **kwargs):
        progress.info('ubiquity/install/user')
        return plugin.InstallPlugin.install(
            self, target, progress, *args, **kwargs)
