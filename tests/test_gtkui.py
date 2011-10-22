# -*- coding: utf-8; -*-
#!/usr/bin/python

import os
os.environ['UBIQUITY_PLUGIN_PATH'] = 'ubiquity/plugins'
os.environ['UBIQUITY_GLADE'] = 'gui/gtk'

import unittest
from ubiquity.frontend import gtk_ui
import mock

class TestFrontend(unittest.TestCase):
    def setUp(self):
        for obj in ('ubiquity.misc.drop_privileges',
                    'ubiquity.misc.regain_privileges',
                    'ubiquity.misc.execute',
                    'ubiquity.frontend.base.drop_privileges',
                    'ubiquity.frontend.gtk_ui.Wizard.customize_installer',
                    'ubiquity.nm.wireless_hardware_present',
                    'ubiquity.misc.add_connection_watch',
                    'ubiquity.misc.has_connection',
                    'ubiquity.upower.setup_power_watch'):
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)
            if obj in ('ubiquity.misc.wireless_hardware_present',
                       'ubiquity.misc.has_connection'):
                patcher.return_value = False

    def test_question_dialog(self):
        ui = gtk_ui.Wizard('test-ubiquity')
        with mock.patch('gi.repository.Gtk.Dialog.run') as run:
            run.return_value = 0
            ret = ui.question_dialog(title=u'♥', msg=u'♥',
                                     options=(u'♥', u'£'))
            self.assertEqual(ret, u'£')
            run.return_value = 1
            ret = ui.question_dialog(title=u'♥', msg=u'♥',
                                     options=(u'♥', u'£'))
            self.assertEqual(ret, u'♥')

    def test_pages_fit_on_a_netbook(self):
        from gi.repository import Gtk, GObject
        ui = gtk_ui.Wizard('test-ubiquity')
        ui.set_page(1)
        ui.translate_pages()
        GObject.timeout_add(250, Gtk.main_quit)
        Gtk.main()
        alloc = ui.live_installer.get_allocation()
        print alloc.height
        self.assertLessEqual(alloc.width, 640)
        self.assertLessEqual(alloc.height, 500)
