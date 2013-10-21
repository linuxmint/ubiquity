#!/usr/bin/python3

import grp
import io
import os
import pwd
from test.support import EnvironmentVarGuard, run_unittest
import unittest

# These tests require Mock 0.7.0
import mock

from ubiquity import misc


_proc_swaps = [
    'Filename\t\t\t\tType\t\tSize\tUsed\tPriority',
    '/dev/sda5                               partition\t1046524\t56160\t-1']
_disk_info = ('Ubuntu-Server 10.04.1 LTS _Lucid Lynx_ '
              '- Release i386 (20100816.2)')
_proc_mounts = [
    'rootfs / rootfs rw 0 0',
    'none /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0',
    'none /proc proc rw,nosuid,nodev,noexec,relatime 0 0',
    ('none /dev devtmpfs '
     'rw,relatime,size=503688k,nr_inodes=125922,mode=755 0 0'),
    ('none /dev/pts devpts rw,nosuid,noexec,relatime,gid=5,mode=620,'
     'ptmxmode=000 0 0'),
    'fusectl /sys/fs/fuse/connections fusectl rw,relatime 0 0',
    ('/dev/disk/by-uuid/35583897-668f-4303-80a1-aa4e7f599978 / ext4 '
     'rw,relatime,errors=remount-ro,barrier=1,data=ordered 0 0'),
    'none /sys/kernel/debug debugfs rw,relatime 0 0',
    'none /sys/kernel/security securityfs rw,relatime 0 0',
    'none /dev/shm tmpfs rw,nosuid,nodev,relatime 0 0',
    'none /var/run tmpfs rw,nosuid,relatime,mode=755 0 0',
    'none /var/lock tmpfs rw,nosuid,nodev,noexec,relatime 0 0',
    ('binfmt_misc /proc/sys/fs/binfmt_misc binfmt_misc '
     'rw,nosuid,nodev,noexec,relatime 0 0'),
    ('gvfs-fuse-daemon /home/evan/.gvfs fuse.gvfs-fuse-daemon '
     'rw,nosuid,nodev,relatime,user_id=1000,group_id=1000 0 0'),
]


class EnvironmentVarGuardRestore(EnvironmentVarGuard):
    """Stronger version of EnvironmentVarGuard.

    This class restores os.environ even if something within its context
    manipulates os.environ directly.
    """

    def __init__(self):
        EnvironmentVarGuard.__init__(self)
        self._environ = self._environ.copy()


