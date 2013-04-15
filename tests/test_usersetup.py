#!/usr/bin/python3
# -*- coding: utf-8; -*-

import unittest

from gi.repository import UbiquityMockResolver
import mock

from ubiquity import gtkwidgets, plugin_manager


def mock_get_string(name, lang=None, prefix=None):
    return "%s: %s" % (lang, name)


class UserSetupTests(unittest.TestCase):
    def setUp(self):
        for obj in ('ubiquity.misc.execute',
                    'ubiquity.misc.execute_root',
                    'ubiquity.misc.dmimodel'):
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)
        ubi_usersetup = plugin_manager.load_plugin('ubi-usersetup')
        controller = mock.Mock()
        controller.oem_config = False
        self.ubi_usersetup = ubi_usersetup
        self.gtk = self.ubi_usersetup.PageGtk(controller)

    def test_hostname_check(self):
        self.gtk.resolver = UbiquityMockResolver.MockResolver(
            hostname='myhostname')
        self.gtk.hostname_ok.show()
        self.gtk.hostname.set_text('ahostnamethatdoesntexistonthenetwork')
        self.gtk.hostname_error = mock.Mock()
        self.gtk.hostname_timeout(self.gtk.hostname)
        gtkwidgets.refresh()
        self.assertEqual(self.gtk.hostname_error.call_count, 0)

    def test_hostname_check_exists(self):
        error_msg = 'That name already exists on the network.'
        self.gtk.resolver = UbiquityMockResolver.MockResolver(
            hostname='myhostname')
        self.gtk.hostname_ok.show()
        self.gtk.hostname.set_text('myhostname')
        self.gtk.hostname_error = mock.Mock()
        self.gtk.hostname_timeout(self.gtk.hostname)
        gtkwidgets.refresh()
        self.assertTrue(self.gtk.hostname_error.call_count > 0)
        self.gtk.hostname_error.assert_called_with(error_msg)

    def test_hostname_check_bogus_dns(self):
        self.gtk.resolver = UbiquityMockResolver.MockResolver(
            hostname='myhostname')
        self.gtk.detect_bogus_result('myhostname')
        gtkwidgets.refresh()
        self.gtk.hostname_ok.show()
        self.gtk.hostname.set_text('myhostname')
        self.gtk.hostname_error = mock.Mock()
        self.gtk.hostname_timeout(self.gtk.hostname)
        gtkwidgets.refresh()
        self.assertEqual(self.gtk.hostname_error.call_count, 0)

    def assertHostnameErrors(self, errors, hostname):
        self.assertEqual(errors, self.ubi_usersetup.check_hostname(hostname))

    def test_check_hostname(self):
        self.assertHostnameErrors(['hostname_error_length'], 'a' * 64)
        self.assertHostnameErrors(['hostname_error_badchar'], 'abc123$')
        self.assertHostnameErrors(['hostname_error_badhyphen'], '-abc123')
        self.assertHostnameErrors(['hostname_error_badhyphen'], 'abc123-')
        self.assertHostnameErrors(['hostname_error_baddots'], '.abc123')
        self.assertHostnameErrors(['hostname_error_baddots'], 'abc123.')
        self.assertHostnameErrors(['hostname_error_baddots'], 'abc..123')
        self.assertHostnameErrors([
            'hostname_error_length',
            'hostname_error_badchar',
            'hostname_error_badhyphen',
            'hostname_error_baddots',
        ], '-abc..123$' + 'a' * 64)
        self.assertHostnameErrors([], 'abc123')

    def assertUsernameErrors(self, errors, username):
        self.assertEqual(errors, self.ubi_usersetup.check_username(username))

    def test_check_username(self):
        self.assertUsernameErrors(['username_error_badfirstchar'], 'Evan')
        self.assertUsernameErrors(['username_error_badchar'], 'evan$')
        self.assertUsernameErrors([], 'evan')

    def test_unicode(self):
        # i18n needs to be imported to register ascii_transliterate
        from ubiquity import i18n

        self.gtk.controller.get_string = mock_get_string
        heart = '♥'
        self.gtk.set_fullname(heart)
        self.gtk.set_username(heart)
        self.gtk.set_hostname(heart)
        # Shortcut initialization
        self.gtk.fullname.set_name('fullname')
        self.gtk.username.set_name('username')
        self.gtk.username_edited = False
        self.gtk.hostname_edited = False
        self.gtk.info_loop(self.gtk.fullname)
        self.gtk.info_loop(self.gtk.username)

    def test_on_authentication_toggled(self):
        self.gtk.login_encrypt.set_active(True)
        self.gtk.login_auto.set_active(True)
        self.gtk.on_authentication_toggled(self.gtk.login_auto)
        self.assertFalse(self.gtk.login_encrypt.get_active())

        self.gtk.login_auto.set_active(True)
        self.gtk.login_encrypt.set_active(True)
        self.gtk.on_authentication_toggled(self.gtk.login_encrypt)
        self.assertTrue(self.gtk.login_pass.get_active())

    def test_default_username(self):
        self.gtk.controller.get_string = mock_get_string
        self.gtk.set_fullname('Example Person')
        # Shortcut initialization
        self.gtk.fullname.set_name('fullname')
        self.gtk.username_edited = False
        self.gtk.info_loop(self.gtk.fullname)
        self.assertEqual('example', self.gtk.get_username())
        self.assertUsernameErrors([], self.gtk.get_username())

    def test_default_username_strips_invalid_characters(self):
        self.gtk.controller.get_string = mock_get_string
        self.gtk.set_fullname('&Foo!$ Bar!')
        # Shortcut initialization
        self.gtk.fullname.set_name('fullname')
        self.gtk.username_edited = False
        self.gtk.info_loop(self.gtk.fullname)
        self.assertEqual('foo', self.gtk.get_username())
        self.assertUsernameErrors([], self.gtk.get_username())
