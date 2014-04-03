# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2013
#
# Author: Daniel Chapman daniel@chapman-mail.com
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import random
import time
from autopilot.input import Pointer, Mouse, Keyboard
from ubiquity_autopilot_tests.emulators import AutopilotGtkEmulatorBase
from ubiquity_autopilot_tests.tools.compare import expectThat
from ubiquity_autopilot_tests.emulators import gtkcontrols, gtkaccessible
import logging
logger = logging.getLogger(__name__)


class GtkContainers(AutopilotGtkEmulatorBase):
    """ Base class for all gtkcontainers objects """
    def __init__(self, *args):
        super(GtkContainers, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())


class GtkBox(GtkContainers):
    """ Emulator class for a GtkBox instance """
    def __init__(self, *args):
        super(GtkBox, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()

    def get_random_language(self, ):
        """ gets a random language from the 'stepLanguage' page

        :returns: A random TreeView item from the language treeview
        :raises: EmulatorException if function is not called from the
                step language page object

        You can now use select_language_item

        """
        logger.debug("get_random_language()")
        if self.name == 'stepLanguage':
            language_item = self._get_install_language()
            if language_item is None:
                raise ValueError("Language could not be selected")
            return language_item
        raise RuntimeError("Function can only be used from a stepLanguage "
                           "page object. Use .select_single('GtkBox, "
                           "name='stepLanguage')")

    def select_language(self, item):
        """ Selects a language for the install

        You can either use get_random_language or if you want to set the
        install language instead of randomly selecting an item. Then select
        from the treeview using GtkTreeView.select_item and pass the returned
        item to select_language

        :param item: A treeview item object
        :raises: exception if function not called from stepLanguage page object


        """
        if self.name == 'stepLanguage':
            logger.debug("select_language()")
            treeview = self.select_single('GtkTreeView')
            treeview.click()
            #for sanity lets ensure we always start at the top of the list
            logger.debug("Selecting top item of treeview list")
            self.kbd.press_and_release('Home')
            tree_items = treeview.get_all_items()
            top_item = tree_items[0]
            #If we are at the top
            if top_item.selected:
                logger.debug("top item {0} selected"
                             .format(top_item.accessible_name))
                #Now select required Language
                self.kbd.type(item.accessible_name[0:2])
                item.click()
                #check selected
                if item.selected:
                    logger.debug("Install language successfully selected! :-)")
                    return
                raise ValueError("Could not select Item")
            raise ValueError("Top item  not selected")
        raise ValueError("Function can only be used from a stepLanguage page "
                         "object. Use .select_single('GtkBox, "
                         "name='stepLanguage')")

    def _get_install_language(self, ):
        """ Gets a random language for the install

        :returns: an object of a TreeView item for the chosen language
        """
        logger.debug("_get_install_language()")
        treeview = self.select_single('GtkTreeView')
        #lets get all items
        treeview_items = treeview.get_all_items()

        #get a language which the first two chars can be ascii decoded
        test_language = self._get_decode_ascii_item(treeview_items)
        return test_language

    def _get_decode_ascii_item(self, items):
        """ decodes a list of unicode items """
        logger.debug("_get_decode_ascii_item()")
        # at the moment we can't select all locales as this would be a pain
        # to figure out all encodings for keyboard input
        lang_item = None
        l_ascii = None
        while True:
            lang_item = random.choice(items)
            l_unicode = lang_item.accessible_name
            logger.debug("Attempting to decode %s" % l_unicode)
            lan = l_unicode[0:2]
            try:
                l_ascii = lan.encode('ascii')
            except UnicodeEncodeError:
                logger.debug("%s could not be decoded" % l_unicode)
                pass
            if l_ascii:
                logger.debug("%s decoded successfully" % l_unicode)
                break
        logger.debug("Returning selected language: %s" % l_unicode)
        return lang_item

    def select_location(self, location):
        """ Selects a location on the timezone map """
        if self.name == 'stepLocation':
            logger.debug("select_location({0})".format(location))

            location_map = self.select_single('CcTimezoneMap')
            self.pointing_device.move_to_object(location_map)
            x1, y1, x2, y2 = location_map.globalRect
            #hmmmm this is tricky! and really hacky
            pos = self.pointing_device.position()
            x = pos[0]
            y = pos[1]
            x -= 25  # px
            self.pointing_device.move(x, y)
            while True:
                entry = self.select_single('GtkEntry')
                if entry.text != location:
                    pos = self.pointing_device.position()
                    x = pos[0]
                    y = pos[1]
                    y -= 10  # px
                    self.pointing_device.move(x, y)
                    self.pointing_device.click()
                    if y < y1:
                        logger.warning("We missed the location on the map and "
                                       "ended up outside the globalRect. Now "
                                       "using the default selected location "
                                       "instead")
                        break
                else:
                    expectThat(entry.text).equals(location)
                    logger.debug("Location; '{0}' selected".format(location))
                    break
        else:
            raise ValueError("Function can only be called from a "
                             "stepLocation page object")

    def create_user(self, name, password):
        """ Creates a user account with password

        :param name: Username
        :param password: user password

        """
        logger.debug("create_user({0}, {1})".format(name, password))
        if self.name == 'stepUserInfo':
            self._enter_username(name)
            self._enter_password(password)
        else:
            raise ValueError("Function can only be called froma stepUserInfo"
                             "page object")

    def _enter_username(self, name):
        """ Enters the username

        :param name: username for user account
        """
        logger.debug("_enter_username({0})".format(name))
        entry = self.select_single('GtkEntry', name='fullname')
        with self.kbd.focused_type(entry) as kb:
            kb.press_and_release('Ctrl+a')
            kb.press_and_release('Delete')
            kb.type(name)

        #lets get the fullname from the entry
        # as we don't know the kb layout till runtime
        fullname = entry.text
        logger.debug("Checking that name, username and hostname all contain "
                     "'{0}'".format(name))
        #now check computer name contains username
        hostname_entry = self.select_single('GtkEntry', name='hostname')
        expectThat(hostname_entry.text).contains(
            fullname.lower(),
            msg="GtkBox._enter_username(): Expected the hostname entry: "
                "'{0}', to contain '{1}'"
                .format(hostname_entry.text, fullname.lower()))
        #check username contains name
        username_entry = self.select_single('GtkEntry', name='username')
        expectThat(username_entry.text).contains(
            fullname.lower(),
            msg="GtkBox._enter_username(): Expected the username entry: "
                "'{0}', to contain '{1}'"
                .format(username_entry.text, fullname.lower()))
        #check the GtkYes images are now visible
        logger.debug("Checking the stock 'gtk-yes' images are visible")
        images = ['fullname_ok', 'hostname_ok', 'username_ok']
        for image in images:
            img = self.select_single('GtkImage', name=image)
            expectThat(img.visible).equals(
                True,
                msg="Expected {0} image to be visible but it wasn't"
                .format(img.name))
            expectThat(img.stock).equals(
                'gtk-yes',
                msg="Expected {0} image to have a 'gtk-yes' stock image and "
                    "not {1}".format(img.name, img.stock))

    def _enter_password(self, password):
        if self.name == 'stepUserInfo':

            while True:
                self._enter_pass_phrase(password)
                match = self._check_phrase_match()

                if match:
                    break
        else:
            raise ValueError("enter_crypto_phrase() can only be called from "
                             "stepPartCrypto page object")

    def _enter_pass_phrase(self, phrase):

        pwd_entries = ['password', 'verified_password']
        for i in pwd_entries:
            entry = self.select_single(BuilderName=i)
            with self.kbd.focused_type(entry) as kb:
                kb.press_and_release('Ctrl+a')
                kb.press_and_release('Delete')
                expectThat(entry.text).equals(
                    u'',
                    msg='{0} entry text was not cleared properly'
                    .format(entry.name))
                kb.type(phrase)

    def _check_phrase_match(self, ):
        pwd1 = self.select_single(BuilderName='password').text
        pwd2 = self.select_single(BuilderName='verified_password').text
        if pwd1 == pwd2:
            return True
        else:
            return False

    def encrypt_home_dir(self, encrypt=None):
        """ Check the login_encrypt box """
        chk_encrypt = self.select_single(BuilderName='login_encrypt')
        active = chk_encrypt.active

        if encrypt is None:
            # Switch checkbox and ensure it switched
            self.pointing_device.click_object(chk_encrypt)
            expectThat(chk_encrypt.active).equals(
                not active,
                msg='encrypt home checkbox state did not change. Current '
                'state: {0}'.format(chk_encrypt.active))
        elif encrypt and not active:
            self.pointing_device.click_object(chk_encrypt)
            expectThat(chk_encrypt.active).equals(
                True,
                msg='encrypt home checkbox not active and should be.')
        elif not encrypt and active:
            self.pointing_device.click_object(chk_encrypt)
            expectThat(chk_encrypt.active).equals(
                False,
                msg='encrypt home checkbox active and should not be.')
        else:
            raise ValueError("Invalid value for 'encrypt' parameter: {}"
                             .format(encrypt))


class GtkAlignment(GtkContainers):
    """ Emulator class for a GtkAlignment instance """
    def __init__(self, *args):
        super(GtkAlignment, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()

    def enter_crypto_phrase(self, crypto_phrase):
        if self.name == 'stepPartCrypto':

            while True:
                self._enter_pass_phrase(crypto_phrase)
                match = self._check_crypto_phrase_match()

                if match:
                    break
        else:
            raise ValueError("enter_crypto_phrase() can only be called from "
                             "stepPartCrypto page object")

    def _enter_pass_phrase(self, phrase):

        pwd_entries = ['password', 'verified_password']
        for i in pwd_entries:
            entry = self.select_single(BuilderName=i)
            with self.kbd.focused_type(entry) as kb:
                kb.press_and_release('Ctrl+a')
                kb.press_and_release('Delete')
                expectThat(entry.text).equals(
                    u'',
                    msg='{0} entry text was not cleared properly'
                        .format(entry.name))
                kb.type(phrase)

    def _check_crypto_phrase_match(self, ):
        pwd1 = self.select_single(BuilderName='password').text
        pwd2 = self.select_single(BuilderName='verified_password').text
        if pwd1 == pwd2:
            return True
        else:
            return False

    def create_new_partition_table(self, ):
        if self.name == 'stepPartAdvanced':
            new_partition_button = self.select_single(
                BuilderName='partition_button_new_label')
            self.pointing_device.click_object(new_partition_button)
            time.sleep(5)
            self.kbd.press_and_release('Right')
            self.kbd.press_and_release('Enter')
            time.sleep(5)
        else:
            raise ValueError("create_new_partition_table() can only be called "
                             "from stepPartAdvanced page object")