class MiscTests(unittest.TestCase):

    def setUp(self):
        misc.get_release.release_info = None

    @mock.patch('builtins.open')
    def test_is_swap(self, mock_open):
        magic = mock.MagicMock(spec=io.TextIOBase)
        mock_open.return_value = magic
        magic.__enter__.return_value = magic
        magic.__iter__.return_value = iter(_proc_swaps)
        self.assertTrue(misc.is_swap('/dev/sda5'))
        self.assertFalse(misc.is_swap('/dev/sda'))

    @mock.patch('builtins.open')
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

    @mock.patch('builtins.open')
    def test_get_release(self, mock_open):
        magic = mock.MagicMock(spec=io.TextIOBase)
        magic.__enter__.return_value = magic
        mock_open.return_value = magic
        magic.readline.return_value = _disk_info
        release = misc.get_release()
        self.assertEqual(release.name, 'Ubuntu Server')
        self.assertEqual(release.version, '10.04.1 LTS')

    @mock.patch('builtins.open')
    def test_get_release_fail(self, mock_open):
        mock_open.side_effect = Exception('Pow!')
        release = misc.get_release()
        self.assertEqual(release.name, 'Ubuntu')
        self.assertEqual(release.version, '')

    #@mock.patch('os.path.exists')
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

    @mock.patch('builtins.open')
    def test_mount_info(self, mock_open):
        magic = mock.MagicMock(spec=io.TextIOBase)
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

    @mock.patch('ubiquity.gsettings.set_list')
    @mock.patch('ubiquity.misc.execute')
    def test_set_indicator_keymaps_english(self, mock_execute, mock_set_list):
        misc.set_indicator_keymaps('en')
        self.assertEqual(mock_execute.call_count, 1)
        self.assertEqual(mock_execute.call_args[0][0], 'setxkbmap')
        self.assertEqual(mock_set_list.call_count, 1)
        self.assertEqual(
            mock_set_list.call_args[0][0], 'org.gnome.libgnomekbd.keyboard')
        self.assertEqual(mock_set_list.call_args[0][1], 'layouts')
        self.assertEqual('us', mock_set_list.call_args[0][2][0])
        self.assertEqual(len(mock_set_list.call_args[0][2]), 4)

    @mock.patch('ubiquity.gsettings.set_list')
    @mock.patch('ubiquity.misc.execute')
    def test_set_indicator_keymaps_french(self, mock_execute, mock_set_list):
        misc.set_indicator_keymaps('fr')
        self.assertEqual(mock_execute.call_count, 1)
        self.assertEqual(mock_execute.call_args[0][0], 'setxkbmap')
        self.assertEqual(mock_set_list.call_count, 1)
        self.assertEqual(
            mock_set_list.call_args[0][0], 'org.gnome.libgnomekbd.keyboard')
        self.assertEqual(mock_set_list.call_args[0][1], 'layouts')
        self.assertEqual('fr\toss', mock_set_list.call_args[0][2][0])
        self.assertEqual(len(mock_set_list.call_args[0][2]), 4)

    @mock.patch('ubiquity.gsettings.set_list')
    @mock.patch('ubiquity.misc.execute')
    def test_set_indicator_keymaps_variants(self, mock_execute, mock_set_list):
        misc.set_indicator_keymaps('sv')
        self.assertEqual(mock_execute.call_count, 1)
        self.assertEqual(mock_execute.call_args[0][0], 'setxkbmap')
        self.assertEqual(mock_set_list.call_count, 1)
        self.assertEqual(
            mock_set_list.call_args[0][0], 'org.gnome.libgnomekbd.keyboard')
        self.assertEqual(mock_set_list.call_args[0][1], 'layouts')
        self.assertIn('se\tdvorak', mock_set_list.call_args[0][2])

    @mock.patch('ubiquity.gsettings.set_list')
    @mock.patch('ubiquity.misc.execute')
    def test_set_indicator_keymaps_ta(self, mock_execute, mock_set_list):
        misc.set_indicator_keymaps('ta')
        self.assertEqual(mock_execute.call_count, 1)
        self.assertEqual(mock_execute.call_args[0][0], 'setxkbmap')
        self.assertEqual(mock_set_list.call_count, 1)
        self.assertEqual(
            mock_set_list.call_args[0][0], 'org.gnome.libgnomekbd.keyboard')
        self.assertEqual(mock_set_list.call_args[0][1], 'layouts')
        self.assertEqual('in\ttam', mock_set_list.call_args[0][2][0])
        self.assertEqual(len(mock_set_list.call_args[0][2]), 4)

    @mock.patch('ubiquity.gsettings.set_list')
    @mock.patch('ubiquity.misc.execute')
    def test_set_indicator_keymaps_simplified_chinese(self, mock_execute,
                                                      mock_set_list):
        misc.set_indicator_keymaps('zh_CN')
        self.assertEqual(mock_execute.call_count, 1)
        self.assertEqual(mock_execute.call_args[0][0], 'setxkbmap')
        self.assertEqual(mock_set_list.call_count, 1)
        self.assertEqual(
            mock_set_list.call_args[0][0], 'org.gnome.libgnomekbd.keyboard')
        self.assertEqual(mock_set_list.call_args[0][1], 'layouts')
        self.assertEqual('cn', mock_set_list.call_args[0][2][0])
        self.assertEqual(len(mock_set_list.call_args[0][2]), 1)

    @mock.patch('ubiquity.gsettings.set_list')
    @mock.patch('ubiquity.misc.execute')
    def test_set_indicator_keymaps_unknown(self, mock_execute, mock_set_list):
        misc.set_indicator_keymaps('unknownlanguage')
        self.assertEqual(mock_execute.call_count, 0)
        self.assertEqual(mock_set_list.call_count, 0)

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
        pwd.getpwuid.return_value.pw_gid = '1000'
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
        with EnvironmentVarGuard() as env:
            env['PKEXEC_UID'] = '1000'
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
        with EnvironmentVarGuardRestore():
            os.environ['PKEXEC_UID'] = '1000'
            misc.drop_all_privileges()
            os.setreuid.assert_called_once_with(1000, 1000)
            os.setregid.assert_called_once_with(1000, 1000)
            os.setgroups.assert_called_once_with([1234])
            self.assertEqual(os.environ['HOME'], 'fakeusr')


