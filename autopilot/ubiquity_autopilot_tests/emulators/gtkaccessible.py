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
from autopilot.input import Pointer, Mouse
from ubiquity_autopilot_tests.emulators import AutopilotGtkEmulatorBase

import logging
logger = logging.getLogger(__name__)


class GtkButtonAccessible(AutopilotGtkEmulatorBase):

    def __init__(self, *args):
        super(GtkButtonAccessible, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def click(self, ):
        logger.debug('Clicking {0} item'.format(self.accessible_name))
        self.pointing_device.click_object(self)


class GtkTextCellAccessible(AutopilotGtkEmulatorBase):

    def __init__(self, *args):
        super(GtkTextCellAccessible, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def click(self, ):
        logger.debug('Clicking tree item')
        self.pointing_device.click_object(self)


class GtkTreeViewAccessible(AutopilotGtkEmulatorBase):

    def __init__(self, *args):
        super(GtkTreeViewAccessible, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())

    def select_item(self, label):
        """ Selects an item in a GtkTreeViewAccessible object """
        logger.debug('Selecting {0} item'.format(label))
        item = self._get_item(label)
        if item is None:
            raise ValueError("Could not select item with label {0}"
                             .format(label))
        logger.debug('{0} item found, returning item'.format(label))
        return item

    def select_item_by_index(self, index):
        """ Select an item by its index """
        return self._get_treeview_items()[index]

    def get_all_items(self, startWith=None):
        """ Gets all items in GtkTreeView

        :param startWith: gets a list of items that start with given string
        :rtype: List of items in treeview

        """
        item_list = []
        items = self._get_treeview_items()
        if startWith:
            logger.debug(
                "Searching for items beginning with '{0}'".format(startWith))
            for item in items:
                if startWith in item.accessible_name[0:len(startWith)+1]:
                    item_list.append(item)
            return item_list
        else:
            return items

    def _get_treeview_items(self, ):
        logger.debug('Getting list of items.....')
        items = self.select_many('GtkTextCellAccessible')
        if items is None:
            raise ValueError(
                "Could not get a list of treeview items"
            )
        return items

    def _get_item(self, label):
        """ Gets an item in a GtkTreeView """
        return self.select_single('GtkTextCellAccessible',
                                  accessible_name=label)


class GtkNoteBookAccessible(AutopilotGtkEmulatorBase):

    def __init__(self, *args):
        super(GtkNoteBookAccessible, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())


class GtkNoteBookPageAccessible(AutopilotGtkEmulatorBase):

    def __init__(self, *args):
        super(GtkNoteBookPageAccessible, self).__init__(*args)
        self.pointing_device = Pointer(Mouse.create())
