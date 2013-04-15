#!/usr/bin/python3

from itertools import zip_longest
import os
from test.support import run_unittest
import unittest

import debconf
# These tests require Mock 0.7.0
import mock

from ubiquity import misc, plugin_manager


ubi_partman = plugin_manager.load_plugin('ubi-partman')


def question_has_variables(question, lookup_variables):
    existing_variables = []
    found_question = False
    if 'UBIQUITY_TEST_INSTALLED' in os.environ:
        templates_dat = '/var/cache/debconf/templates.dat'
    else:
        templates_dat = 'tests/templates.dat'
    # Templates files are (at least in theory) mixed-encoding, so we must
    # treat them as binary data and decode only marked elements.  In this
    # function, we only care about question and variable names, which should
    # always be ASCII.
    with open(templates_dat, 'rb') as templates:
        for line in templates:
            if found_question and line == b'\n':
                break

            if line.startswith(('Name: %s' % question).encode()):
                found_question = True
                continue
            elif not found_question:
                continue

            if line.startswith(b'Description:'):
                last = 13
            elif line.startswith(b'Extended_description:'):
                last = 22
            else:
                continue

            while True:
                start = line.find(b'${', last)
                if start != -1:
                    end = line.find(b'}', last)
                    if end != -1:
                        existing_variables.append(line[start + 2:end].decode())
                        last = end + 1
                    else:
                        exc = ('Expected to find } on \'%s\'' %
                               line.decode(errors='replace'))
                        raise EOFError(exc)
                else:
                    break
    if not found_question:
        raise AssertionError('Never found the question: %s' % question)
    only_in_lookup = set(lookup_variables) - set(existing_variables)
    only_in_template = set(existing_variables) - set(lookup_variables)
    if only_in_lookup or only_in_template:
        raise AssertionError(
            ('%s\nOnly in lookup: %s\nOnly in template: %s' % (
                question, ', '.join(only_in_lookup),
                ', '.join(only_in_template))))


# These tests skip when their dependencies are not met and tests/run takes
# arguments to generate said dependencies, so neither need to know about the
# inner workings of each other.

@unittest.skipUnless('UBIQUITY_TEST_INSTALLED' in os.environ or
                     os.path.exists('tests/partman-tree'),
                     'Need /lib/partman.')
class PartmanPageDirectoryTests(unittest.TestCase):
    def setUp(self):
        # We could mock out the db for this, but we ultimately want to make
        # sure that the debconf questions its getting exist.
        self.page = ubi_partman.Page(None)
        self.page.db = debconf.DebconfCommunicator('ubi-test', cloexec=True)
        self.addCleanup(self.page.db.shutdown)

        if 'UBIQUITY_TEST_INSTALLED' not in os.environ:
            self.mock_partman_tree()

        # Don't cache descriptions.
        self.page.description_cache = {}

    def mock_partman_tree(self):
        prefix = 'tests/partman-tree'

        def side_effect_factory(real_method):
            def side_effect(path, *args, **kw):
                if path.startswith('/lib/partman'):
                    return real_method('%s%s' % (prefix, path), *args, **kw)
                else:
                    return real_method(path, *args, **kw)
            return side_effect

        for method in ('listdir', 'path.isdir', 'access', 'path.exists'):
            if method.startswith('path'):
                real_method = getattr(os.path, method.split('.')[1])
            else:
                real_method = getattr(os, method)
            method = mock.patch('os.%s' % method)
            mocked_method = method.start()
            mocked_method.side_effect = side_effect_factory(real_method)
            self.addCleanup(method.stop)

    #def test_filesystem_description(self):
    #    for fs in self.page.scripts('/lib/partman/valid_filesystems'):
    #        print self.page.filesystem_description(fs)

    #def test_method_description(self):
    #    for method in self.page.subdirectories('/lib/partman/choose_method'):
    #        if method != 'dont_use':
    #            self.assertNotEqual(method,
    #                                self.page.method_description(method))


# A couple of mock helpers for some of the tests below.
def _fake_grub_options(*paths):
    # The interface expects a sequence-of-sequences, although the method
    # only cares about sub-sequences of length 1, where the path is
    # element zero.
    def grub_options():
        return [(path,) for path in paths]

    return grub_options


