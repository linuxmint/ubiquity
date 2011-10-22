#!/usr/bin/python


import unittest
# These tests require Mock 0.7.0
import mock
from test import test_support
from ubiquity import misc

import os
import pwd
import grp

_proc_swaps = [
    'Filename\t\t\t\tType\t\tSize\tUsed\tPriority',
    '/dev/sda5                               partition\t1046524\t56160\t-1']
_disk_info = ('Ubuntu-Server 10.04.1 LTS _Lucid Lynx_ '
              '- Release i386 (20100816.2)')
_proc_mounts = [
'rootfs / rootfs rw 0 0',
'none /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0',
'none /proc proc rw,nosuid,nodev,noexec,relatime 0 0',
'none /dev devtmpfs rw,relatime,size=503688k,nr_inodes=125922,mode=755 0 0',
'none /dev/pts devpts rw,nosuid,noexec,relatime,gid=5,mode=620,'
    'ptmxmode=000 0 0',
'fusectl /sys/fs/fuse/connections fusectl rw,relatime 0 0',
'/dev/disk/by-uuid/35583897-668f-4303-80a1-aa4e7f599978 / ext4 '
    'rw,relatime,errors=remount-ro,barrier=1,data=ordered 0 0',
'none /sys/kernel/debug debugfs rw,relatime 0 0',
'none /sys/kernel/security securityfs rw,relatime 0 0',
'none /dev/shm tmpfs rw,nosuid,nodev,relatime 0 0',
'none /var/run tmpfs rw,nosuid,relatime,mode=755 0 0',
'none /var/lock tmpfs rw,nosuid,nodev,noexec,relatime 0 0',
'binfmt_misc /proc/sys/fs/binfmt_misc binfmt_misc '
    'rw,nosuid,nodev,noexec,relatime 0 0',
'gvfs-fuse-daemon /home/evan/.gvfs fuse.gvfs-fuse-daemon '
    'rw,nosuid,nodev,relatime,user_id=1000,group_id=1000 0 0',
]

class MiscTests(unittest.TestCase):

    def setUp(self):
        misc.get_release.release_info = None

    @mock.patch('__builtin__.open')
    def test_is_swap(self, mock_open):
        magic = mock.MagicMock(spec=file)
        mock_open.return_value = magic
        magic.__iter__.return_value = iter(_proc_swaps)
        self.assertTrue(misc.is_swap('/dev/sda5'))
        self.assertFalse(misc.is_swap('/dev/sda'))

    @mock.patch('__builtin__.open')
    def test_is_swap_fail(self, mock_open):
        mock_open.side_effect = Exception('Ka-blamo!')
        self.assertFalse(misc.is_swap('/dev/sda5'))

    def test_format_size(self):
        self.assertEqual(misc.format_size(4 * 1000 ** 0), '4.0 B')
        self.assertEqual(misc.format_size(4 * 1000 ** 1), '4.0 kB')
        self.assertEqual(misc.format_size(4 * 1000 ** 2), '4.0 MB')
        self.assertEqual(misc.format_size(4 * 1000 ** 3), '4.0 GB')
        self.assertEqual(misc.format_size(4 * 1000 ** 4), '4.0 TB')

    def test_create_bool(self):
        self.assertIs(misc.create_bool('true'), True)
        self.assertIs(misc.create_bool('false'), False)
        # debconf will only ever return 'true' or 'false', though arguably
        # this particular behavior of returning back the parameter will bite
        # us at some point.
        self.assertIs(misc.create_bool('True'), 'True')

    def test_get_install_medium(self):
        # TODO: Need to patch out os.access and the internals of
        # raise_privileges.  If the uid is not set to 0 inside our mocked
        # os.access, raise an exception as a side effect.
        pass

    @mock.patch('__builtin__.open')
    def test_get_release(self, mock_open):
        magic = mock.MagicMock(spec=file)
        magic.__enter__.return_value = magic
        mock_open.return_value = magic
        magic.readline.return_value = _disk_info
        release = misc.get_release()
        self.assertEqual(release.name, 'Ubuntu-Server')
        self.assertEqual(release.version, '10.04.1 LTS')

    @mock.patch('__builtin__.open')
    def test_get_release_fail(self, mock_open):
        mock_open.side_effect = Exception('Pow!')
        release = misc.get_release()
        self.assertEqual(release.name, 'Linux Mint')
        self.assertEqual(release.version, '12')

    #@mock.patch('__builtin__.os.path.exists')
    #def windows_startup_folder(self, mock_exists):
    #    #mock_exists.return_value = True
    #    locations = [
    #        # Windows 7
    #        'ProgramData/Microsoft/Windows/Start Menu/Programs/Startup',
    #        # Windows XP
    #        'Documents and Settings/All Users/Start Menu/Programs/Startup',
    #        # Windows NT
    #        'Winnt/Profiles/All Users/Start Menu/Programs/Startup',
    #                ]
    #    locations_iter = iter(locations)
    #    def exists(path):
    #        return path == locations_iter.next()

    #    self.assertEqual(misc.windows_startup_folder('/tmp/tmp.XXXXXX'))

    @mock.patch('__builtin__.open')
    def test_mount_info(self, mock_open):
        magic = mock.MagicMock(spec=file)
        magic.__enter__.return_value = magic
        mock_open.return_value = magic
        # TODO come up with better mountpoints.
        magic.__iter__.return_value = iter(_proc_mounts)
        release = misc.mount_info('/dev/pts')
        self.assertEqual(release, ('none', 'devpts', 'rw'))

        magic.__iter__.return_value = iter(_proc_mounts)
        release = misc.mount_info('/proc')
        self.assertEqual(release, ('none', 'proc', 'rw'))

        magic.__iter__.return_value = iter(_proc_mounts)
        release = misc.mount_info('XXX')
        self.assertEqual(release, ('', '', ''))

    def test_debconf_escape(self):
        self.assertEqual(misc.debconf_escape('\\A test string\n'),
                         '\\\\A\\ test\\ string\\n')

    @mock.patch('ubiquity.gconftool.set_list')
    @unittest.skipIf(True, 'functionality currently broken.')
    def test_set_indicator_keymaps(self, mock_set_list):
        misc.set_indicator_keymaps('en_US.UTF-8')
        self.assertEqual(mock_set_list.call_count, 1)
        self.assertEqual(mock_set_list.call_args[0][0],
            '/desktop/gnome/peripherals/keyboard/kbd/layouts')
        self.assertEqual(mock_set_list.call_args[0][1], 'string')
        self.assertIn('us', mock_set_list.call_args[0][2])
        self.assertIn('gb', mock_set_list.call_args[0][2])
        self.assertIn('gb\tintl', mock_set_list.call_args[0][2])
        self.assertIn('gb\tmac', mock_set_list.call_args[0][2])

