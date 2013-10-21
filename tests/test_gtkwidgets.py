#!/usr/bin/python3
# -*- coding: utf-8; -*-

import sys
from test.support import run_unittest
import unittest

import dbus
from gi.repository import Gtk, TimezoneMap
import mock

from ubiquity import gtkwidgets, nm, segmented_bar
from ubiquity.frontend.gtk_components import nmwidgets


class MockController(object):
    def get_string(self, name, lang=None, prefix=None):
        return "%s: %s" % (lang, name)


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.err = None

        def excepthook(exctype, value, tb):
            # Workaround for http://bugzilla.gnome.org/show_bug.cgi?id=616279
            Gtk.main_quit()
            self.err = exctype, value, tb

        sys.excepthook = excepthook
        self.win = Gtk.Window()

    def tearDown(self):
        self.win.hide()
        if self.err:
            exctype, value, tb = self.err
            if value.__traceback__ is not tb:
                raise value.with_traceback(tb)
            else:
                raise value

    def test_segmented_bar(self):
        sb = segmented_bar.SegmentedBar()
        self.win.add(sb)
        sb.add_segment_rgb('Test One', 30 * 1000 * 1000 * 1000, 'ff00ff')
        sb.add_segment_rgb('Test Two', 30 * 1000 * 1000 * 1000, '0000ff')
        for segment in sb.segments:
            self.assertEqual(segment.subtitle, '30.0 GB')
        self.assertEqual(sb.segments[0].title, 'Test One')
        self.assertEqual(sb.segments[1].title, 'Test Two')
        sb.remove_all()
        self.assertEqual(sb.segments, [])
        self.win.show_all()
        gtkwidgets.refresh()

    def test_timezone_map(self):
        tzmap = TimezoneMap.TimezoneMap()
        self.win.add(tzmap)
        #tzmap.select_city('America/New_York')
        self.win.show_all()
        self.win.connect('destroy', Gtk.main_quit)
        gtkwidgets.refresh()

    def test_state_box(self):
        sb = gtkwidgets.StateBox('foobar')
        self.assertEqual(sb.get_property('label'), 'foobar')
        sb.set_property('label', 'barfoo')
        self.assertEqual(sb.get_property('label'), 'barfoo')
        sb.set_state(True)
        self.assertEqual(sb.image.get_stock(),
                         ('gtk-yes', Gtk.IconSize.LARGE_TOOLBAR))
        self.assertEqual(sb.get_state(), True)
        sb.set_state(False)
        self.assertEqual(sb.image.get_stock(),
                         ('gtk-no', Gtk.IconSize.LARGE_TOOLBAR))
        self.assertEqual(sb.get_state(), False)

    def test_gtk_to_cairo_color(self):
        self.assertEqual(gtkwidgets.gtk_to_cairo_color('white'),
                         (1.0, 1.0, 1.0))
        self.assertEqual(gtkwidgets.gtk_to_cairo_color('black'), (0, 0, 0))
        # After all these years a discrepancy between X11 green and CSS
        # green was noticed
        self.assertEqual(gtkwidgets.gtk_to_cairo_color('#00ff00'), (0, 1.0, 0))
        self.assertEqual(gtkwidgets.gtk_to_cairo_color('red'), (1.0, 0, 0))
        self.assertEqual(gtkwidgets.gtk_to_cairo_color('blue'), (0, 0, 1.0))


class NetworkStoreTests(unittest.TestCase):
    def setUp(self):
        self.model = nmwidgets.GtkNetworkStore()

    def test_add_device(self):
        self.model.add_device('/foo', 'Intel', 'Wireless')
        device_it = self.model.get_iter_first()
        self.assertEqual(self.model.get(device_it, 0, 1, 2),
                         ('/foo', 'Intel', 'Wireless'))

    def test_has_device(self):
        self.model.add_device('/foo', 'Intel', 'Wireless')
        self.model.add_device('/bar', 'Intel', 'Wireless')

        self.assert_(self.model.has_device('/foo'))
        self.assert_(not self.model.has_device('/not-there'))

    def test_get_device_ids(self):
        self.model.add_device('/foo', 'Intel', 'Wireless')
        self.model.add_device('/bar', 'Intel', 'Wireless')

        lst = self.model.get_device_ids()
        self.assertListEqual(lst, ['/foo', '/bar'])

    def test_add_ap(self):
        self.model.add_device('/foo', 'Intel', 'Wireless')
        self.model.add_ap('/foo', 'Orange', True, 40)
        self.model.add_ap('/foo', 'Apple', False, 60)
        device_it = self.model.get_iter_first()

        ap_it = self.model.iter_children(device_it)
        self.assert_(ap_it)
        self.assertEqual(self.model.get(ap_it, 0, 1, 2), ('Orange', True, 40))

        ap_it = self.model.iter_next(ap_it)
        self.assert_(ap_it)
        self.assertEqual(self.model.get(ap_it, 0, 1, 2), ('Apple', False, 60))

        ap_it = self.model.iter_next(ap_it)
        self.assert_(not ap_it)

    def test_has_ap(self):
        self.model.add_device('/foo', 'Intel', 'Wireless')
        self.model.add_ap('/foo', 'Orange', True, 40)
        self.model.add_ap('/foo', 'Apple', False, 60)

        self.assert_(self.model.has_ap('/foo', 'Orange'))
        self.assert_(not self.model.has_ap('/not-there', 'Orange'))
        self.assert_(not self.model.has_ap('/foo', 'Aubergine'))

    def test_set_ap_strength(self):
        self.model.add_device('/foo', 'Intel', 'Wireless')
        self.model.add_ap('/foo', 'Orange', True, 40)

        self.model.set_ap_strength('/foo', 'Orange', 80)
        device_it = self.model.get_iter_first()
        ap_it = self.model.iter_children(device_it)
        self.assertEqual(self.model[ap_it][2], 80)

    def test_remove_aps_not_in(self):
        def list_aps():
            device_it = self.model.get_iter_first()
            ap_it = self.model.iter_children(device_it)
            ret = []
            while ap_it:
                ret.append(self.model[ap_it][0])
                ap_it = self.model.iter_next(ap_it)
            return ret

        self.model.add_device('/foo', 'Intel', 'Wireless')
        fruits = ['Orange', 'Apple', 'Grape']
        for ssid in fruits:
            self.model.add_ap('/foo', ssid, True, 0)

        self.model.remove_aps_not_in('/foo', fruits)
        ret = list_aps()
        # There haven't been any changes in this update.
        self.assertListEqual(fruits, ret)

        # An AP that was present no longer is.
        fruits.pop()
        self.model.remove_aps_not_in('/foo', fruits)
        ret = list_aps()
        self.assertListEqual(fruits, ret)


