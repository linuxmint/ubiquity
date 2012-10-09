#! /usr/bin/python3

import unittest

import mock

from ubiquity import gtkwidgets, nm, plugin_manager


class WirelessTests(unittest.TestCase):
    @mock.patch('ubiquity.nm.NetworkManager.start')
    @mock.patch('ubiquity.nm.NetworkManager.get_state')
    @mock.patch('ubiquity.misc.has_connection')
    def setUp(self, has_connection, get_state, *args):
        has_connection.return_value = True
        get_state.return_value = nm.NM_STATE_DISCONNECTED

        self.ubi_wireless = plugin_manager.load_plugin('ubi-wireless')

        self.gtk = self.ubi_wireless.PageGtk(mock.Mock())
        self.nmwidget = self.gtk.nmwidget
        self.manager = self.nmwidget.view.wifi_model
        self.model = self.manager.model
        self.manager.passphrases_cache = {}

    @mock.patch('ubiquity.nm.NetworkManager.is_connected')
    def test_secure_ap_can_enter_password(self, is_connected):
        is_connected.return_value = False
        iterator = self.model.append(None, ['/foo', 'Intel', 'Wireless'])
        iterator_insecure = self.model.append(iterator, ['Insecure', False, 0])
        iterator_secure = self.model.append(iterator, ['Secure', True, 0])
        gtkwidgets.refresh()
        self.assertFalse(self.nmwidget.hbox.get_sensitive())
        self.nmwidget.view.set_cursor(
            self.model.get_path(iterator_secure), None, False)
        gtkwidgets.refresh()
        self.assertTrue(self.nmwidget.hbox.get_sensitive())
        self.nmwidget.view.set_cursor(
            self.model.get_path(iterator_insecure), None, False)
        gtkwidgets.refresh()
        self.assertFalse(self.nmwidget.hbox.get_sensitive())