#class PartedServerTests(unittest.TestCase):
#    def setUp(self):
#        patcher = mock.patch('ubiquity.parted_server.PartedServer')
#        patcher.start()
#        # Probably best to patch at the dialog level rather than each method
#        # call.
#        # Maybe implement this once we have tests for PartedServer itself,
#        # with mocks we can reuse.
#        self.addCleanup(patcher.stop)
#
#    def test_boot_device(self):
#        print misc.boot_device()


class PrivilegeTests(unittest.TestCase):

    def setUp(self):
        # *whistles*
        for obj in ('os.geteuid', 'os.getuid',
                    'pwd.getpwuid', 'grp.getgrall', 'os.setgroups'):
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)

        os.geteuid.return_value = 0
        os.getuid.return_value = 0

        pwd.getpwuid.return_value.pw_name = 'fakegrp'
        gr = mock.Mock()
        gr.gr_mem = ['fakegrp']
        gr.gr_gid = 1234
        grp.getgrall.return_value = [gr]

    def tearDown(self):
        # Reset the multiple call guard.
        misc._dropped_privileges = 0

    @mock.patch('os.setegid')
    @mock.patch('os.seteuid')
    @mock.patch('os.setgroups')
    def test_drop_privileges(self, *args):
        with test_support.EnvironmentVarGuard():
            os.environ['SUDO_UID'] = '1000'
            os.environ['SUDO_GID'] = '1000'
            misc.drop_privileges()
        os.seteuid.assert_called_once_with(1000)
        os.setegid.assert_called_once_with(1000)
        os.setgroups.assert_called_once_with([1234])

    @mock.patch('os.seteuid')
    @mock.patch('os.setegid')
    @mock.patch('os.setgroups')
    def test_regain_privileges(self, *args):
        self.test_drop_privileges()
        misc.regain_privileges()
        os.seteuid.assert_called_once_with(0)
        os.setegid.assert_called_once_with(0)
        os.setgroups.assert_called_once_with([])

    @mock.patch('os.setregid')
    @mock.patch('os.setreuid')
    def test_drop_all_privileges(self, *args):
        pwd.getpwuid.return_value.pw_dir = 'fakeusr'
        with test_support.EnvironmentVarGuard():
            os.environ['SUDO_UID'] = '1000'
            os.environ['SUDO_GID'] = '1000'
            misc.drop_all_privileges()
            os.setreuid.assert_called_once_with(1000, 1000)
            os.setregid.assert_called_once_with(1000, 1000)
            os.setgroups.assert_called_once_with([1234])
            self.assertEqual(os.environ['HOME'], 'fakeusr')

if __name__ == '__main__':
    pass
    #test_support.run_unittest(MiscTests, PrivilegeTests)
