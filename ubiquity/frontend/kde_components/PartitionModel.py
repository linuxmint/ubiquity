# -*- coding: utf-8 -*-

import syslog

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from ubiquity.misc import *
from ubiquity.components import partman, partman_commit

# describes the display for the manual partition view widget
class PartitionModel(QAbstractItemModel):
    def __init__(self, ubiquity, parent=None):
        QAbstractItemModel.__init__(self, parent)

        rootData = []
        rootData.append(QVariant(ubiquity.get_string('partition_column_device')))
        rootData.append(QVariant(ubiquity.get_string('partition_column_type')))
        rootData.append(QVariant(ubiquity.get_string('partition_column_mountpoint')))
        rootData.append(QVariant(ubiquity.get_string('partition_column_format')))
        rootData.append(QVariant(ubiquity.get_string('partition_column_size')))
        rootData.append(QVariant(ubiquity.get_string('partition_column_used')))
        self.rootItem = TreeItem(rootData)

    def append(self, data, ubiquity):
        self.rootItem.appendChild(TreeItem(data, ubiquity, self.rootItem))

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return QVariant()

        item = index.internalPointer()

        if role == Qt.CheckStateRole and index.column() == 3:
            return QVariant(item.data(index.column()))
        elif role == Qt.DisplayRole and index.column() != 3:
            return QVariant(item.data(index.column()))
        else:
            return QVariant()

    def setData(self, index, value, role):
        item = index.internalPointer()
        if role == Qt.CheckStateRole and index.column() == 3:
            item.partman_column_format_toggled(value.toBool())
        self.emit(SIGNAL("dataChanged(const QModelIndex&, const QModelIndex&)"), index, index)
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled

        #self.setData(index, QVariant(Qt.Checked), Qt.CheckStateRole)
        #return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 3:
            item = index.internalPointer()
            if item.formatEnabled():
                return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
            else:
                return Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.rootItem.data(section)

        return QVariant()

    def index(self, row, column, parent = QModelIndex()):
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        return parentItem.childCount()

    def children(self):
        return self.rootItem.children()

class TreeItem:
    def __init__(self, data, ubiquity=None, parent=None):
        self.parentItem = parent
        self.itemData = data
        self.childItems = []
        self.ubiquity = ubiquity

    def appendChild(self, item):
        self.childItems.append(item)

    def child(self, row):
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def children(self):
        return self.childItems

    def columnCount(self):
        if self.parentItem is None:
            return len(self.itemData)
        else:
            return 5

    def data(self, column):
        if self.parentItem is None:
            return QVariant(self.itemData[column])
        elif column == 0:
            return QVariant(self.partman_column_name())
        elif column == 1:
            return QVariant(self.partman_column_type())
        elif column == 2:
            return QVariant(self.partman_column_mountpoint())
        elif column == 3:
            return QVariant(self.partman_column_format())
        elif column == 4:
            return QVariant(self.partman_column_size())
        elif column == 5:
            return QVariant(self.partman_column_used())
        else:
            return QVariant("other")

    def parent(self):
        return self.parentItem

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)

        return 0

    def partman_column_name(self):
        partition = self.itemData[1]
        if 'id' not in partition:
            # whole disk
            return partition['device']
        elif partition['parted']['fs'] != 'free':
            return '  %s' % partition['parted']['path']
        elif partition['parted']['type'] == 'unusable':
            return '  %s' % self.ubiquity.get_string('partman/text/unusable')
        else:
            # partman uses "FREE SPACE" which feels a bit too SHOUTY for
            # this interface.
            return '  %s' % self.ubiquity.get_string('partition_free_space')

    def partman_column_type(self):
        partition = self.itemData[1]
        if 'id' not in partition or 'method' not in partition:
            if ('parted' in partition and
                partition['parted']['fs'] != 'free' and
                'detected_filesystem' in partition):
                return partition['detected_filesystem']
            else:
                return ''
        elif ('filesystem' in partition and
              partition['method'] in ('format', 'keep')):
            return partition['acting_filesystem']
        else:
            return partition['method']

    def partman_column_mountpoint(self):
        partition = self.itemData[1]
        if isinstance(self.ubiquity.dbfilter, partman.Partman):
            mountpoint = self.ubiquity.dbfilter.get_current_mountpoint(partition)
            if mountpoint is None:
                mountpoint = ''
        else:
            mountpoint = ''
        return mountpoint

    def partman_column_format(self):
        partition = self.itemData[1]
        if 'id' not in partition:
            return ''
            #cell.set_property('visible', False)
            #cell.set_property('active', False)
            #cell.set_property('activatable', False)
        elif 'method' in partition:
            if partition['method'] == 'format':
                return Qt.Checked
            else:
                return Qt.Unchecked
            #cell.set_property('visible', True)
            #cell.set_property('active', partition['method'] == 'format')
            #cell.set_property('activatable', 'can_activate_format' in partition)
        else:
            return Qt.Unchecked  ##FIXME should be enabled(False)
            #cell.set_property('visible', True)
            #cell.set_property('active', False)
            #cell.set_property('activatable', False)

    def formatEnabled(self):
        """is the format tickbox enabled"""
        partition = self.itemData[1]
        return 'method' in partition and 'can_activate_format' in partition

    def partman_column_format_toggled(self, value):
        if not self.ubiquity.allowed_change_step:
            return
        if not isinstance(self.ubiquity.dbfilter, partman.Partman):
            return
        #model = user_data
        #devpart = model[path][0]
        #partition = model[path][1]
        devpart = self.itemData[0]
        partition = self.itemData[1]
        if 'id' not in partition or 'method' not in partition:
            return
        self.ubiquity.allow_change_step(False)
        self.ubiquity.dbfilter.edit_partition(devpart, format='dummy')

    def partman_column_size(self):
        partition = self.itemData[1]
        if 'id' not in partition:
            return ''
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['parted']['size']) / 1000000
            return '%d MB' % size_mb

    def partman_column_used(self):
        partition = self.itemData[1]
        if 'id' not in partition or partition['parted']['fs'] == 'free':
            return ''
        elif 'resize_min_size' not in partition:
            return self.ubiquity.get_string('partition_used_unknown')
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['resize_min_size']) / 1000000
            return '%d MB' % size_mb
            