#! /usr/bin/python3
# -*- coding: utf-8; -*-

import io
import os
import unittest

import mock

from ubiquity import filteredcommand


class FilteredCommandTests(unittest.TestCase):
    def setUp(self):
        os.environ['UBIQUITY_DEBUG_CORE'] = '1'
        # The situation with Python 3 is more pleasant than it used to be
        # with Python 2, although no less fiddly to test.  sys.stderr is an
        # io.TextIOWrapper object in the default locale encoding and with
        # errors="backslashreplace"; so we can mock up one of these with the
        # worst-case locale encoding of ASCII.
        new_stderr = io.TextIOWrapper(
            io.BytesIO(), encoding='ASCII', errors='backslashreplace')
        patcher = mock.patch('sys.stderr', new_stderr)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        del os.environ['UBIQUITY_DEBUG_CORE']

    def write_side_effect(self, *args, **kwargs):
        for arg in args:
            if isinstance(arg, str):
                arg.encode('ascii')

    def test_debug_unicode(self):
        variant = "Arménien"
        filteredcommand.UntrustedBase.debug(
            "Unknown keyboard variant %s", variant)

    def test_debug_bytes(self):
        variant = b"English"
        filteredcommand.UntrustedBase.debug(
            "Unknown keyboard variant %s", variant)
