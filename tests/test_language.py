# -*- coding: utf8; -*-
#!/usr/bin/python

import unittest
import mock
import sys, os

from ubiquity import i18n
from gi.repository import Gtk

os.environ['UBIQUITY_GLADE'] = 'gui/gtk'

def side_effect_factory(real_method):
    new_path = 'd-i/source/localechooser/debian/localechooser' \
               '/usr/share/localechooser/languagelist.data.gz'
    def side_effect(path, *args, **kw):
        if path.endswith('languagelist.data.gz'):
            return real_method(new_path, *args, **kw)
        else:
            return real_method(path, *args, **kw)
    return side_effect

class LanguageTests(unittest.TestCase):
    def setUp(self):
        for obj in ('ubiquity.misc.execute',
                'ubiquity.misc.execute_root'):
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)

        sys.path.insert(0, 'ubiquity/plugins')
        ubi_language = __import__('ubi-language')
        sys.path.pop()

        controller = mock.Mock()
        controller.oem_user_config = True
        controller.oem_config = False
        self.ubi_language = ubi_language
        self.gtk = self.ubi_language.PageGtk(controller)

    def test_labels_dont_wrap(self):
        # I would love to test whether the actual allocations are all the
        # same height; however, GTK+3.0 does not allow access to the
        # GtkIconViewItem GList.
        real_method = open
        method = mock.patch('__builtin__.open')
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
        layout =  self.gtk.iconview.create_pango_layout(longest)
        self.assertEqual(layout.get_pixel_size()[0] + pad * 2, width)
