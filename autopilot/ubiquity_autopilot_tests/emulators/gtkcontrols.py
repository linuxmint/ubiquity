# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2013
#
# Author: Daniel Chapman daniel@chapman-mail.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
from autopilot.input import Pointer, Mouse, Keyboard
from ubiquity_autopilot_tests.emulators import AutopilotGtkEmulatorBase
from ubiquity_autopilot_tests.tools.compare import expectThat
from ubiquity_autopilot_tests.emulators import gtkaccessible
import logging
import re
from collections import namedtuple
logger = logging.getLogger(__name__)


class GtkEntry(AutopilotGtkEmulatorBase):
    """ Emulator for a GtkEntry widget """
    def __init__(self, *args):
        super(GtkEntry, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()

    def click(self, ):
        """ Click on GtkEntry """
        self.pointing_device.click_object(self)


class GtkButton(AutopilotGtkEmulatorBase):
    """ Emulator for a GtkButton Instance """
    def __init__(self, *args):
        super(GtkButton, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def click(self,):
        """ Clicks a GtkButton widget

        On some occasions you may need to wait for a button to become
        sensitive.
        So when calling this function if the sensitive property is 0 it will
        wait for 10 seconds for button to become sensitive before clicking
        """
        #sometimes we may need to wait for the button to become clickable
        # so lets wait for it if we do
        logger.debug('Clicking "{0}" button'.format(self.name))
        if self.sensitive == 0:
            self.sensitive.wait_for(1)
        self.pointing_device.click_object(self)


class GtkLabel(AutopilotGtkEmulatorBase):
    """ Emulator for a GtkLabel Instance"""
    def __init__(self, *args):
        super(GtkLabel, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def click(self, ):
        """ Clicks on a GtkLabel """
        logger.debug('Clicking "{0}" label'.format(self.name))
        self.pointing_device.click_object(self)

    def check(self, visible=True):
        expectThat(self.label).is_unicode()
        expectThat(self.label).not_equals(
            u'',
            msg="Expected {0} label to contain text, but its empty"
                .format(self.name))
        expectThat(self.visible).equals(
            visible,
            msg="Expected {0} label to be visible, but its wasn't"
                .format(self.name))


class GtkToggleButton(AutopilotGtkEmulatorBase):
    """ Emulator for a GtkToggleButton instance """
    def __init__(self, *args):
        super(GtkToggleButton, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def check(self, visible=True):
        expectThat(self.label).is_unicode()
        expectThat(self.label).not_equals(
            u'',
            msg="Expected {0} label to contain text, but its empty"
                .format(self.name))
        expectThat(self.visible).equals(
            visible,
            msg="Expected {0} label to be visible, but its wasn't"
                .format(self.name))

    def click(self, ):
        """ Clicks a GtkToggleButton,

        and waits for the active state (toggled/nottoggled)
        to change after being clicked

        """
        #get current state
        new_val = 0
        if self.active == 0:
            new_val = 1
        logger.debug('Objects current state is "{0}", '
                     'the state after clicking should be "{1}"'
                     .format(self.active, new_val))
        #now click it
        self.pointing_device.click_object(self)
        #now wait for state to change
        self.active.wait_for(new_val)
        logger.debug('Object clicked, state change successful')


class GtkCheckButton(GtkToggleButton):
    """ Emulator for a GtkCheckButton instance """
    def __init__(self, *args):
        super(GtkCheckButton, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())


class GtkRadioButton(AutopilotGtkEmulatorBase):
    """ Emulator for a GtkRadioButton instance """
    def __init__(self, *args):
        super(GtkRadioButton, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def click(self, ):
        """ Clicks a GtkRadioButton

        If the Radio button is not already active, click and wait for
        active to be true

        """
        if self.active == 1:
            logger.debug('Object already selected. Returning')
            return
        #now click it
        self.pointing_device.click_object(self)
        #now wait for state to change
        self.active.wait_for(1)
        logger.debug(
            'Object clicked and and selected. Active state changed '
            'successfully')

    def check(self, visible=True):
        expectThat(self.label).is_unicode()
        expectThat(self.label).not_equals(
            u'',
            msg="Expected {0} label to contain text, but its empty"
                .format(self.name))
        expectThat(self.visible).equals(
            visible,
            msg="Expected {0} label to be visible, but its wasn't"
                .format(self.name))


class GtkImage(AutopilotGtkEmulatorBase):
    """ Emulator class for a GtkImage instance """
    def __init__(self, *args):
        super(GtkImage, self).__init__(*args)

    def check(self, visible=True, imageStock='gtk-yes'):
        if visible:
            expectThat(self.visible).equals(
                visible,
                msg="Expected {0} label to be visible, but its wasn't"
                    .format(self.name))

            expectThat(self.stock).equals(
                imageStock,
                msg="Expected {0} image to have stock image {1} but instead "
                    "it is {2}".format(self.name, imageStock, self.stock))


class GtkTreeView(AutopilotGtkEmulatorBase):
    """ Emulator for a GtkTreeView instance """
    def __init__(self, *args):
        super(GtkTreeView, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def click(self, ):
        """ This simply clicks a treeview object """
        self.pointing_device.click_object(self)
        expectThat(self.is_focus).equals(True)

    def select_item(self, labelText):
        """ Selects an item in a GtkTreeView by its UI label text

        :param labelText: The label value of the tree item as seen on the UI
        :returns: An object of the requested treeitem

        e.g. If you want to click say an item displaying 'Home' in a treeview
        then it would be::

            treeitem = treeview.select_item('Home')
            treeitem.click()

        If for some reason this doesn't work then use the :func:`click()`
        function to get the treeviews focus

        """
        logger.debug('Selecting "{0}" item'.format(labelText))
        try:
            # lets try and get the corresponding GailTreeView so we can assure
            # we are selecting the item from the correct treeview
            treeview = self._get_gail_treeview()
            treeview_item = treeview.select_item(str(labelText))
        except ValueError:
            # lets catch the exception and have one last go at selecting the
            # item from a root instance
            # This may return more than one though.
            logger.warning('Could not get corresponding '
                           'GtkTreeViewAccessibleObject with globalRect {0}. '
                           'Trying to select GtkTreeView item  from root '
                           'object instead'.format(self.globalRect))
            root = self.get_root_instance()
            if root is None:
                raise ValueError("Emulator could not get a root instance")

            treeview_item = root.select_single('GtkCellTextAccessible',
                                               accessible_name=str(labelText))
            if treeview_item is None:
                raise ValueError(
                    "Could not select item with label '{0}'".format(labelText))
        logger.debug('Corresponding Item Found in treeview. Returning item.')
        return treeview_item

    def select_item_by_index(self, index):
        """ Selects an item in a GtkTreeVIew by its index

        :param index: index of the list item
        :rtype: Object of the treeview item at the selected index

        """
        treeview = self._get_gail_treeview()
        treeview_item = treeview.select_item_by_index(index)
        if treeview_item is None:
            raise ValueError("Could not select item with index '{0}'"
                             .format(index))
        return treeview_item

    def get_all_items(self, startWith=None):
        logger.debug('GtkTreeView.get_all_items()')
        treeview = self._get_gail_treeview()
        items = treeview.get_all_items(startWith)
        if items is None:
            raise ValueError("NoneType: Could not get list of items")
        return items

    def get_partition_table_dict(self, ):
        """ Returns a dict of named tuples generated by the list
            of items returned from get_all_items.

            This enables us to access any available table cell
            using the Row number and column name

            example usage:

            >>> treeview = self.app.select_single('GtkTreeView')
            >>> table = treeview.get_partition_table_dict()
            # we can now access any cell using Row number as Key and
            column name
             i.e table['Row Number'].ColumnName

            >>> item = table['Row2'].Mount

            We now have an introspectable object for that particular
            cell which we can use
            to either assert the properties of the cell and also click etc....

            >>> self.assertThat(item.accessible_name, Equals('/home'))
            >>> self.mouse.click(item)
        """
        #first get accessible tree
        treeview = self._get_gail_treeview()
        # Now each column header is a GtkButton, so we get the label from each
        # one and create a list
        tree_column_objects = treeview.select_many('GtkButtonAccessible')
        column_names = []
        for column in tree_column_objects:
            #We are only interested in columns with headers. Blank columns
            # seem to usually be used for spacing and contain no cells
            if column.accessible_name == '':
                pass
            else:
                #strip all non alpaha chars
                name = re.sub(r'\W+', '', column.accessible_name)
                column_names.append(name)
        # Create a named tuple using the column headers, which enables access
        # to the column by name
        Columns = namedtuple('Columns', column_names)
        #generate a list of items
        tree_items = treeview.get_all_items()
        # lets create a temp list
        temp_list = []
        #TODO: we actually don't really need this
        for item in tree_items:
            temp_list.append(item)
        # so we want to create a Columns tuple for each row in the table
        # therefore picking only the n items where n is the number of column
        # names
        start, end = 0, len(column_names)
        row_list, table_dict = [], {}
        for i in range(0, int(len(temp_list) / len(column_names))):
            # fill columns tuple
            row = Columns(*temp_list[start:end])
            # create a new tuple adding the current row number
            # which we will use as dict key
            row_list.append(('Row{0}'.format(i+1), row))
            # update our table dict
            table_dict.update(row_list)
            # remove the items we just added from the temp list
            del temp_list[start:end]
        # return table_dict
        return table_dict

    def get_number_of_rows(self, ):
        items = self.get_partition_table_dict()
        return len(items)

    def _get_gail_treeview(self, ):
        """
        Gets the GtkTreeViews corresponding GtkTreeViewAccessible object
        """
        logger.debug('Getting corresponding GtkTreeViewAccessible object')
        # lets get a root instance
        root = self.get_root_instance()
        assert root is not None
        # As the treeview item is in the GAILWindow tree and not our current
        # tree We want to select the treeviewaccessible with the same
        # globalRect as us
        logger.debug('Selecting GtkTreeViewAccessible with same globalRect')
        treeviews = root.select_many('GtkTreeViewAccessible',
                                     globalRect=self.globalRect)
        # if the treeviews are nested they could potentially have the
        # same globalRect so lets pick out the one thats visible
        for treeview in treeviews:
            if treeview.visible:
                logger.debug('GtkTreeViewAccessible object found, '
                             'returning object.')
                return treeview
        raise ValueError(
            "No treeview visible with globalRect {0}".format(self.globalRect)
        )


class GtkComboBox(AutopilotGtkEmulatorBase):
    """ Emulator class for a GtComboBox instance"""
    def __init__(self, *args):
        super(GtkComboBox, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()

    def click(self, ):
        """Click Instance """
        self.pointing_device.click_object(self)

    def select_item(self, labelText, enter=True):
        """ Selects an item in a GtkComboBox by its UI label text value

        :param labelText: The label value of the list item as seen on the UI
        :raises: **ValueError** when item is not in ComboBox list

        e.g. ::

             combobox = self.main_window.select_single('GtkComboBox')
             combobox.select_item('ListItem')

        If for some reason this doesn't work then use the :func:`click()`
        function to get the combobox focus

        """
        logger.debug('Selecting "{0}" item'.format(labelText))
        #get our gail combo to start
        combo = self._get_gail_combobox()
        # get total number of items in the combo
        items = combo.select_many('GtkMenuItemAccessible')
        self.click()
        # lets start at the top of the list
        self.kbd.press_and_release('Home')
        if enter:
            self.kbd.press_and_release('Enter')
        else:
            self.kbd.press_and_release('Down')

        #XXX: we should probably check the item is in the combo before
        # cycling through.
        for item in items:
            if labelText == combo.accessible_name:
                logger.debug('Item is now selected')
                return
            else:
                logger.debug('Go to next item in combo')
                self.kbd.press_and_release('Down')

        raise ValueError(
            'Item with label text "{0}" was not found'.format(labelText))

    def select_filesystem_format(self, fsFormat):
        logger.debug('Selecting "{0}" item'.format(fsFormat))
        #get our gail combo to start
        combo = self._get_gail_combobox()
        # get total number of items in the combo
        items = combo.select_many('GtkMenuItemAccessible')
        self.click()
        # lets start at the top of the list
        self.kbd.press_and_release('Home')
        self.kbd.press_and_release('Enter')

        index = next((index for index, value in enumerate(items)
                      if fsFormat == value.accessible_name), None)

        i = 0
        while True:
            if i < index:
                self.kbd.press_and_release('Down')
                i += 1
            else:
                assert i == index
                break

    def _get_gail_combobox(self, ):
        """ Gets the GtkComBox's corresponding GtkComboBoxAccessible object """
        # lets get a root instance
        logger.debug('Getting corresponding GtkComboBoxAccessible object')
        root = self.get_root_instance()
        assert root is not None
        combos = root.select_many('GtkComboBoxAccessible',
                                  globalRect=self.globalRect)
        for combo in combos:
            if combo.visible:
                logger.debug('Combo found, returning combo')
                return combo
        raise ValueError(
            "No ComboBox visible with globalRect {0}".format(self.globalRect)
        )


class GtkComboBoxText(GtkComboBox):
    """ Emulator class for a GtkComboBoxText instance

    .. note:: see :func:`GtkComboBox`. `GtkComboBoxText` inherits from
        `GtkComboBox`

    """
    def __init__(self, *args):
        super(GtkComboBoxText, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()


class GtkSpinButton(AutopilotGtkEmulatorBase):
    """ Emulator class for a GtSpinButton instance"""
    def __init__(self, *args):
        super(GtkSpinButton, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
        self.kbd = Keyboard.create()

    def enter_value(self, value):
        self._select_entry()
        self.kbd.type(value)
        expectThat(self.text).equals(
            value,
            msg="Expected spinbutton value '{0}' to equal {1}"
                .format(self.text, value))

    def _select_entry(self, ):
        self.pointing_device.move_to_object(self)
        pos = self.pointing_device.position()
        x = pos[0]
        y = pos[1]
        x -= 15  # px
        self.pointing_device.move(x, y)
        self.pointing_device.click()
        self.kbd.press_and_release('Ctrl+a')
        self.kbd.press_and_release('Delete')


class GtkProgressBar(AutopilotGtkEmulatorBase):
    """ Emulator class for a GtkProgressBar instance"""
    def __init__(self, *args):
        super(GtkProgressBar, self).__init__(*args)