class GrubDefaultTests(unittest.TestCase):
    """Support for testing ubiquity.misc.grub_default.

    This class mocks several methods to make it possible to test
    ubiquity.misc.grub_default.  Individual tests should set self.devices to
    a list of elements as follows:

        [grub_dev, os_dev, by_id_dev]

    grub_dev should not be surrounded with (); os_dev should not be prefixed
    with /dev/; by_id_dev should not be prefixed with /dev/disk/by-id/.

    For example:

        [
            ['hd0', 'sda', 'serial-number-for-sda'],
            ['hd1', 'sdb', 'serial-number-for-sdb'],
        ]

    Tests should also set self.cdrom_mount to a (disk, fs_type) pair, e.g.
    ('/dev/sr0', 'iso9660'), may set self.removable_devices to a list of
    paths to removable devices, e.g. ['/dev/sdb'], and may set
    self.boot_device to the path to a device containing /boot, e.g.
    '/dev/sdb'.
    """

    def setUp(self):
        to_patch = (
            'os.path.realpath',
            'os.path.samefile',
            'ubiquity.misc.boot_device',
            'ubiquity.misc.cdrom_mount_info',
            'ubiquity.misc.grub_device_map',
            'ubiquity.misc.is_removable',
        )
        for obj in to_patch:
            patcher = mock.patch(obj)
            patcher.start()
            self.addCleanup(patcher.stop)

        os.path.realpath.side_effect = self.realpath_side_effect
        os.path.samefile.side_effect = self.samefile_side_effect
        misc.boot_device.side_effect = self.boot_device_side_effect
        misc.cdrom_mount_info.side_effect = self.cdrom_mount_info_side_effect
        misc.grub_device_map.side_effect = self.grub_device_map_side_effect
        misc.is_removable.side_effect = self.is_removable_side_effect

        self.removable_devices = []
        self.boot_device = None

    def iter_devices(self):
        """Iterate through devices, expanding abbreviated forms."""
        for grub_dev, os_dev, by_id_dev in self.devices:
            yield ('(%s)' % grub_dev, '/dev/%s' % os_dev,
                   '/dev/disk/by-id/%s' % by_id_dev)

    def realpath_side_effect(self, filename):
        filename = os.path.abspath(filename)
        for _, os_dev, by_id_dev in self.iter_devices():
            if filename in (os_dev, by_id_dev):
                return os_dev
        return filename

    def samefile_side_effect(self, f1, f2):
        f1 = os.path.abspath(f1)
        f2 = os.path.abspath(f2)
        if f1 == f2:
            return True
        for _, os_dev, by_id_dev in self.iter_devices():
            if f1 == os_dev and f2 == by_id_dev:
                return True
            elif f1 == by_id_dev and f2 == os_dev:
                return True
        return False

    def boot_device_side_effect(self):
        return self.boot_device

    def cdrom_mount_info_side_effect(self):
        return list(self.cdrom_mount)

    def grub_device_map_side_effect(self):
        device_map = []
        for grub_dev, _, by_id_dev in self.iter_devices():
            device_map.append('%s\t%s' % (grub_dev, by_id_dev))
        return device_map

    def is_removable_side_effect(self, device):
        if device in self.removable_devices:
            return device
        else:
            return None

    def test_removable(self):
        self.devices = [['hd0', 'sda', 'serial-number-for-sda']]
        self.cdrom_mount = ('/dev/sr0', 'iso9660')
        self.boot_device = '/dev/sdb'
        self.removable_devices = [self.boot_device]
        self.assertEqual('/dev/sdb', misc.grub_default())

    def test_use_first_disk(self):
        self.devices = [
            ['hd0', 'sda', 'disk-1'],
            ['hd1', 'sdb', 'disk-2'],
        ]
        self.cdrom_mount = ('/dev/sr0', 'vfat')
        self.assertEqual('/dev/sda', misc.grub_default())

    @mock.patch('ubiquity.misc.drop_privileges')
    @mock.patch('ubiquity.misc.regain_privileges')
    def test_avoid_cdrom(self, *args):
        self.devices = [
            ['hd0', 'sda', 'cdrom'],
            ['hd1', 'sdb', 'disk'],
        ]
        self.cdrom_mount = ('/dev/sda', 'vfat')
        self.assertEqual('/dev/sdb', misc.grub_default())
        self.cdrom_mount = ('/dev/disk/by-id/cdrom', 'vfat')
        self.assertEqual('/dev/sdb', misc.grub_default())

    def test_usb_iso9660(self):
        self.devices = [
            ['hd0', 'sda', 'usb'],
            ['hd1', 'sdb', 'disk'],
        ]
        self.cdrom_mount = ('/dev/sda', 'iso9660')
        self.removable_devices = ['/dev/sda']
        self.boot_device = None
        self.assertEqual('/dev/sdb', misc.grub_default())
        self.boot_device = '/dev/sdb'
        self.assertEqual('/dev/sdb', misc.grub_default())
        self.devices = [
            ['hd0', 'sda', 'disk'],
            ['hd1', 'sdb', 'usb'],
        ]
        self.cdrom_mount = ('/dev/sdb', 'iso9660')
        self.removable_devices = ['/dev/sdb']
        self.boot_device = None
        self.assertEqual('/dev/sda', misc.grub_default())
        self.boot_device = '/dev/sda'
        self.assertEqual('/dev/sda', misc.grub_default())


if __name__ == '__main__':
    run_unittest(MiscTests, PrivilegeTests, GrubDefaultTests)
