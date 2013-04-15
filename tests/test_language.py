#!/usr/bin/python3
# -*- coding: utf-8; -*-

import os
from test.support import EnvironmentVarGuard
import unittest

from gi.repository import Gtk
import mock

from ubiquity import i18n, plugin_manager


def side_effect_factory(real_method):
    new_path = 'd-i/source/localechooser/debian/localechooser' \
               '/usr/share/localechooser/languagelist.data.gz'

    def side_effect(path, *args, **kw):
        if path.endswith('languagelist.data.gz'):
            return real_method(new_path, *args, **kw)
        else:
            return real_method(path, *args, **kw)

    return side_effect


class OEMUserLanguageTests(unittest.TestCase):
    def setUp(self):
        for obj in ('ubiquity.misc.execute', 'ubiquity.misc.execute_root'):
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)

        ubi_language = plugin_manager.load_plugin('ubi-language')

        controller = mock.Mock()
        controller.oem_user_config = True
        controller.oem_config = False
        self.ubi_language = ubi_language
        self.gtk = self.ubi_language.PageGtk(controller)

    def test_labels_dont_wrap(self):
        # I would love to test whether the actual allocations are all the
        # same height; however, GTK+3.0 does not allow access to the
        # GtkIconViewItem GList.
        if 'UBIQUITY_TEST_INSTALLED' not in os.environ:
            real_method = open
            method = mock.patch('builtins.open')
            mocked_method = method.start()
            mocked_method.side_effect = side_effect_factory(real_method)
            self.addCleanup(method.stop)

        current_language, sorted_choices, language_display_map = \
            i18n.get_languages(0, False)
        w = Gtk.Window()
        # Roughly the size of plugin area.
        w.set_size_request(752, 442)
        w.add(self.gtk.page)
        w.show_all()
        self.gtk.set_language_choices(sorted_choices, language_display_map)
        width = self.gtk.iconview.get_item_width()
        longest_length = 0
        longest = ''
        for choice in sorted_choices:
            length = len(choice)
            if length > longest_length:
                longest_length = length
                longest = choice
        pad = self.gtk.iconview.get_property('item-padding')
        layout = self.gtk.iconview.create_pango_layout(longest)
        self.assertEqual(layout.get_pixel_size()[0] + pad * 2, width)


class LanguageTests(unittest.TestCase):
    def setUp(self):
        for obj in ('ubiquity.misc.execute', 'ubiquity.misc.execute_root'):
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)

        ubi_language = plugin_manager.load_plugin('ubi-language')

        self.controller = mock.Mock()
        self.controller.oem_user_config = False
        self.controller.oem_config = False
        self.ubi_language = ubi_language
        # Set the environment variable needed in order for PageGtk to hook up
        # the Try Ubuntu button with the appropriate action.
        with EnvironmentVarGuard() as environ:
            environ['UBIQUITY_GREETER'] = '1'
            self.gtk = self.ubi_language.PageGtk(self.controller)

    def test_try_ubuntu_clicks(self):
        from ubiquity import gtkwidgets

        # Ensure that the mock changes state correctly.
        self.controller.allowed_change_step.return_value = True

        def side_effect(*args):
            assert len(args) == 1 and type(args[0]) is bool
            self.controller.allowed_change_step.return_value = args[0]

        self.controller.allow_change_step.side_effect = side_effect
        # Multiple clicks on Try Ubuntu crash the installer.  LP: #911907
        self.gtk.try_ubuntu.clicked()
        self.gtk.try_ubuntu.clicked()
        # Process the clicks.
        gtkwidgets.refresh()
        # When the Try Ubuntu button is clicked, the dbfilter's ok_handler()
        # methods should have been called only once.
        self.assertEqual(self.controller.dbfilter.ok_handler.call_count, 1)
