# Testing Ubiquity Installer
# Author: Dan Chapman <daniel@chapman-mail.com>
# Copyright (C) 2013
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import os
import logging
import random
import time
import configparser
import unittest

from testtools.matchers import Equals, NotEquals

from autopilot.introspection.dbus import StateNotFoundError
from autopilot.matchers import Eventually
from autopilot.introspection import get_proxy_object_for_existing_process
from autopilot.input import (
    Mouse,
    Keyboard,
    Pointer
)
from ubiquity_autopilot_tests.emulators import gtktoplevel
from ubiquity_autopilot_tests.emulators.gtktoplevel import GtkWindow
from ubiquity_autopilot_tests.emulators import AutopilotGtkEmulatorBase
from ubiquity_autopilot_tests.testcase import UbiquityTestCase
from ubiquity_autopilot_tests.configs import english_label_conf
from ubiquity_autopilot_tests.configs.partconfig import (
    Config1,
    Config2,
    Config3,
    Config4,
    Config5,
    Config6
)
from ubiquity_autopilot_tests.matchers.range import InRange

custom_configs = [Config1, Config2, Config3, Config4, Config5, Config6]
logger = logging.getLogger(__name__)


class UbiquityAutopilotTestCase(UbiquityTestCase):

    def setUp(self):
        super(UbiquityAutopilotTestCase, self).setUp()
        self.app = self.launch_application()

        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()
        self.current_page_title = ''
        self.previous_page_title = ''
        self.current_step = ''
        self.step_before = ''
        self.english_install = False
        english_label_conf.generate_config()
        self.english_config = configparser.ConfigParser()
        self.english_config.read('/tmp/english_config.ini')
        #delete config at end of test
        self.addCleanup(os.remove, '/tmp/english_config.ini')
        # always starts with 1 row ('/dev/sda')
        self.part_table_rows = 1
        self.total_number_partitions = 0

    def tearDown(self):
        self._check_no_visible_dialogs()
        super(UbiquityAutopilotTestCase, self).tearDown()
        unittest.TestCase.tearDown(self)

    def launch_application(self):
        '''
        Hmm... launch ubiquity


        :returns: The application proxy object.
        '''
        my_process = int(os.environ['UBIQUITY_PID'])
        my_dbus = str(os.environ['DBUS_SESSION_BUS_ADDRESS'])
        return get_proxy_object_for_existing_process(
            pid=my_process, dbus_bus=my_dbus,
            emulator_base=AutopilotGtkEmulatorBase)

    @property
    def main_window(self, ):
        return self.app.select_single('GtkWindow', name='live_installer')

    def go_to_next_page(self, wait=False):
        """ Goes to the next page of Ubiquity installer

        Will timeout after 2 mins waiting for next page to appear.

        Params:
            wait: If set to true will wait for the buttons sensitive property
                  to be true. Will timeout after 20mins.
                NOTE: this should only be used when clicking 'Install Now'
                the default 2 mins is sufficient for every other page switch

        """
        logger.debug('go_to_next_page(wait={0})'.format(wait))
        nxt_button = self.main_window.select_single('GtkButton', name='next')
        nxt_button.click()

        if wait:
            # This sleep just bridges a weird error when the next button,
            # sometimes flickers its sensitive property back to 1 once clicked
            # and then goes back to 0
            time.sleep(2)
            # now take back over from the sleep and wait for sensitive to
            # become 1
            logger.debug("Waiting for 'next' Button to become sensitive "
                         "again.....")
            self.assertThat(nxt_button.sensitive,
                            Eventually(Equals(True), timeout=1200))

        page_title = self.main_window.select_single(
            'GtkLabel', name='page_title')
        self.assertThat(page_title.label,
                        Eventually(NotEquals(self.current_page_title),
                                   timeout=120))

    def go_to_progress_page(self, ):
        """ This simply clicks next and goes to the progress page

        NOTE:
            This shouldn't be used for any other page switches as it does no
            checks.

        """
        nxt_button = self.main_window.select_single('GtkButton', name='next')
        nxt_button.click()

    def welcome_page_tests(self, lang=None):
        """ Runs the tests for the Welcome Page
        :param lang: The treeview label value (e.g 'English') of the required
                     language.
                     If None will pick a random language from the tree.
                     ..NOTE: You should only specify a language if the test
                         relies upon a specific language. It is better to write
                         the tests to work for any language.

        """

        self._update_current_step('stepLanguage')
        self._check_navigation_buttons()
        #first check pageTitle visible and correct if label given
        logger.debug("run_welcome_page_tests()")
        #selecting an install language
        logger.debug("Selecting stepLanguage page object")
        welcome_page = self.main_window.select_single(
            'GtkBox', name='stepLanguage')
        treeview = welcome_page.select_single('GtkTreeView')
        #lets get all items
        treeview_items = treeview.get_all_items()
        #first lets check all the items are non-empty unicode strings
        logger.debug("Checking all tree items are valid unicode")
        for item in treeview_items:
            logger.debug("Check tree item with name '%s' is unicode" %
                         item.accessible_name)
            self.expectIsInstance(item.accessible_name, str,
                                  "[Page:'stepLanguage'] Expected '%s' tree "
                                  "view item to be unicode but it wasn't" %
                                  item.accessible_name)
            self.expectThat(item.accessible_name, NotEquals(u''),
                            "[Page:'stepLanguage'] Tree item found that "
                            "doesn't contain any text")

        if lang:
            if lang == 'English':
                self.english_install = True
            item = treeview.select_item(lang)
            language = item
        else:
            language = welcome_page.get_random_language()
            if language == 'English':
                self.english_install = True
        welcome_page.select_language(language)

        self.assertThat(language.selected, Equals(True))
        ##Test release notes label is visible
        logger.debug("Checking the release_notes_label")
        self.check_visible_object_with_label('release_notes_label')
        release_notes_label = welcome_page.select_single(
            BuilderName='release_notes_label')
        self.pointing_device.move_to_object(release_notes_label)
        self._update_page_titles()
        self._check_page_titles()
        self._check_navigation_buttons()

    def preparing_page_tests(self, updates=False, thirdParty=False,
                             networkConnection=True, sufficientSpace=True,
                             powerSource=False):
        """ Runs the tests for the 'Preparing to install' page

        :param updates: Boolean, if True selects install updates during install

        :param thirdParty: Boolean, if True selects install third-party
                                    software

        :param networkConnection: Boolean if True checks the network state box
                                    is visible and objects are correct, If
                                    false will still check the objects are
                                    correct but the state box is not visible

        :param sufficientSpace: Boolean if True checks the network state box is
                                    visible and objects are correct, If false
                                    will still check the objects are correct
                                    but the state box is not visible

        :param powerSource: Boolean if True checks the network state box is
                                    visible and objects are correct, If false
                                    will still check the objects are correct
                                    but the state box is not visible

        """
        self._update_current_step('stepPrepare')
        self._check_navigation_buttons()
        self._update_page_titles()

        logger.debug("run_preparing_page_tests()")
        logger.debug("selecting stepPrepare page")
        preparing_page = self.main_window.select_single(
            'GtkAlignment', BuilderName='stepPrepare')

        objList = ['prepare_best_results', 'prepare_foss_disclaimer',
                   'prepare_download_updates', 'prepare_nonfree_software']
        self.check_visible_object_with_label(objList)

        if updates:
            logger.debug("Selecting install updates")
            update_checkbutton = preparing_page.select_single(
                'GtkCheckButton', BuilderName='prepare_download_updates')
            self.pointing_device.click_object(update_checkbutton)

        if thirdParty:
            logger.debug("Selecting install thirdparty software")
            thrdprty_checkbutton = preparing_page.select_single(
                'GtkCheckButton', BuilderName='prepare_nonfree_software')
            self.pointing_device.click_object(thrdprty_checkbutton)

        self._check_preparing_statebox('prepare_network_connection',
                                       visible=networkConnection)
        #and sufficient space
        self._check_preparing_statebox('prepare_sufficient_space',
                                       visible=sufficientSpace)
        # and power source
        self._check_preparing_statebox('prepare_power_source',
                                       visible=powerSource)

        self._check_page_titles()
        self._check_navigation_buttons()

    def edubuntu_addon_window_tests(self, unity=False,
                                    gnome=False, ltsp=False):
        """Run Page tests for edubuntu addon page"""
        self._update_current_step('edubuntu-addon_window')
        self._check_navigation_buttons()
        self._update_page_titles()
        add_on_page = self.main_window.select_single(
            'GtkVBox', BuilderName='edubuntu-addon_window')
        page_objects = ['fallback_install', 'description', 'fallback_title',
                        'fallback_description', 'ltsp_install', 'ltsp_title',
                        'ltsp_description', 'ltsp_interface_label']
        self.check_visible_object_with_label(page_objects)

        env = None
        if unity:
            logger.debug('Using default Unity env...')
            pass
        elif gnome:
            logger.debug("Using gnome fallback env")
            env = 'fallback_install'
        elif ltsp:
            logger.debug('Using LTSP env')
            env = 'ltsp_install'
        else:
            items = [None, 'fallback_install', 'ltsp_install']
            env = random.choice(items)

        if env:
            choice = add_on_page.select_single(BuilderName=env)
            self.pointing_device.click_object(choice)

        self._check_page_titles()
        self._check_navigation_buttons()

    def edubuntu_packages_window_tests(self, ):
        """Run Page tests for edubuntu packages page"""
        self._update_current_step('edubuntu-packages_window')
        self._check_navigation_buttons()
        self._update_page_titles()
        self.check_visible_object_with_label('description')
        self._check_page_titles()
        self._check_navigation_buttons()

    def installation_type_page_tests(self, default=False, lvm=False,
                                     lvmEncrypt=False, custom=False):
        """Runs the tests for the installation type page

        :param default: Boolean if True will use the default selected option
            for the installation

        :param lvm: Boolean if True will use the LVM option for the
            installation

        :param lvmEncrypt: Boolean if True will use the LVM with encryption
            option for the installation

        :param custom: Boolean if True will use the 'Something else' option for
            the installation

        """
        self._update_current_step('stepPartAsk')
        self._check_navigation_buttons()
        self._update_page_titles()

        option_name = None
        if default:
            from ubiquity_autopilot_tests.configs import default_install

            config = default_install
        if lvm:
            from ubiquity_autopilot_tests.configs import lvm_install

            config = lvm_install
            option_name = 'use_lvm'
        if lvmEncrypt:
            from ubiquity_autopilot_tests.configs import encrypt_lvm_install

            config = encrypt_lvm_install
            option_name = 'use_crypto'
        if custom:
            from ubiquity_autopilot_tests.configs import custom_install

            config = custom_install
            option_name = 'custom_partitioning'

        self.check_visible_object_with_label(config.visible_options)
        self.check_hidden_object_with_label(config.hidden_options)
        install_type_page = self.main_window.select_single(
            'GtkAlignment', BuilderName='stepPartAsk')
        if option_name:
            obj = install_type_page.select_single(BuilderName=option_name)
            self.pointing_device.click_object(obj)

        self._check_page_titles()
        self._check_navigation_buttons()

    def lvm_crypto_page_tests(self, crypto_password):
        """ Runs the tests for the LVM encryption password page

        :param crypto_password: *String*, password to be used for the
                                encryption

        """
        self._update_current_step('stepPartCrypto')
        self._check_navigation_buttons()
        self._update_page_titles()

        logger.debug("run_step_part_crypto_page_tests({0})"
                     .format(crypto_password))
        logger.debug('Selecting stepPartCrypto page object')
        crypto_page = self.main_window.select_single(
            'GtkAlignment', BuilderName='stepPartCrypto')

        items = ['verified_crypto_label', 'crypto_label', 'crypto_description',
                 'crypto_warning', 'crypto_extra_label', 'crypto_extra_time',
                 'crypto_description_2', 'crypto_overwrite_space']
        self.check_visible_object_with_label(items)

        crypto_page.enter_crypto_phrase(crypto_password)
        self._check_page_titles()
        self._check_navigation_buttons()

    def custom_partition_page_tests(self, part_config=None):
        """ Runs the tests for the custom partition page

        The custom partition configurations are in partconfig.py. This function
        selects a random Config for each test run from partconfig.py.

        When adding a new config, import it and add it to the custom_configs
        list

        :param part_config:
        """
        part_config = Config1
        self._update_current_step('stepPartAdvanced')
        self._check_navigation_buttons()
        self._update_page_titles()
        logger.debug("run_custom_partition_page_tests()")
        logger.debug("Selecting the stepPartAdvanced page object")
        custom_page = self.main_window.select_single(
            'GtkAlignment', BuilderName='stepPartAdvanced')
        treeview = custom_page.select_single('GtkTreeView')
        self.expectThat(treeview.visible, Equals(True),
                        "[Page:'{0}'] Partition tree view was not visible")
        obj_list = ['partition_button_new', 'partition_button_delete',
                    'partition_button_edit', 'partition_button_edit',
                    'partition_button_new_label']
        for name in obj_list:
            obj = custom_page.select_single(BuilderName=name)
            self.expectThat(obj.visible, Equals(True),
                            "[Page:'{0}'] {1} object was not visible"
                            .format(self.current_step, obj.name))
        logger.debug("Sleeping while we wait for all UI elements to fully "
                     "load")
        time.sleep(5)  # need to give time for all UI elements to load
        custom_page.create_new_partition_table()
        #update number of table rows
        self.part_table_rows = treeview.get_number_of_rows()
        logger.debug("TOTAL NUMBER OF ROWS: {0}".format(self.part_table_rows))
        #lets create the partitions from here
        if part_config:
            logger.debug("Setting the given partition config")
            config = part_config
        else:
            logger.debug("Selecting a random partition config")
            config = random.choice(custom_configs)
            logger.debug("LENGTH OF CONFIG IS: {0}".format(len(config)))

        logger.debug(
            "TOTAL NUMBER OF PARTITIONS IN CONFIG: {0}".format(len(config))
        )
        self.total_number_partitions = len(config)
        logger.debug(
            "TOTAL NUMBER OF PARTITIONS TO BE IN TABLE: {0}".format(
                self.total_number_partitions)
        )
        for elem in config:
            self._add_new_partition()

            partition_dialog = self.main_window.get_dialog(
                'GtkDialog', BuilderName='partition_dialog')
            self.assertThat(partition_dialog.visible, Eventually(Equals(True)),
                            "Partition dialog not visible")
            partition_dialog.set_partition_size(elem['PartitionSize'])
            partition_dialog.set_partition_location(elem['Position'])
            partition_dialog.set_partition_type(elem['PartitionType'])
            partition_dialog.set_file_system_type(elem['FileSystemType'])
            partition_dialog.set_mount_point(elem['MountPoint'])
            ok_button = partition_dialog.select_single(
                'GtkButton', BuilderName='partition_dialog_okbutton')
            self.pointing_device.click_object(ok_button)
            self.assertThat(partition_dialog.visible,
                            Eventually(Equals(False)),
                            "Partition dialog did not close")
            self._check_partition_created(elem)
        # TODO: Uncomment once bug 1066152 is fixed
        #self._check_page_titles()
        self._check_navigation_buttons()

    def location_page_tests(self, ):
        """ Runs the test for the Location page

        Due to not being able to introspect the timezone map we only have a
        choice of 4 locations which get selected at random.

        """
        logger.debug('run_location_page_tests()')
        self._update_current_step('stepLocation')
        self._check_navigation_buttons(continue_button=True, back_button=True,
                                       quit_button=False, skip_button=False)
        self._update_page_titles()

        logger.debug("Selecting stepLocation page object")
        location_page = self.main_window.select_single(
            'GtkBox', BuilderName='stepLocation')
        location_map = location_page.select_single('CcTimezoneMap')
        self.assertThat(location_map.visible, Equals(True),
                        "Expected location map to be visible but it wasn't")
        location_entry = location_page.select_single(
            BuilderName='timezone_city_entry')
        self.assertThat(location_entry.visible, Equals(True),
                        "Expected location entry to be visible but it wasn't")

        location = ['London', 'Paris', 'Madrid', 'Algiers']
        if self.english_install:
            location_page.select_location('London')
        else:
            location_page.select_location(random.choice(location))
        self._check_page_titles()
        self._check_navigation_buttons(continue_button=True, back_button=True,
                                       quit_button=False, skip_button=False)

    def keyboard_layout_page_tests(self, ):
        self._update_current_step('stepKeyboardConf')
        self._check_navigation_buttons(continue_button=True, back_button=True,
                                       quit_button=False, skip_button=False)
        self._update_page_titles()
        logger.debug("run_keyboard_layout_page_tests()")

        logger.debug("Selecting the stepKeyboardCOnf page object")
        keyboard_page = self.main_window.select_single(
            'GtkAlignment',
            BuilderName='stepKeyboardConf')
        treeviews = keyboard_page.select_many('GtkTreeView')
        # lets check all the keyboard tree items for the selected language
        # TODO: we should probably test at some point try changing the keyboard
        #       layout to a different language/locale/layout and see if
        #       ubiquity breaks
        for treeview in treeviews:
            items = treeview.get_all_items()
            for item in items:
                self.expectIsInstance(item.accessible_name, str,
                                      "[Page:'%r'] Expected %r item to be "
                                      "unicode but it wasn't" % (
                                          self.current_step,
                                          item.accessible_name))
                self.expectThat(item.accessible_name, NotEquals(u''),
                                "[Page:'{0}'] Tree view item found which "
                                "didn't contain text, but it should!!")

        # now lets test typing with the keyboard layout
        entry = keyboard_page.select_single('GtkEntry')
        while True:
            text = u'Testing keyboard layout'
            with self.keyboard.focused_type(entry) as kb:
                kb.type(text)
                #check entry value is same length as text
                if len(entry.text) == len(text):
                    # only test the entry value if we are using english install
                    if self.english_install:
                        self.expectThat(entry.text, Equals(text))
                    self.expectThat(
                        entry.text, NotEquals(u''),
                        "[Page:'{0}'] Expected Entry to contain text "
                        "after typing but it didn't"
                        .format(self.current_step))
                    self.expectIsInstance(
                        entry.text, str,
                        "[Page:'{0}'] Expected Entry text to be "
                        "unicode but it wasnt"
                        .format(self.current_step))
                    break
                #delete the entered text before trying again
                kb.press_and_release('Ctrl+a')
                kb.press_and_release('Delete')
        # TODO: Test detecting keyboard layout
        self._check_page_titles()
        self._check_navigation_buttons(continue_button=True, back_button=True,
                                       quit_button=False, skip_button=False)

    def user_info_page_tests(self, username, pwd,
                             encrypted=False, autologin=False):
        """ Runs tests for the User Info Page

        :param username:*String*, name of user

        :param pwd: *String*, password for user

        :param encrypted: *Bool* if true encypts the home directory

        :param autologin: *Bool* if true sets the user account to login
                           automagically

        """
        self._update_current_step('stepUserInfo')
        self._check_navigation_buttons(continue_button=True, back_button=True,
                                       quit_button=False, skip_button=False)
        self._update_page_titles()
        logger.debug("Selecting stepUserInfo page")
        user_info_page = self.main_window.select_single(
            'GtkBox',
            BuilderName='stepUserInfo')

        objects = ['hostname_label', 'username_label', 'password_label',
                   'verified_password_label', 'hostname_extra_label'
                   ]
        logger.debug("checking user info page objects ......")
        self.check_visible_object_with_label(objects)

        user_info_page.create_user(username, pwd)
        #TODO: get these working
        if encrypted:
            user_info_page.encrypt_home_dir(encrypt=True)
        if autologin:
            user_info_page.set_auto_login()

        self._check_page_titles()
        self._check_navigation_buttons(continue_button=True, back_button=True,
                                       quit_button=False, skip_button=False)

    def progress_page_tests(self, ):
        ''' Runs the test for the installation progress page

            This method tracks the current progress of the install
            by using the fraction property of the progress bar
            to assertain the percentage complete.

        '''
        #TODO: Remove all these prints once dbus bug is fixed
        logger.debug("run_install_progress_page_tests()")
        print("run_install_progress_page_tests()")
        #We cant assert page title here as its an external html page
        #Maybe try assert WebKitWebView is visible
        #
        # NOTE: disable test to check if webkit view is visible. autopilot
        #       randomly crashes with LP#1284671 and very often in the QA Lab
        #print("Selecting WebKit")
        #webkitwindow = self.main_window.select_single(
        #    'GtkScrolledWindow', name='webkit_scrolled_window'
        #)
        #print("Test webkitwindow visible")
        #self.expectThat(webkitwindow.visible, Equals(True))
        #print("Webkit window found and is visible")
        print("Selecting Progress bar")
        progress_bar = self.main_window.select_single('GtkProgressBar',
                                                      name='install_progress')

        #Copying files progress bar
        print("Entering first tracking loop all that will be called "
              "from here is GtkWindow name = liveinstaller and the "
              "progressbar")
        self._track_install_progress()
        print("First loop complete waiting for pbar to go back to 0")
        self.assertThat(progress_bar.fraction, Eventually(
            Equals(0.0), timeout=180))
        print("Now entering the second loop...........")
        #And now the install progress bar
        self._track_install_progress()

    def check_visible_object_with_label(self, visible_obj):
        """Check an visible objects label and visible properties,

        :param visible_obj: Accepts either a objects name property or
                            a list of names
        ..note:: If english installation this function will also test the
                 english label value which is retrieved from the
                 generated english_config.ini file
        """
        if isinstance(visible_obj, list):
            for item in visible_obj:
                self._check_object(item)
            return
        if isinstance(visible_obj, str):
            self._check_object(visible_obj)
            return
        raise ValueError(
            "Object name must either be a string or list of strings")

    def check_hidden_object_with_label(self, hidden_obj):
        """Check an hidden objects label and visible properties,

        :param hidden_obj: Accepts either a objects name property or
                            a list of names
        """
        if isinstance(hidden_obj, list):
            for item in hidden_obj:
                self._check_object(item, False)
            return
        if isinstance(hidden_obj, str):
            self._check_object(hidden_obj, False)
            return
        raise ValueError(
            "Object name must either be a string or list of strings")

    def _check_object(self, obj_name, obj_visible=True):
        logger.debug("Checking {0} object.......".format(obj_name))
        #select current page object
        page = self.main_window.select_single(BuilderName=self.current_step)
        #select object
        page_object = page.select_single(BuilderName=obj_name)
        if obj_visible:
            visible_message = "[Page:'{0}'] Expected {1} object to be " \
                              "visible but it wasn't".format(self.current_step,
                                                             page_object.name)
        else:
            visible_message = "[Page:'{0}'] Expected {1} object to not be " \
                              "visible but it was!".format(self.current_step,
                                                           page_object.name)
        self.expectThat(page_object.visible, Equals(obj_visible),
                        visible_message)
        self.expectThat(page_object.label, NotEquals(u''),
                        "[Page:'{0}'] Expected {1} objects label value to "
                        "contain text but it didn't"
                        .format(self.current_step, page_object.name))
        self.expectIsInstance(page_object.label, str,
                              "[Page:'{0}'] Expected {1} objects label "
                              "value to be unicode but it wasn't"
                              .format(self.current_step, page_object.name))
        #we only want to test visible english values, hidden ones don't matter
        if (self.current_step in self.english_config) and obj_visible:
            if self.english_install and (
                    obj_name in self.english_config[self.current_step]):
                logger.debug(
                    "Checking {0} object's english label value....".format(
                        obj_name))
                #if english install check english values
                self.expectThat(page_object.label, Equals(
                    self.english_config[self.current_step][obj_name]))

    def _track_install_progress(self, ):
        '''Gets the value of the fraction property of the progress bar

            so we can see when the progress bar is complete

        '''
        logger.debug("_track_install_progress_bar()")
        print("_track_install_progress()")
        print("selecting progress bar")
        progress_bar = self.main_window.select_single('GtkProgressBar',
                                                      name='install_progress')
        progress = 0.0
        while progress < 1.0:
            #print("Progressbar = %d" % progress)
            #keep updating fraction value
            #print("Getting an updated pbar.fraction")
            progress = progress_bar.fraction
            #print("Got an updated pbar fraction")
            # lets sleep for longer at early stages then
            # reduce nearer to complete
            if progress < 0.5:
                time.sleep(5)
            elif progress < 0.7:
                time.sleep(3)
            elif progress < 0.85:
                time.sleep(1)
            else:
                pass

            #logger.debug('Percentage complete "{0:.0f}%"'
            #             .format(progress * 100))

    def _check_no_visible_dialogs(self, arg=None):
        # lets try grab some dialogs we know of
        dialogs = ['warning_dialog', 'crash_dialog',
                   'bootloader_fail_dialog', 'ubi_question_dialog']
        safe_dialogs = ['finished_dialog', 'partition_dialog']
        for dialog_name in dialogs:
            dialog = self.app.select_single(BuilderName=dialog_name)
            if dialog.visible:
                msg = self._get_dialog_message(dialog)
                # each dialog will display a label explaining the error
                self.expectNotVisible(dialog.visible,
                                      "{0} was found to be visible. "
                                      "With error message: \n"
                                      "{1}"
                                      .format(dialog.name, msg))
        # Try grab dialogs created at runtime
        unknown_dialogs = self.app.select_many('GtkDialog')
        for dlg in unknown_dialogs:
            if dlg.name in dialogs or safe_dialogs:
                pass
            else:
                if dlg.visible:
                    msg = self._get_dialog_message(dlg)
                    # each dialog will display a label explaining the error
                    self.expectNotVisible(dlg.visible,
                                          "Error dialog found to be visible "
                                          "With error message: \n"
                                          "{0}"
                                          .format(msg))
        # Lets try and grab any spawned GtkMessageDialogs
        try:
            unknown_msg_dialogs = self.app.select_many('GtkMessageDialog')
            for dlg in unknown_msg_dialogs:
                msg = self._get_dialog_message(dlg)
                # each dialog will display a label explaining the error
                self.expectNotVisible(dlg.visible,
                                      "A GtkMessageDialog was found to be "
                                      "visible. With error message: \n"
                                      "{0}"
                                      .format(msg))
        except StateNotFoundError:
            # catch statenotfound so we can continue
            pass

    def _get_dialog_message(self, dlg_object):
        dialog_labels = dlg_object.select_many('GtkLabel')
        message = ''
        for gtklabel in dialog_labels:
            #only add labels longer than 'Continue' so we avoid button labels
            if len(gtklabel.label) > 8:
                message += (gtklabel.label + '. ')

        return message

    def _add_new_partition(self, ):
        """ adds a new partition """
        logger.debug("_add_new_partition()")
        custom_page = self.main_window.select_single(
            'GtkAlignment',
            BuilderName='stepPartAdvanced')
        tree_view = custom_page.select_single('GtkTreeView')
        item = tree_view.select_item(u'  free space')
        self.pointing_device.click_object(item)
        self.assertThat(item.selected, Equals(True),
                        "[Page:'{0}'] Free Space tree item not selected"
                        .format(self.current_step))
        add_button = custom_page.select_single(
            'GtkToolButton',
            BuilderName='partition_button_new')
        self.pointing_device.click_object(add_button)
        time.sleep(2)
        logger.debug('_add_new_partition complete')

    def _check_partition_created(self, config):
        """ Checks that the partition was created properly
        """
        logger.debug("Checking partition was created.....")
        custom_page = self.main_window.select_single(
            'GtkAlignment',
            BuilderName='stepPartAdvanced')
        tree_view = custom_page.select_single('GtkTreeView')
        #assert a new row has been added to the partition table
        total_rows = self._update_table_row_count(config)
        logger.debug("TOTAL NUMBER OF ROWS: {0}".format(self.part_table_rows))
        self.assertThat(total_rows, Equals(self.part_table_rows))
        items = tree_view.get_all_items()

        fsFormat = config['FileSystemType']
        mount_point = config['MountPoint']
        size_obj = config['PartitionSize']
        if mount_point:
            index = next((index for index, value in enumerate(items)
                          if mount_point == value.accessible_name), None)
            self.assertIsNotNone(index,
                                 "Could not get index for '{0}' tree item"
                                 .format(mount_point))
            logger.debug("Found index for {0} tree item".format(mount_point))
            fs_item = tree_view.select_item_by_index(index - 1)
            mount_item = tree_view.select_item_by_index(index)
            size_item = tree_view.select_item_by_index(index + 1)
        else:
            index = next((index for index, value in enumerate(items)
                          if fsFormat.lower() == value.accessible_name), None)
            self.assertIsNotNone(index,
                                 "Could not get index for {0} FS tree item"
                                 .format(fsFormat))
            logger.debug("Found index for {0} tree item".format(fsFormat))
            fs_item = tree_view.select_item_by_index(index)
            mount_item = tree_view.select_item_by_index(index + 1)
            size_item = tree_view.select_item_by_index(index + 2)

        self.expectThat(fsFormat.lower(), Equals(fs_item.accessible_name))
        self.expectThat(fs_item.visible, Equals(True),
                        "[Page: '{0}'] Expected {0} to be visible but "
                        "it wasn't".format(fs_item.accessible_name))

        if mount_point:
            # Fail the test if we don't have correct mount point
            self.assertThat(mount_point,
                            Equals(mount_item.accessible_name))
            self.expectThat(mount_item.visible, Equals(True),
                            "[Page: '{0}'] Expected {0} to be visible but "
                            "it wasn't".format(mount_item.accessible_name))

        if size_obj:
            self.expectThat(
                int(size_item.accessible_name.strip(' MB')),
                InRange((size_obj - 3), (size_obj + 3)),
                "[Page:'{0}'] Expected partition size to be "
                "somwhere in the range of {1}-{2}MB but instead was {3}. "
                "This means the created partition was significantly "
                "different in size to the requested amount of {4}MB"
                .format(self.current_step, str(size_obj - 3),
                        str(size_obj + 3), size_item.accessible_name,
                        str(size_obj)))
            self.expectThat(size_item.visible, Equals(True),
                            "[Page: '{0}'] Expected {0} to be visible but "
                            " it wasn't".format(size_item.accessible_name))
            logger.debug("Partition created")

    def _check_navigation_buttons(self, continue_button=True, back_button=True,
                                  quit_button=True, skip_button=False):
        """ Function that checks the navigation buttons through out the install

        :param continue_button: Boolean value of buttons expected visibility
        :param back_button: Boolean value of buttons expected visibility
        :param quit_button: Boolean value of buttons expected visibility
        :param skip_button: Boolean value of buttons expected visibility

        """
        logger.debug("check_window_constants({0}, {1}, {2}, {3})".format(
            continue_button, back_button, quit_button, skip_button))

        con_button = self.main_window.select_single('GtkButton', name='next')
        self.assertThat(con_button.visible, Equals(continue_button))

        bk_button = self.main_window.select_single('GtkButton', name='back')
        self.assertThat(bk_button.visible, Equals(back_button))

        qt_button = self.main_window.select_single('GtkButton', name='quit')
        self.assertThat(qt_button.visible, Equals(quit_button))

        skp_button = self.main_window.select_single('GtkButton', name='skip')
        self.assertThat(skp_button.visible, Equals(skip_button))

    def _update_current_step(self, name):
        logger.debug("Updating current step to %s" % name)
        self.step_before = self.current_step
        self.current_step = name
        # Lets print current step
        print("Current step = {0}".format(self.current_step))

    def _update_table_row_count(self, config):
        " Returns number of rows in table"

        custom_page = self.main_window.select_single(
            'GtkAlignment',
            BuilderName='stepPartAdvanced')
        tree_view = custom_page.select_single('GtkTreeView')
        num = tree_view.get_number_of_rows()
        if num == self.total_number_partitions:
            #TODO: assert 'free space' changes to a partition
            # this will take some further work.
            time.sleep(15)
            return num

        if num == self.part_table_rows:

            timeout = 30
            while True:
                if num is not self.part_table_rows + 1:
                    time.sleep(1)

                    num = tree_view.get_number_of_rows()
                    if num is self.part_table_rows + 1:
                        break
                    elif not timeout:

                        raise ValueError("No new rows in partition table")
                    else:
                        timeout -= 1

        self.assertThat(num, Equals(self.part_table_rows + 1))
        self.part_table_rows = num
        return num

    def _update_page_titles(self, ):
        self.previous_page_title = self.current_page_title
        self.current_page_title = self.main_window.select_single(
            'GtkLabel',
            BuilderName='page_title').label

    def _check_page_titles(self, ):
        current_page_title = self.main_window.select_single(
            'GtkLabel',
            BuilderName='page_title')
        if self.current_step in self.english_config:
            if self.english_install and (
                    'page_title' in self.english_config[self.current_step]):
                #if english install check english values
                self.expectThat(current_page_title.label, Equals(
                    self.english_config[self.current_step]['page_title']))
        #also lets check it changed from the previous page

        message_one = "Expected %s page title '%s' to not equal the "\
            "previous %s page title '%s' but it does" % (
                self.current_step, self.current_page_title,
                self.step_before, self.previous_page_title)

        self.expectThat(self.previous_page_title,
                        NotEquals(self.current_page_title),
                        message=message_one)
        ## XXX Re-enable to catch bugs where page title changes after a page
        ##     has loaded
        #
        ## This second one catches the known bug for the stepPartAdvanced page
        ## title switching back to the prev page title
        #message_two = "Expected %s page title '%s' to not equal the "\
        #    "previous %s page title '%s' but it does" % (
        #        self.current_step, current_page_title.label,
        #        self.step_before, self.previous_page_title)
        ## This only runs if the current page title changes from its initial
        ## value when page loaded
        #if current_page_title.label != self.current_page_title:
        #    self.expectThat(self.previous_page_title,
        #                    NotEquals(current_page_title.label),
        #                    message=message_two)
        #    self.expectThat(current_page_title.visible, Equals(True),
        #                    "[Page:'{0}'] Expect page title to be visible "
        #                    "but it wasn't".format(self.current_step))

    def _check_preparing_statebox(self, stateboxName, visible=True,
                                  imagestock='gtk-yes'):
        """ Checks the preparing page statebox's """
        logger.debug("Running checks on {0} StateBox".format(stateboxName))
        preparing_page = self.main_window.select_single(
            'GtkAlignment', BuilderName='stepPrepare')
        state_box = preparing_page.select_single(
            'StateBox', BuilderName=stateboxName)
        logger.debug('check({0}, {1})'.format(visible, imagestock))
        logger.debug("Running checks.......")
        if visible:
            self.expectThat(state_box.visible, Equals(visible),
                            "StateBox.check(): Expected {0} statebox to be "
                            "visible but it wasn't"
                            .format(state_box.name))
            label = state_box.select_single('GtkLabel')
            self.expectThat(label.label, NotEquals(u''),
                            "[Page:'{0}'] Expected {1} Statebox's label to "
                            "contain text but it didn't"
                            .format(self.current_step, stateboxName))
            self.expectThat(label.visible, Equals(visible),
                            "[Page:'{0}'] Expected {1} Statebox label's "
                            "visible property to be {2} "
                            .format(self.current_step, stateboxName,
                                    str(visible)))
            self.expectIsInstance(label.label, str,
                                  "[Page:'{0}'] Expected {1} Statebox's label "
                                  "to be unicode but it wasn't"
                                  .format(self.current_step, stateboxName))
            image = state_box.select_single('GtkImage')
            self.expectThat(image.stock, Equals(imagestock))
            self.expectThat(image.visible, Equals(visible))

        else:
            self.expectThat(state_box.visible, Equals(False),
                            "[Page:'{0}'] Expected {1} statebox to not be "
                            "visible but it was"
                            .format(self.current_step, stateboxName))

    def get_distribution(self, ):
        """Returns the name of the running distribution."""
        logger.debug("Detecting flavor")
        with open('/cdrom/.disk/info') as f:
            for line in f:
                distro = line[:max(line.find(' '), 0) or None]
                if distro:
                    logger.debug("{0} flavor detected".format(distro))
                    return str(distro)
                raise SystemError("Could not get distro name")
