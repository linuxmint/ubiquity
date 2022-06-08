#!/usr/bin/python3

import os
import unittest
import unittest.mock
from test.support import run_unittest

import debconf

from ubiquity import plugin_manager

ubi_console_setup = plugin_manager.load_plugin("ubi-console-setup")


@unittest.skipUnless("DEBCONF_SYSTEMRC" in os.environ, "Need a database.")
class TestPageBase(unittest.TestCase):
    def setUp(self):
        # We could mock out the db for this, but we ultimately want to make
        # sure that the debconf questions it's getting exist.
        self.page = ubi_console_setup.Page(None, ui=unittest.mock.Mock())
        self.page.db = debconf.DebconfCommunicator("ubi-test", cloexec=True)
        self.addCleanup(self.page.db.shutdown)


class TestPage(TestPageBase):
    DEFAULT_ENGLISH_KEYBOARDS = [
        ("xkb", "us"),
        ("xkb", "au"),
        ("xkb", "cm"),
        ("xkb", "gb"),
    ]

    @unittest.mock.patch("ubi-console-setup.gsettings.set_list")
    def test_set_gnome_keyboard_layout_with_variant(self, set_list_mock):
        self.page.gnome_input_sources = self.DEFAULT_ENGLISH_KEYBOARDS
        self.page.set_gnome_keyboard_layout("de", "neo")
        set_list_mock.assert_has_calls(
            [
                unittest.mock.call(
                    "org.gnome.desktop.input-sources",
                    "sources",
                    [("xkb", "de+neo")],
                ),
                unittest.mock.call(
                    "org.gnome.desktop.input-sources",
                    "sources",
                    [("xkb", "de+neo")] + self.DEFAULT_ENGLISH_KEYBOARDS,
                ),
            ]
        )

    @unittest.mock.patch("ubi-console-setup.gsettings.set_list")
    def test_set_gnome_keyboard_layout_without_variant(self, set_list_mock):
        self.page.gnome_input_sources = self.DEFAULT_ENGLISH_KEYBOARDS
        self.page.set_gnome_keyboard_layout("de", "")
        set_list_mock.assert_has_calls(
            [
                unittest.mock.call(
                    "org.gnome.desktop.input-sources",
                    "sources",
                    [("xkb", "de")],
                ),
                unittest.mock.call(
                    "org.gnome.desktop.input-sources",
                    "sources",
                    [("xkb", "de")] + self.DEFAULT_ENGLISH_KEYBOARDS,
                ),
            ]
        )

    @unittest.mock.patch("ubi-console-setup.gsettings.set_list")
    def test_set_gnome_keyboard_layout_to_existing_layout(self, set_list_mock):
        self.page.gnome_input_sources = self.DEFAULT_ENGLISH_KEYBOARDS
        self.page.set_gnome_keyboard_layout("gb", "")
        set_list_mock.assert_has_calls(
            [
                unittest.mock.call(
                    "org.gnome.desktop.input-sources",
                    "sources",
                    [("xkb", "gb")],
                ),
                unittest.mock.call(
                    "org.gnome.desktop.input-sources",
                    "sources",
                    self.DEFAULT_ENGLISH_KEYBOARDS,
                ),
            ]
        )

    @unittest.mock.patch("ubi-console-setup.gsettings.set_list")
    def test_set_gnome_keyboard_layout_with_empty_input_sources(
        self, set_list_mock
    ):
        self.page.gnome_input_sources = None
        self.page.set_gnome_keyboard_layout("us", "")
        set_list_mock.assert_called_once_with(
            "org.gnome.desktop.input-sources", "sources", [("xkb", "us")]
        )


if __name__ == "__main__":
    run_unittest(TestPage)  # pragma: no cover
