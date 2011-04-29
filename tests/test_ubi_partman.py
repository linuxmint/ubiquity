#!/usr/bin/python


import unittest
# These tests require Mock 0.7.0
import mock
from test import test_support
import sys
import os
sys.path.insert(0, 'ubiquity/plugins')
ubi_partman = __import__('ubi-partman')
sys.path.pop()
from ubiquity import misc
import debconf

def question_has_variables(question, lookup_variables):
    existing_variables = []
    found_question = False
    with open('tests/templates.dat') as templates:
        for line in templates:
            if found_question and line == '\n':
                break

            if line.startswith('Name: %s' % question):
                found_question = True
                continue
            elif not found_question:
                continue

            if line.startswith('Description:'):
                last = 13
            elif line.startswith('Extended_description:'):
                last = 22
            else:
                continue

            while True:
                start = line.find('${', last)
                if start != -1:
                    end = line.find('}', last)
                    if end != -1:
                        existing_variables.append(line[start+2:end])
                        last = end + 1
                    else:
                        exc = 'Expected to find } on \'%s\'' % line
                        raise EOFError, exc
                else:
                    break
    if not found_question:
        raise AssertionError, 'Never found the question: %s' % question
    only_in_lookup = set(lookup_variables) - set(existing_variables)
    only_in_template = set(existing_variables) - set(lookup_variables)
    if only_in_lookup or only_in_template:
        raise AssertionError, ('%s\nOnly in lookup: %s\nOnly in template: %s' %
            (question, ', '.join(only_in_lookup), ', '.join(only_in_template)))


# These tests skip when their dependencies are not met and tests/run takes
# arguments to generate said dependencies, so neither need to know about the
# inner workings of each other.

@unittest.skipUnless(os.path.exists('tests/partman-tree'), 'Need /lib/partman.')
class PartmanPageDirectoryTests(unittest.TestCase):
    def setUp(self):
        # We could mock out the db for this, but we ultimately want to make
        # sure that the debconf questions its getting exist.
        self.page = ubi_partman.Page(None)
        self.page.db = debconf.DebconfCommunicator('ubi-test', cloexec=True)
        self.addCleanup(self.page.db.shutdown)

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

        # Don't cache descriptions.
        self.page.description_cache = {}

    #def test_filesystem_description(self):
    #    for fs in self.page.scripts('/lib/partman/valid_filesystems'):
    #        print self.page.filesystem_description(fs)

    #def test_method_description(self):
    #    for method in self.page.subdirectories('/lib/partman/choose_method'):
    #        if method != 'dont_use':
    #            self.assertNotEqual(method,
    #                                self.page.method_description(method))

@unittest.skipUnless('DEBCONF_SYSTEMRC' in os.environ, 'Need a database.')
class TestPage(unittest.TestCase):
    def setUp(self):
        # We could mock out the db for this, but we ultimately want to make
        # sure that the debconf questions its getting exist.
        self.page = ubi_partman.Page(None)
        self.page.db = debconf.DebconfCommunicator('ubi-test', cloexec=True)
        self.addCleanup(self.page.db.shutdown)

        # Don't cache descriptions.
        self.page.description_cache = {}

    def test_description(self):
        question = 'partman-auto/init_automatically_partition'
        description = unicode(self.page.db.metaget(question, 'description'),
                              'utf-8', 'replace')
        self.assertEqual(self.page.description(question), description)
        self.assertIn(question, self.page.description_cache)

    def test_default_mountpoint_choices(self):
        pairs = [('partman-basicfilesystems/fat_mountpoint', 'ntfs'),
                 ('partman-basicfilesystems/mountpoint', 'ext4')]
        try:
            # We cannot test uboot if we're not running on armel.
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
            self.assertItemsEqual(mountpoints, default_mountpoints)

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
        
        # Pretend to be online.
        self.page.db.set('ubiquity/online', 'true')

    # 'This computer currently has Windows on it.'
    def test_windows_only(self):
        operating_system = u'Windows XP'
        misc.find_in_os_prober.return_value = operating_system
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ntfs')
        layout = { '=dev=sda' : [part] }
        self.page.extra_options = {}
        self.page.extra_options['resize'] = {
            '=dev=sda' : [ '', 0, 0, 0, '', 0, 'ntfs']}

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
        self.assertItemsEqual(resize, options['resize'])
        self.assertIn('use_device', options)
        self.assertItemsEqual(replace, options['use_device'])
        self.assertIn('manual', options)
        self.assertItemsEqual(self.manual, options['manual'])

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
        self.assertItemsEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertItemsEqual(self.manual, options['manual'])

    # 'This computer currently has Ubuntu 10.04 on it.'
    def test_older_ubuntu_only(self):
        operating_system = u'Ubuntu 10.04'
        misc.find_in_os_prober.return_value = operating_system
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        layout = { '=dev=sda' : [part] }
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
        self.assertItemsEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertItemsEqual(self.manual, options['manual'])

        self.assertIn('reuse', options)
        self.assertItemsEqual(reuse, options['reuse'])

    # 'This computer currently has Ubuntu 11.04 on it.'
    @unittest.skipIf(True, 'functionality currently broken.')
    def test_same_ubuntu_only(self):
        operating_system = u'Ubuntu 11.04'
        misc.find_in_os_prober.return_value = operating_system
        part = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        layout = { '=dev=sda' : [part] }
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
        reuse = ubi_partman.PartitioningOption(title, desc)

        operating_systems, ubuntu_systems = \
            self.page.calculate_operating_systems(layout)
        options = self.page.calculate_autopartitioning_options(
                        operating_systems, ubuntu_systems)
        self.assertIn('use_device', options)
        self.assertItemsEqual(use_device, options['use_device'])

        self.assertIn('manual', options)
        self.assertItemsEqual(self.manual, options['manual'])

        self.assertIn('reuse', options)
        self.assertItemsEqual(reuse, options['reuse'])

    # 'This computer currently has multiple operating systems on it.'
    def test_multiple_operating_systems(self):
        operating_systems = [u'Ubuntu 10.04', u'Windows XP', u'Mac OSX']
        def side_effect(*args, **kwargs):
            return operating_systems.pop()
        misc.find_in_os_prober.side_effect = side_effect
        part1 = ubi_partman.Partition('/dev/sda1', 0, '1234-1234', 'ext4')
        part2 = ubi_partman.Partition('/dev/sda2', 0, '1234-1234', 'ext4')
        part3 = ubi_partman.Partition('/dev/sda3', 0, '1234-1234', 'ext4')
        layout = { '=dev=sda' : [part1, part2, part3] }
        self.page.extra_options = {}
        self.page.extra_options['use_device'] = ('debconf-return-value',
                                                 [{'disk-desc': 0}])
        self.page.extra_options['resize'] = {
            '=dev=sda' : [ '', 0, 0, 0, '', 0, 'ntfs']}

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
        self.assertItemsEqual(use_device, options['use_device'])

        self.assertIn('resize', options)
        self.assertItemsEqual(resize, options['resize'])

        self.assertIn('manual', options)
        self.assertItemsEqual(self.manual, options['manual'])

if __name__ == '__main__':
    test_support.run_unittest(TestCalculateAutopartitioningOptions, TestPage, PartmanPageDirectoryTests)
