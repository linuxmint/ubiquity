#!/usr/bin/python3

import os
import shutil
import tempfile
import unittest

# These tests require Mock 0.7.0
import mock

from ubiquity import plugin_manager


ubi_prepare = plugin_manager.load_plugin('ubi-prepare')


class TestPage(unittest.TestCase):
    def setUp(self):
        self.page = ubi_prepare.Page(None)
        self.bindir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bindir)
        patcher = mock.patch.dict(
            os.environ,
            {'PATH': '%s:%s' % (self.bindir, os.environ['PATH'])})
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch('ubiquity.misc.regain_privileges')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch('ubiquity.misc.drop_privileges')
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_parted_devices(self, output):
        path = os.path.join(self.bindir, 'parted_devices')
        with open(path, 'wb') as f:
            f.write(b"#!/bin/sh\nprintf '" + output + b"'\n")
        os.chmod(path, 0o755)

    def test_free_space(self):
        self.fake_parted_devices(
            b'/dev/sda\t123004854272\tSanDisk Ultra\n'
            b'/dev/sdb\t500107862016\tSamsung SSD\n')
        self.assertEqual(500107862016, self.page.free_space())

    def test_free_space_non_utf8_model(self):
        # Some disks report model names that are not valid UTF-8
        # (linuxmint/ubiquity#62).
        self.fake_parted_devices(
            b'/dev/nvme0n1\t1024209543168\tINNOVATION\241\241IT\n')
        self.assertEqual(1024209543168, self.page.free_space())
