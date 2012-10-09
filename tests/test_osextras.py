#! /usr/bin/python3

import errno
import os
import shutil
import tempfile
from test.support import EnvironmentVarGuard
import unittest

from ubiquity import osextras


class OsextrasTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)

    def create_empty_file(self, path, mode=None):
        try:
            os.makedirs(os.path.dirname(path))
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        with open(path, "w"):
            pass
        if mode is not None:
            os.chmod(path, mode)

    def test_realpath_root_resolves_relative_paths(self):
        outer_file = os.path.join(self.temp_dir, "outer-file")
        outer_link = os.path.join(self.temp_dir, "link")
        chroot = os.path.join(self.temp_dir, "chroot")
        inner_dir = os.path.join(chroot, self.temp_dir[1:])
        inner_file = os.path.join(inner_dir, "inner-file")
        inner_file_relative = os.path.join(self.temp_dir, "inner-file")
        inner_link = os.path.join(inner_dir, "link")
        self.create_empty_file(outer_file)
        os.symlink(outer_file, outer_link)
        self.create_empty_file(inner_file)
        os.symlink(inner_file_relative, inner_link)
        self.assertEqual(
            inner_file, osextras.realpath_root(chroot, outer_link))

    def test_find_on_path_root_resolves_relative_paths(self):
        outer_bin = os.path.join(self.temp_dir, "bin")
        chroot = os.path.join(self.temp_dir, "chroot")
        inner_bin = os.path.join(chroot, self.temp_dir[1:], "bin")
        self.create_empty_file(os.path.join(outer_bin, "executable"), 0o755)
        self.create_empty_file(os.path.join(inner_bin, "executable"), 0o755)
        with EnvironmentVarGuard() as env:
            env['PATH'] = outer_bin
            self.assertTrue(osextras.find_on_path_root(chroot, "executable"))

    def test_unlink_force_unlinks_existing(self):
        path = os.path.join(self.temp_dir, "file")
        self.create_empty_file(path)
        self.assertTrue(os.path.exists(path))
        osextras.unlink_force(path)
        self.assertFalse(os.path.exists(path))

    def test_unlink_force_ignores_missing(self):
        path = os.path.join(self.temp_dir, "missing")
        self.assertFalse(os.path.exists(path))
        osextras.unlink_force(path)
        self.assertFalse(os.path.exists(path))

    def test_glob_root_resolves_relative_paths(self):
        inner_dir = os.path.join(self.temp_dir, "dir")
        expected_files = []
        for inner_file in ("file1", "file2"):
            expected_files.append(os.path.join("/dir", inner_file))
            self.create_empty_file(os.path.join(inner_dir, inner_file))
        self.assertEqual(
            sorted(expected_files),
            sorted(osextras.glob_root(self.temp_dir, "/dir/*")))