udevinfo = """
UDEV_LOG=3
DEVPATH=/devices/pci0000:00/0000:00:1c.1/0000:03:00.0/net/wlan0
DEVTYPE=wlan
INTERFACE=wlan0
IFINDEX=3
SUBSYSTEM=net
ID_VENDOR_FROM_DATABASE=Intel Corporation
ID_MODEL_FROM_DATABASE=PRO/Wireless 3945ABG [Golan] Network Connection
ID_BUS=pci
ID_VENDOR_ID=0x8086
ID_MODEL_ID=0x4227
ID_MM_CANDIDATE=1
"""


class NetworkManagerTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('ubiquity.nm.NetworkManager.start')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.model = nmwidgets.GtkNetworkStore()
        self.manager = nm.NetworkManager(self.model,
                                         nmwidgets.GLibQueuedCaller)

    @mock.patch('subprocess.Popen')
    def test_get_vendor_and_model_null(self, mock_subprocess):
        mock_subprocess.return_value.communicate.return_value = (
            '', 'device path not found\n')
        self.assertEqual(nm.get_vendor_and_model('bogus'), ('', ''))

    @mock.patch('subprocess.Popen')
    def test_get_vendor_and_model(self, mock_subprocess):
        mock_subprocess.return_value.communicate.return_value = (
            udevinfo, None)
        self.assertEqual(nm.get_vendor_and_model('foobar'),
                         ('Intel Corporation',
                          'PRO/Wireless 3945ABG [Golan] Network Connection'))

    def test_decode_ssid(self):
        ssid = [dbus.Byte(85), dbus.Byte(98), dbus.Byte(117), dbus.Byte(110),
                dbus.Byte(116), dbus.Byte(117), dbus.Byte(45), dbus.Byte(66),
                dbus.Byte(97), dbus.Byte(116), dbus.Byte(116), dbus.Byte(101),
                dbus.Byte(114), dbus.Byte(115), dbus.Byte(101), dbus.Byte(97)]
        self.assertEqual(nm.decode_ssid(ssid), 'Ubuntu-Battersea')

    def test_decode_ssid_utf8(self):
        ssid = [dbus.Byte(82), dbus.Byte(195), dbus.Byte(169), dbus.Byte(115),
                dbus.Byte(101), dbus.Byte(97), dbus.Byte(117)]
        self.assertEqual(nm.decode_ssid(ssid), 'Réseau')

    def test_decode_ssid_latin1(self):
        ssid = [dbus.Byte(82), dbus.Byte(233), dbus.Byte(115), dbus.Byte(101),
                dbus.Byte(97), dbus.Byte(117)]
        self.assertEqual(nm.decode_ssid(ssid), 'R\ufffdseau')

    def test_pixbuf_func(self):
        iterator = self.model.append(None, ['/foo', 'Intel', 'Wireless'])
        mock_cell = mock.Mock()
        tv = nmwidgets.NetworkManagerTreeView()
        tv.pixbuf_func(None, mock_cell, self.model, iterator, None)
        mock_cell.set_property.assert_called_with('pixbuf', None)
        # 0% strength, protected network
        i = self.model.append(iterator, ['Orange', True, 0])
        tv.pixbuf_func(None, mock_cell, self.model, i, None)
        mock_cell.set_property.assert_called_with('pixbuf', tv.icons[5])
        # 30% strength, protected network
        self.model.set_value(i, 2, 30)
        tv.pixbuf_func(None, mock_cell, self.model, i, None)
        mock_cell.set_property.assert_called_with('pixbuf', tv.icons[6])
        # 95% strength, unprotected network
        self.model.set_value(i, 1, False)
        self.model.set_value(i, 2, 95)
        tv.pixbuf_func(None, mock_cell, self.model, i, None)
        mock_cell.set_property.assert_called_with('pixbuf', tv.icons[4])

    def test_data_func(self):
        iterator = self.model.append(None, ['/foo', 'Intel', 'Wireless'])
        mock_cell = mock.Mock()
        tv = nmwidgets.NetworkManagerTreeView()
        tv.data_func(None, mock_cell, self.model, iterator, None)
        mock_cell.set_property.assert_called_with('text', 'Intel Wireless')
        i = self.model.append(iterator, ['Orange', True, 0])
        tv.data_func(None, mock_cell, self.model, i, None)
        mock_cell.set_property.assert_called_with('text', 'Orange')

if __name__ == '__main__':
    run_unittest(WidgetTests, NetworkStoreTests, NetworkManagerTests)