def _fake_grub_default(default):
    def grub_default():
        return default

    return grub_default


@unittest.skipUnless('DEBCONF_SYSTEMRC' in os.environ, 'Need a database.')
class TestPageBase(unittest.TestCase):
    def setUp(self):
        # We could mock out the db for this, but we ultimately want to make
        # sure that the debconf questions it's getting exist.
        self.page = ubi_partman.Page(None, ui=mock.Mock())
        self.page.db = debconf.DebconfCommunicator('ubi-test', cloexec=True)
        self.addCleanup(self.page.db.shutdown)

        # Don't cache descriptions.
        self.page.description_cache = {}


class TestPage(TestPageBase):
    def test_description(self):
        question = 'partman-auto/init_automatically_partition'
        description = misc.utf8(self.page.db.metaget(question, 'description'),
                                'replace')
        self.assertEqual(self.page.description(question), description)
        self.assertIn(question, self.page.description_cache)

    def test_default_mountpoint_choices(self):
        pairs = [('partman-basicfilesystems/fat_mountpoint', 'ntfs'),
                 ('partman-basicfilesystems/mountpoint', 'ext4')]
        try:
            # We cannot test uboot if we're not running on armel/armhf.
            self.page.description('partman-uboot/mountpoint')
            pairs.append(('partman-uboot/mountpoint', 'uboot'))
        except debconf.DebconfError:
            pass
        for question, fs in pairs:
            choices = self.page.choices_untranslated(question)
            mountpoints = [choice.split(' ', 1)[0] for choice in choices
                           if choice.startswith('/')]
            default_mountpoints = [default[0] for default in
                                   self.page.default_mountpoint_choices(fs)]
            self.assertTrue(len(default_mountpoints) > 0)
            self.assertCountEqual(mountpoints, default_mountpoints)

    def test_method_description(self):
        # FIXME: move this into the Directory tests, following use_as()
        pairs = [('swap', 'partman/method_long/swap'),
                 ('biosgrub', 'partman/method_long/biosgrub')]
        try:
            # We cannot test efi if we're not running on x86.
            self.page.description('partman-efi/text/efi')
            pairs.append(('efi', 'partman-efi/text/efi'))
        except debconf.DebconfError:
            pass
        try:
            # We cannot test newworld if we're not running on powerpc.
            self.page.description('partman/method_long/newworld')
            pairs.append(('newworld', 'partman/method_long/newworld'))
        except debconf.DebconfError:
            pass
        for method, question in pairs:
            self.assertEqual(self.page.description(question),
                             self.page.method_description(method))
        self.assertEqual(self.page.method_description('foobar'), 'foobar')

    def test_calculate_autopartitioning_heading(self):
        oses = []
        has_ubuntu = False
        head = self.page.calculate_autopartitioning_heading(oses, has_ubuntu)
        q = 'ubiquity/partitioner/heading_no_detected'
        no_detected = self.page.extended_description(q)
        self.assertEqual(no_detected, head)


@unittest.skipUnless(os.environ['DEB_HOST_ARCH'] in ('amd64', 'i386'),
                     'GRUB-related tests are only relevant on x86')
