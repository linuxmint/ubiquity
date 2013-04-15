#! /usr/bin/python3

import os
import shutil
import tempfile
import unittest

from ubiquity import install_misc


class InstallMiscTests(unittest.TestCase):
    def setUp(self):
        self.source = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.source)
        self.target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.target)

    def source_path(self, relpath):
        return os.path.join(self.source, relpath)

    def target_path(self, relpath):
        return os.path.join(self.target, relpath)

    def try_remove_target(self, relpath):
        # Imitate the copy_all context in which remove_target is normally
        # run.
        st = os.lstat(self.source_path(relpath))
        install_misc.remove_target(self.source, self.target, relpath, st)

    def test_remove_target_ignores_nonexistent(self):
        with open(self.source_path("not-in-target"), "w"):
            pass
        self.try_remove_target("not-in-target")

    def test_remove_target_for_directory_leaves_directory(self):
        os.mkdir(self.source_path("dir"))
        os.mkdir(self.target_path("dir"))
        self.try_remove_target("dir")
        self.assertTrue(os.path.isdir(self.target_path("dir")))

    def test_remove_target_removes_non_directory(self):
        os.mkdir(self.source_path("source-dir-target-file"))
        with open(self.target_path("source-dir-target-file"), "w"):
            pass
        self.try_remove_target("source-dir-target-file")
        self.assertFalse(os.path.exists(
            self.target_path("source-dir-target-file")))

    def test_remove_target_removes_empty_directory(self):
        with open(self.source_path("source-file-target-empty-dir"), "w"):
            pass
        os.mkdir(self.target_path("source-file-target-empty-dir"))
        self.try_remove_target("source-file-target-empty-dir")
        self.assertFalse(os.path.exists(
            self.target_path("source-file-target-empty-dir")))

    def test_remove_target_moves_symlink_target_nonexistent(self):
        os.makedirs(self.source_path("usr/local"))
        os.symlink("share/man", self.source_path("usr/local/man"))
        os.makedirs(self.target_path("usr/local/man"))
        with open(self.target_path("usr/local/man/file"), "w"):
            pass
        self.try_remove_target("usr/local/man")
        self.assertFalse(os.path.exists(self.target_path("usr/local/man")))
        self.assertTrue(
            os.path.isdir(self.target_path("usr/local/share/man")))
        self.assertTrue(
            os.path.isfile(self.target_path("usr/local/share/man/file")))

    def test_remove_target_moves_absolute_symlink_target_nonexistent(self):
        os.makedirs(self.source_path("usr/local"))
        os.symlink("/usr/local/share/man", self.source_path("usr/local/man"))
        os.makedirs(self.target_path("usr/local/man"))
        with open(self.target_path("usr/local/man/file"), "w"):
            pass
        self.try_remove_target("usr/local/man")
        self.assertFalse(os.path.exists(self.target_path("usr/local/man")))
        self.assertTrue(
            os.path.isdir(self.target_path("usr/local/share/man")))
        self.assertTrue(
            os.path.isfile(self.target_path("usr/local/share/man/file")))

    def test_remove_target_moves_symlink_target_empty_directory(self):
        os.makedirs(self.source_path("usr/local"))
        os.symlink("share/man", self.source_path("usr/local/man"))
        os.makedirs(self.target_path("usr/local/man"))
        with open(self.target_path("usr/local/man/file"), "w"):
            pass
        os.makedirs(self.target_path("usr/local/share/man"))
        self.try_remove_target("usr/local/man")
        self.assertFalse(os.path.exists(self.target_path("usr/local/man")))
        self.assertTrue(
            os.path.isdir(self.target_path("usr/local/share/man")))
        self.assertTrue(
            os.path.isfile(self.target_path("usr/local/share/man/file")))

    def test_remove_target_backs_up_non_empty_directory(self):
        with open(self.source_path("source-file-target-non-empty-dir"), "w"):
            pass
        os.mkdir(self.target_path("source-file-target-non-empty-dir"))
        tp = self.target_path("source-file-target-non-empty-dir/file")
        with open(tp, "w"):
            pass
        self.try_remove_target("source-file-target-non-empty-dir")
        self.assertFalse(os.path.exists(
            self.target_path("source-file-target-non-empty-dir")))
        self.assertTrue(os.path.isdir(
            self.target_path("source-file-target-non-empty-dir.bak")))
        self.assertTrue(os.path.isfile(
            self.target_path("source-file-target-non-empty-dir.bak/file")))
