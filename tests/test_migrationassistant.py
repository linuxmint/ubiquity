#! /usr/bin/python

import os
import unittest

import mock

class TestMigrationAssistant(unittest.TestCase):
    def setUp(self):
        os.environ['UBIQUITY_MIGRATION_ASSISTANT'] = '1'

    def tearDown(self):
        del os.environ['UBIQUITY_MIGRATION_ASSISTANT']

    @mock.patch('ubiquity.misc.execute')
    @mock.patch('ubiquity.misc.execute_root')
    @mock.patch('ubiquity.misc.dmimodel')
    @mock.patch('ubiquity.misc.drop_privileges')
    @mock.patch('ubiquity.misc.regain_privileges')
    @mock.patch('ubiquity.frontend.gtk_ui.Wizard.customize_installer')
    @mock.patch('ubiquity.nm.wireless_hardware_present')
    @mock.patch('ubiquity.nm.NetworkManager.start')
    @mock.patch('ubiquity.nm.NetworkManager.get_state')
    @mock.patch('ubiquity.misc.has_connection')
    @mock.patch('ubiquity.upower.setup_power_watch')
    @mock.patch('dbus.mainloop.glib.DBusGMainLoop')
    @mock.patch('gi.repository.UbiquityWebcam.Webcam.available')
    @mock.patch('ubiquity.i18n.reset_locale')
    def test_sensible_treeview_size(self, mock_reset_locale, *args):
        """The tree view should show at least a sensible number of items."""
        from ubiquity.frontend import gtk_ui
        mock_reset_locale.return_value = 'en_US.UTF-8'
        ui = gtk_ui.Wizard('test-ubiquity')
        ui.translate_pages()
        ma_page = [page for page in ui.pages
                   if page.module.NAME == 'migrationassistant'][0]
        ui.set_page(ma_page.module.NAME)
        tree = []
        for part in ('sda1', 'sda2', 'sda3', 'sda4'):
            tree.append({
                'user': 'tester',
                'part': part,
                'os': 'Ubuntu',
                'items': ['Bookmarks', 'Documents'],
                'selected': False,
                })
        ma_page.ui.ma_set_choices(tree)
        ui.refresh()
        visible_range = ui.matreeview.get_visible_range()
        if len(visible_range) == 3:  # pygobject < 3.1.92
            valid, start_path, end_path = visible_range
            self.assertTrue(valid)
        else:
            start_path, end_path = visible_range
        self.assertEqual('0', start_path.to_string())
        self.assertEqual('3', end_path.to_string())