class TestPageGrub(TestPageBase):
    def test_maybe_update_dont_install(self):
        self.page.install_bootloader = False
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 0)

    @mock.patch('ubiquity.misc.grub_options', _fake_grub_options('/dev/vda1'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_maybe_update_install(self):
        self.page.install_bootloader = True
        self.page.disk_cache = {}
        self.page.partition_cache = {}
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)

    @mock.patch('ubiquity.misc.grub_options', _fake_grub_options('/dev/vda1'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_install_grub_to_valid_filesystem(self):
        # Return some fake grub options.
        self.page.install_bootloader = True
        self.page.disk_cache = {
            'ignore-1': {
                'device': '/dev/vda',
            },
        }
        self.page.partition_cache = {
            'ignore': {
                'parted': {
                    'path': '/dev/vda1',
                    'fs': 'ext4',
                }
            }
        }
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)
        self.page.ui.set_grub_options.assert_called_once_with('/dev/vda', {
            '/dev/vda': True,
            '/dev/vda1': True,
        })

    @mock.patch('ubiquity.misc.grub_options', _fake_grub_options('/dev/vda1'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_install_grub_to_invalid_filesystem(self):
        # Return some fake grub options.
        self.page.install_bootloader = True
        self.page.disk_cache = {
            'ignore-1': {
                'device': '/dev/vda',
            },
        }
        self.page.partition_cache = {
            'ignore': {
                'parted': {
                    'path': '/dev/vda1',
                    'fs': 'xfs',
                }
            }
        }
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)
        self.page.ui.set_grub_options.assert_called_once_with('/dev/vda', {
            '/dev/vda': True,
            '/dev/vda1': False,
        })

    @mock.patch('ubiquity.misc.grub_options',
                _fake_grub_options('/dev/vda1', '/dev/vda2'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_install_grub_to_mixed_filesystems(self):
        # Return some fake grub options.
        self.page.install_bootloader = True
        self.page.disk_cache = {
            'ignore-1': {
                'device': '/dev/vda',
            },
        }
        self.page.partition_cache = {
            'ignore-1': {
                'parted': {
                    'path': '/dev/vda1',
                    'fs': 'xfs',
                }
            },
            'ignore-2': {
                'parted': {
                    'path': '/dev/vda2',
                    'fs': 'ext2',
                }
            }
        }
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)
        self.page.ui.set_grub_options.assert_called_once_with('/dev/vda', {
            '/dev/vda': True,
            '/dev/vda1': False,
            '/dev/vda2': True,
        })

    @mock.patch('ubiquity.misc.grub_options',
                _fake_grub_options('/dev/vda1', '/dev/vda2', '/dev/vdb1'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_install_grub_offers_to_install_to_disk(self):
        # Return some fake grub options.
        self.page.install_bootloader = True
        self.page.disk_cache = {
            'ignore-1': {
                'device': '/dev/vda',
            },
            'ignore-2': {
                'device': '/dev/vdb',
            },
        }
        self.page.partition_cache = {
            'ignore-1': {
                'parted': {
                    'path': '/dev/vda1',
                    'fs': 'xfs',
                },
            },
            'ignore-2': {
                'parted': {
                    'path': '/dev/vda2',
                    'fs': 'ext2',
                },
            },
            'ignore-3': {
                'parted': {
                    'path': '/dev/vdb1',
                    'fs': 'xfs',
                },
            },
        }
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)
        self.page.ui.set_grub_options.assert_called_once_with('/dev/vda', {
            '/dev/vda': True,
            '/dev/vdb': True,
            '/dev/vda1': False,
            '/dev/vda2': True,
            '/dev/vdb1': False,
        })

    @mock.patch('ubiquity.misc.grub_options',
                _fake_grub_options('/dev/vda1', '/dev/vda2', '/dev/vdb1'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_install_grub_offers_to_install_to_all_but_jfs(self):
        # Return some fake grub options.
        self.page.install_bootloader = True
        self.page.disk_cache = {
            'ignore-1': {
                'device': '/dev/vda',
            },
            'ignore-2': {
                'device': '/dev/vdb',
            },
        }
        self.page.partition_cache = {
            'ignore-1': {
                'parted': {
                    'path': '/dev/vda1',
                    'fs': 'ext4',
                },
            },
            'ignore-2': {
                'parted': {
                    'path': '/dev/vda2',
                    'fs': 'ext2',
                },
            },
            'ignore-3': {
                'parted': {
                    'path': '/dev/vdb1',
                    'fs': 'jfs',
                },
            },
        }
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)
        self.page.ui.set_grub_options.assert_called_once_with('/dev/vda', {
            '/dev/vda': True,
            '/dev/vdb': True,
            '/dev/vda1': True,
            '/dev/vda2': True,
            '/dev/vdb1': False,
        })

    @mock.patch('ubiquity.misc.grub_options',
                _fake_grub_options('/dev/vda1', '/dev/vda2', '/dev/vdb1'))
    @mock.patch('ubiquity.misc.grub_default', _fake_grub_default('/dev/vda'))
    def test_install_grub_offers_to_install_to_all(self):
        # Return some fake grub options.
        self.page.install_bootloader = True
        self.page.disk_cache = {
            'ignore-1': {
                'device': '/dev/vda',
            },
            'ignore-2': {
                'device': '/dev/vdb',
            },
        }
        self.page.partition_cache = {
            'ignore-1': {
                'parted': {
                    'path': '/dev/vda1',
                    'fs': 'ext4',
                },
            },
            'ignore-2': {
                'parted': {
                    'path': '/dev/vda2',
                    'fs': 'ext2',
                },
            },
            'ignore-3': {
                'parted': {
                    'path': '/dev/vdb1',
                    'fs': 'fat16',
                },
            },
        }
        self.page.maybe_update_grub()
        self.assertEqual(self.page.ui.set_grub_options.call_count, 1)
        self.page.ui.set_grub_options.assert_called_once_with('/dev/vda', {
            '/dev/vda': True,
            '/dev/vdb': True,
            '/dev/vda1': True,
            '/dev/vda2': True,
            '/dev/vdb1': True,
        })


@unittest.skipUnless('DEBCONF_SYSTEMRC' in os.environ, 'Need a database.')
class TestCalculateAutopartitioningOptions(unittest.TestCase):
    '''Test that the each expected autopartitioning option exists and is
       worded properly.'''

    def setUp(self):
        # We could mock out the db for this, but we ultimately want to make
        # sure that the debconf questions its getting exist.
        self.page = ubi_partman.Page(None)
        self.page.db = debconf.DebconfCommunicator('ubi-test', cloexec=True)
        self.addCleanup(self.page.db.shutdown)

        find_in_os_prober = mock.patch('ubiquity.misc.find_in_os_prober')
        find_in_os_prober.start()
        self.addCleanup(find_in_os_prober.stop)

        get_release = mock.patch('ubiquity.misc.get_release')
        get_release.start()
        self.addCleanup(get_release.stop)
        self.release = misc.ReleaseInfo('Ubuntu', '11.04')
        misc.get_release.return_value = self.release

        # Don't cache descriptions.
        self.page.description_cache = {}

        # Always checked, never SUBST'ed.
        question = 'ubiquity/partitioner/advanced'
        question_has_variables(question, ['DISTRO'])
        self.page.db.subst(question, 'DISTRO', self.release.name)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        self.manual = ubi_partman.PartitioningOption(title, desc)

    # 'This computer currently has Windows on it.'
    def test_windows_only(self):
        operating_system = 'Windows XP'
        misc.find_in_os_prober.return_value = operating_system
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ntfs')
        layout = {'=dev=sda': [part]}
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        self.page.extra_options['resize'] = {
            '=dev=sda': ['', 0, 0, 0, '', 0, 'ntfs']}

        question = 'ubiquity/partitioner/single_os_resize'
        question_has_variables(question, ['OS', 'DISTRO'])
        # Ensure that we're not grabbing the value from previous runs.
        self.page.db.subst(question, 'OS', operating_system)
        self.page.db.subst(question, 'DISTRO', self.release.name)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        resize = ubi_partman.PartitioningOption(title, desc)

        question = 'ubiquity/partitioner/single_os_replace'
        question_has_variables(question, ['OS', 'DISTRO'])
        self.page.db.subst(question, 'OS', operating_system)
        self.page.db.subst(question, 'DISTRO', self.release.name)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        replace = ubi_partman.PartitioningOption(title, desc)

        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems(layout)
        options = self.page.calculate_autopartitioning_options(
            operating_systems, ubuntu_systems)
        self.assertIn('resize', options)
        self.assertCountEqual(resize, options['resize'])
        self.assertIn('use_device', options)
        self.assertCountEqual(replace, options['use_device'])
        self.assertIn('manual', options)
        self.assertCountEqual(self.manual, options['manual'])

    # 'This computer currently has no operating systems on it.'
    def test_empty(self):
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        question = 'ubiquity/partitioner/no_systems_format'
        question_has_variables(question, ['DISTRO'])
        self.page.db.subst(question, 'DISTRO', self.release.name)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        use_device = ubi_partman.PartitioningOption(title, desc)
        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems([])
        options = self.page.calculate_autopartitioning_options(
            operating_systems, ubuntu_systems)

        self.assertIn('use_device', options)
        self.assertCountEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertCountEqual(self.manual, options['manual'])

    # 'This computer currently has Ubuntu 10.04 on it.'
    def test_older_ubuntu_only(self):
        operating_system = 'Ubuntu 10.04'
        operating_version = '10.04'

        def side_effect(*args, **kwargs):
            if 'with_version' in kwargs:
                return operating_system, operating_version
            return operating_system

        misc.find_in_os_prober.side_effect = side_effect
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        layout = {'=dev=sda': [part]}
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        self.page.extra_options['reuse'] = [(0, '/dev/sda1')]

        question = 'ubiquity/partitioner/ubuntu_format'
        question_has_variables(question, ['CURDISTRO'])
        self.page.db.subst(question, 'CURDISTRO', operating_system)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        use_device = ubi_partman.PartitioningOption(title, desc)

        question = 'ubiquity/partitioner/ubuntu_upgrade'
        question_has_variables(question, ['CURDISTRO', 'VER'])
        self.page.db.subst(question, 'CURDISTRO', operating_system)
        self.page.db.subst(question, 'VER', self.release.version)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        reuse = ubi_partman.PartitioningOption(title, desc)

        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems(layout)
        options = self.page.calculate_autopartitioning_options(
            operating_systems, ubuntu_systems)
        self.assertIn('use_device', options)
        self.assertCountEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertCountEqual(self.manual, options['manual'])

        self.assertIn('reuse', options)
        self.assertCountEqual(reuse, options['reuse'])

    # 'This computer currently has Ubuntu 12.04 on it.'
    def test_same_ubuntu_only(self):
        operating_system = 'Ubuntu 12.04'
        operating_version = '12.04'

        def side_effect(*args, **kwargs):
            if 'with_version' in kwargs:
                return operating_system, operating_version
            return operating_system

        misc.find_in_os_prober.side_effect = side_effect
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        layout = {'=dev=sda': [part]}
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        self.page.extra_options['reuse'] = [(0, '/dev/sda1')]

        question = 'ubiquity/partitioner/ubuntu_format'
        question_has_variables(question, ['CURDISTRO'])
        self.page.db.subst(question, 'CURDISTRO', operating_system)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        use_device = ubi_partman.PartitioningOption(title, desc)

        question = 'ubiquity/partitioner/ubuntu_reinstall'
        question_has_variables(question, ['CURDISTRO'])
        self.page.db.subst(question, 'CURDISTRO', operating_system)
        title = self.page.description(question)
        desc = self.page.extended_description(question)

        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems(layout)
        options = self.page.calculate_autopartitioning_options(
            operating_systems, ubuntu_systems)
        self.assertIn('use_device', options)
        self.assertCountEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertCountEqual(self.manual, options['manual'])

        self.assertNotIn('reuse', options)

    # 'This computer currently has Ubuntu 90.10 on it.'
    def test_newer_ubuntu_only(self):
        operating_system = 'Ubuntu 90.10'
        operating_version = '90.10'

        def side_effect(*args, **kwargs):
            if 'with_version' in kwargs:
                return operating_system, operating_version
            return operating_system

        misc.find_in_os_prober.side_effect = side_effect
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        layout = {'=dev=sda': [part]}
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        self.page.extra_options['reuse'] = [(0, '/dev/sda1')]

        question = 'ubiquity/partitioner/ubuntu_format'
        question_has_variables(question, ['CURDISTRO'])
        self.page.db.subst(question, 'CURDISTRO', operating_system)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        use_device = ubi_partman.PartitioningOption(title, desc)

        question = 'ubiquity/partitioner/ubuntu_reinstall'
        question_has_variables(question, ['CURDISTRO'])
        self.page.db.subst(question, 'CURDISTRO', operating_system)
        title = self.page.description(question)
        desc = self.page.extended_description(question)

        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems(layout)
        options = self.page.calculate_autopartitioning_options(
            operating_systems, ubuntu_systems)
        self.assertIn('use_device', options)
        self.assertCountEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertCountEqual(self.manual, options['manual'])

        self.assertNotIn('reuse', options)

    # 'This computer currently has multiple operating systems on it.'
    def test_multiple_operating_systems(self):
        operating_systems = ['Ubuntu 10.04', 'Windows XP', 'Mac OSX']

        def side_effect(*args, **kwargs):
            return operating_systems.pop()

        misc.find_in_os_prober.side_effect = side_effect
        part1 = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        part2 = ubi_partman.Partition('/dev/sda2', 0, '1234-1234', 'ext4')
        part3 = ubi_partman.Partition('/dev/sda3', 0, '1234-1234', 'ext4')
        layout = {'=dev=sda': [part1, part2, part3]}
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        self.page.extra_options['resize'] = {
            '=dev=sda': ['', 0, 0, 0, '', 0, 'ntfs']}

        question = 'ubiquity/partitioner/multiple_os_format'
        question_has_variables(question, ['DISTRO'])
        self.page.db.subst(question, 'DISTRO', self.release.name)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        use_device = ubi_partman.PartitioningOption(title, desc)

        question = 'ubiquity/partitioner/multiple_os_resize'
        question_has_variables(question, ['DISTRO'])
        self.page.db.subst(question, 'DISTRO', self.release.name)
        title = self.page.description(question)
        desc = self.page.extended_description(question)
        resize = ubi_partman.PartitioningOption(title, desc)

        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems(layout)
        options = self.page.calculate_autopartitioning_options(
            operating_systems, ubuntu_systems)
        self.assertIn('use_device', options)
        self.assertCountEqual(use_device, options['use_device'])

        self.assertIn('resize', options)
        self.assertCountEqual(resize, options['resize'])

        self.assertIn('manual', options)
        self.assertCountEqual(self.manual, options['manual'])


def _fake_grub_options_pairs(paths, descriptions):
    # The interface expects a sequence-of-sequences, although the method
    # only cares about sub-sequences of length 1, where the path is
    # element zero.
    def grub_options():
        return [(path, description)
                for path, description
                in zip_longest(paths, descriptions, fillvalue='')]
    return grub_options


class TestPageGtk(unittest.TestCase):
    def setUp(self):
        # Without this, GtkBuilder cannot construct ResizeWidget and
        # PartitionBox widgets.
        from ubiquity import gtkwidgets

        gtkwidgets  # pacify pyflakes
        controller = mock.Mock()
        self.gtk = ubi_partman.PageGtk(controller)

    def test_advanced_page_link(self):
        from ubiquity import gtkwidgets

        self.gtk.part_auto_hidden_label.emit('activate-link', '')
        gtkwidgets.refresh()
        self.gtk.controller.go_forward.assert_called_once_with()

    @mock.patch('ubiquity.misc.grub_options',
                _fake_grub_options_pairs(
                    ('/dev/vda', '/dev/vdb',
                     '/dev/vda1', '/dev/vda2', '/dev/vdb1'),
                    ('Virtio Block Device (108 GB)',
                     'Virtio Block Device (801 GB)')))
    @unittest.skipUnless(os.environ['DEB_HOST_ARCH'] in ('amd64', 'i386'),
                         'GRUB-related tests are only relevant on x86')
    def test_boot_loader_installation_combobox(self):
        self.gtk.set_grub_options('/dev/vda', {
            '/dev/vda': True,
            '/dev/vda1': True,
            '/dev/vda2': False,
            '/dev/vdb': True,
            '/dev/vdb1': True,
        })
        # The combo box should have everything but vda2.
        expected = [
            '/dev/vda Virtio Block Device (108 GB)',
            '/dev/vdb Virtio Block Device (801 GB)',
            '/dev/vda1 ',
            '/dev/vdb1 ',
        ]
        row_text = []
        for row in self.gtk.grub_device_entry.get_model():
            row_text.append(' '.join(row))
        for want, got in zip(expected, row_text):
            self.assertEqual(want, got)


if __name__ == '__main__':
    run_unittest(
        TestCalculateAutopartitioningOptions,
        TestPage,
        TestPageGrub,
        TestPageGtk,
        PartmanPageDirectoryTests,
    )
