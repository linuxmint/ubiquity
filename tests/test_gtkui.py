#!/usr/bin/python3
# -*- coding: utf-8; -*-

from __future__ import print_function

import os
import unittest

import mock


class TestFrontend(unittest.TestCase):
    def setUp(self):
        for obj in ('ubiquity.misc.drop_privileges',
                    'ubiquity.misc.regain_privileges',
                    'ubiquity.misc.execute',
                    'ubiquity.misc.dmimodel',
                    'ubiquity.frontend.base.drop_privileges',
                    'ubiquity.frontend.gtk_ui.Wizard.customize_installer',
                    'ubiquity.nm.wireless_hardware_present',
                    'ubiquity.nm.NetworkManager.start',
                    'ubiquity.nm.NetworkManager.get_state',
                    'ubiquity.misc.has_connection',
                    'ubiquity.upower.setup_power_watch',
                    'dbus.mainloop.glib.DBusGMainLoop',
                    'ubiquity.i18n.reset_locale',
                    ):
            patcher = mock.patch(obj)
            patched_obj = patcher.start()
            self.addCleanup(patcher.stop)
            if obj in ('ubiquity.misc.wireless_hardware_present',
                       'ubiquity.misc.has_connection'):
                patched_obj.return_value = False
            elif obj == 'ubiquity.i18n.reset_locale':
                patched_obj.return_value = 'en_US.UTF-8'

    def test_question_dialog(self):
        from ubiquity.frontend import gtk_ui

        ui = gtk_ui.Wizard('test-ubiquity')
        with mock.patch('gi.repository.Gtk.Dialog.run') as run:
            run.return_value = 0
            ret = ui.question_dialog(title='♥', msg='♥',
                                     options=('♥', '£'))
            self.assertEqual(ret, '£')
            run.return_value = 1
            ret = ui.question_dialog(title='♥', msg='♥',
                                     options=('♥', '£'))
            self.assertEqual(ret, '♥')

    # TODO: I'm not entirely sure this makes sense, but the numbers are
    # currently rather unstable and seem to depend quite a lot on the theme.
    # This may have something to do with pixmaps not being set up properly
    # when testing against a build tree.
    @unittest.skipIf('UBIQUITY_TEST_INSTALLED' in os.environ,
                     'only testable against a build tree')
    def test_pages_fit_on_a_netbook(self):
        from ubiquity.frontend import gtk_ui

        ui = gtk_ui.Wizard('test-ubiquity')
        ui.translate_pages()
        for page in ui.pages:
            ui.set_page(page.module.NAME)
            ui.refresh()
            ui.refresh()
            if 'UBIQUITY_TEST_SHOW_ALL_PAGES' in os.environ:
                print(page.module.NAME)
                import time
                time.sleep(3)
            alloc = ui.live_installer.get_allocation()
            # width 640, because it is a common small 4:3 width
            # height 556, because e.g. HP Mini has 580 - 24px (indicators)
            # Anything smaller will need to use Alt+Ctrl+Pgd/Right
            # Scrollbars anyone?
            #self.assertLessEqual(alloc.width, 640, page.module.NAME)  # fixme
            self.assertLessEqual(alloc.height, 556, page.module.NAME)
            if page.module.NAME == 'partman':
                ui.allow_change_step(False)

    def test_interface_translated(self):
        import subprocess

        from gi.repository import Gtk

        from ubiquity.frontend import gtk_ui

        ui = gtk_ui.Wizard('test-ubiquity')
        missing_translations = []
        with mock.patch.object(ui, 'translate_widget') as translate_widget:
            def side_effect(widget, lang=None, prefix=None):
                label = isinstance(widget, Gtk.Label)
                button = isinstance(widget, Gtk.Button)
                # We have some checkbuttons without labels.
                button = button and widget.get_label()
                # Stock buttons.
                button = button and not widget.get_use_stock()
                window = isinstance(widget, Gtk.Window)
                if not (label or button or window):
                    return
                name = widget.get_name()
                if not ui.get_string(name, lang, prefix):
                    missing_translations.append(name)
            translate_widget.side_effect = side_effect
            ui.translate_widgets()
            whitelist = [
                # These are calculated and set as the partitioning options are
                # being calculated.
                'reuse_partition_desc', 'reuse_partition',
                'replace_partition_desc', 'replace_partition',
                'resize_use_free_desc', 'resize_use_free',
                'use_device_desc', 'use_device', 'part_ask_heading',
                'custom_partitioning_desc', 'custom_partitioning',
                # Pulled straight from debconf when the installation medium is
                # already mounted.
                'part_advanced_warning_message',
                # These are calculated and set inside info_loop in the user
                # setup page.
                'password_strength', 'hostname_error_label',
                'password_error_label', 'username_error_label',
                # Pulled straight from debconf into the UI on progress.
                'install_progress_text',
                # Contains just the traceback.
                'crash_detail_label',
                # Pages define a debconf template to look up and use as the
                # title. If it is not set or not found, the title is hidden.
                'page_title',
                # To be calculated and set
                'partition_lvm_status',
                # These are "placeholders" for debconfs impromptu notices
                'ubi_question_dialog', 'question_label',
                # Calculated error string
                'label_global_error',
            ]
            deb_host_arch = subprocess.Popen(
                ['dpkg-architecture', '-qDEB_HOST_ARCH'],
                stdout=subprocess.PIPE,
                universal_newlines=True).communicate()[0].strip()
            if deb_host_arch not in ('amd64', 'i386'):
                # grub-installer not available, but this template won't be
                # displayed anyway.
                whitelist.append('grub_device_label')
            missing_translations = set(missing_translations) - set(whitelist)
            missing_translations = list(missing_translations)
            if missing_translations:
                missing_translations = ', '.join(missing_translations)
                raise Exception('Missing translation for:\n%s'
                                % missing_translations)
