#!/usr/bin/python
# -*- coding: utf-8; -*-

import unittest

import debconf
import mock

from ubiquity import plugin_manager

class TimezoneTests(unittest.TestCase):
    def setUp(self):
        self.ubi_timezone = plugin_manager.load_plugin('ubi-timezone')
        db = debconf.DebconfCommunicator('ubi-test', cloexec=True)
        self.addCleanup(db.shutdown)
        controller = mock.Mock()
        controller.dbfilter = self.ubi_timezone.Page(None, db=db)
        self.gtk = self.ubi_timezone.PageGtk(controller)

    @mock.patch('gi.repository.Soup.SessionAsync')
    @mock.patch('gi.repository.Soup.Message')
    @mock.patch('json.loads')
    def test_city_entry(self, json_mock, *args):
        from gi.repository import GObject

        # Patch GObject.timeout_add_seconds to call the supplied function
        # immediately rather than waiting for the interval to expire.
        def side_effect_factory(real_method):
            def side_effect(interval, function, data):
                function(data)
            return side_effect

        json_mock.return_value = []
        real_method = GObject.timeout_add_seconds
        method = mock.patch('gi.repository.GObject.timeout_add_seconds')
        timeout_mock = method.start()
        timeout_mock.side_effect = side_effect_factory(real_method)
        self.addCleanup(method.stop)

        self.gtk.set_timezone('America/New_York')
        self.gtk.city_entry.set_text('Eastern')
        self.gtk.changed(self.gtk.city_entry)
        m = self.gtk.city_entry.get_completion().get_model()
        results = []
        expected = (('Eastern', 'United States'), ('Eastern', 'Canada'))
        for x in m:
            results.append((x[0], x[2]))
        self.assertEqual(len(results), 2,
                msg='expected: %s\ngot: %s' % (str(expected), str(results)))
        self.assertEqual(set(results), set(expected))
        # unicode, LP: #831533
        self.gtk.city_entry.set_text(u'♥')
        self.gtk.changed(self.gtk.city_entry)
