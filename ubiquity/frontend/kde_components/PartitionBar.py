# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2006, 2007, 2008, 2009 Canonical Ltd.
#
# Author:
#   Jonathan Riddell <jriddell@ubuntu.com>
#   Roman Shtylman <shtylman@gmail.com>
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or at your option)
# any later version.
#
# Ubiquity is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with Ubiquity; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
##################################################################################

import sys

from PyQt4 import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from ubiquity.misc import format_size

class Partition:
    # colors used to render partition types
    # 'auto' is used to represent the results of automatic partitioning.
    filesystemColours = {'auto':        '#509DE8',
                         'ext3':        '#418DD4',
                         'ext4':        '#418DD4',
                         'free':        '#FFFFFF',
                         'linux-swap':  '#FF80E0',
                         'fat32':       '#C0DAFF',
                         'fat16':       '#C0DAFF',
                         'ntfs':        '#888786'}

    def __init__(self, name, size, fs):
        self.size = size
        self.fs = fs
        self.next = None
        self.index = None
        self.name = name

class PartitionsBar(QWidget):
    InfoColor = '#333333'

    ## signals
    partitionResized = pyqtSignal(['PyQt_PyObject', 'PyQt_PyObject'])

    def __init__(self, parent = None):
        """ a widget to graphically show disk partitions. """
        QWidget.__init__(self, parent)
        self.partitions = []
        self.bar_height = 20 #should be a multiple of 2
        self.diskSize = 0
        self.radius = 4
        self.setMinimumHeight(self.bar_height + 40)
        self.setMinimumWidth(500)
        sizePolicy = self.sizePolicy()
        sizePolicy.setVerticalStretch(10)
        sizePolicy.setVerticalPolicy(QSizePolicy.Fixed)
        self.setSizePolicy(sizePolicy)

        self.resize_loc = 0
        self.resizing = False
        self.resize_part = None

    def paintEvent(self, qPaintEvent):
        painter = QPainter(self)

        #used for drawing sunken frame
        sunkenFrameStyle = QStyleOptionFrame()
        sunkenFrameStyle.state = QStyle.State_Sunken

        h = self.bar_height
        h_2 = self.bar_height/2
        effective_width = self.width() - 1

        path = QPainterPath()
        path.addRoundedRect(1, 1, self.width()-2, h-2, self.radius, self.radius)

        part_offset = 0
        label_offset = 0
        trunc_pix = 0
        resize_handle_x = None
        for p in self.partitions:
            painter.setRenderHint(QPainter.Antialiasing, True)

            #this is done so that even after resizing, other partitions draw in the same places
            trunc_pix += (effective_width * float(p.size) / self.diskSize)
            pix_size = int(round(trunc_pix))
            trunc_pix -= pix_size

            #use the right color for the filesystem
            if Partition.filesystemColours.has_key(p.fs):
                pColor = QColor(Partition.filesystemColours[p.fs])
            else:
                pColor = QColor(Partition.filesystemColours['free'])

            pal = QPalette(pColor)
            dark = pal.color(QPalette.Dark)
            mid = pColor.darker(125)
            midl = mid.lighter(125)

            grad = QLinearGradient(QPointF(0, 0), QPointF(0, h))

            if p.fs == "free":
                grad.setColorAt(.25, mid)
                grad.setColorAt(1, midl)
            else:
                grad.setColorAt(0, midl)
                grad.setColorAt(.75, mid)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.setClipRect(part_offset, 0, pix_size, h*2)
            painter.drawPath(path)

            if part_offset > 0:
                painter.setPen(dark)
                painter.drawLine(part_offset, 3, part_offset, h - 3)

            painter.setClipping(False)

            draw_labels = True
            if draw_labels:
                #draw the labels
                painter.setPen(Qt.black)

                #name is the path by default, or free space if unpartitioned
                name = p.name
                if name == None:
                    if p.fs == 'free':
                        name = 'free space'
                    elif p.fs == 'swap':
                        name = 'swap'
                    else:
                        name = p.path

                #label vertical location
                labelY = h + 8

                texts = []
                texts.append(name)
                texts.append("%.01f%% (%s)" % (float(p.size) / self.diskSize * 100, format_size(p.size)))

                nameFont = QFont("arial", 10)
                infoFont = QFont("arial", 8)

                painter.setFont(nameFont)
                v_off = 0
                width = 0
                for text in texts:
                    textSize = painter.fontMetrics().size(Qt.TextSingleLine, text)
                    painter.drawText(label_offset + 20, labelY + v_off + textSize.height()/2, text)
                    v_off += textSize.height()
                    painter.setFont(infoFont)
                    painter.setPen(QColor(PartitionsBar.InfoColor))
                    width = max(width, textSize.width())

                painter.setPen(Qt.NoPen)
                painter.setBrush(mid)
                labelRect = QPainterPath()
                labelRect.addRoundedRect(label_offset+1, labelY - 3, 13, 13, 4, 4)
                painter.drawPath(labelRect)

                sunkenFrameStyle.rect = QRect(label_offset, labelY-4, 15, 15)
                self.style().drawPrimitive(QStyle.PE_Frame, sunkenFrameStyle, painter, self)
                self.style().drawPrimitive(QStyle.PE_Frame, sunkenFrameStyle, painter, self)

                label_offset += width + 40

            #set the handle location for drawing later
            if self.resize_part and p == self.resize_part.next:
                resize_handle_x = part_offset

            #increment the partition offset
            part_offset += pix_size

        sunkenFrameStyle.rect = QRect(0, 0, self.width(), h)
        self.style().drawPrimitive(QStyle.PE_Frame, sunkenFrameStyle, painter, self)

        if self.resize_part and resize_handle_x:
            # draw a resize handle
            part = self.resize_part
            xloc = resize_handle_x
            self.resize_loc = xloc
            side = 1
            arr_dist = 5

            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.black)

            painter.setRenderHint(QPainter.Antialiasing, True)
            #move out so not created every time
            arrow_offsets = (
                (0, h/2-1), (4, h/2-1), (4, h/2-3), (8, h/2),
                (4, h/2+3), (4, h/2+1), (0, h/2+1))

            p1 = arrow_offsets[0]
            if part.size > part.minsize:
                arrow = QPainterPath(QPointF(xloc + -1 * p1[0], p1[1]))
                for p in arrow_offsets:
                    arrow.lineTo(xloc + -1 * p[0] + 1, p[1])
                painter.drawPath(arrow)

            if part.size < part.maxsize:
                arrow = QPainterPath(QPointF(xloc + p1[0], p1[1]))
                for p in arrow_offsets:
                    arrow.lineTo(xloc + p[0], p[1])
                painter.drawPath(arrow)

            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setPen(Qt.black)
            painter.drawLine(xloc, 0, xloc, h)

    def addPartition(self, name, size, fs):
        partition = Partition(name, size, fs)
        self.diskSize += size

        #set the previous partition to have this one as next partition
        if len(self.partitions) > 0:
            last = self.partitions[len(self.partitions)-1]
            last.next = partition

        self.partitions.append(partition)

    def setResizePartition(self, path, minsize, maxsize, prefsize, new_label):
        part = None
        index = 0
        for p in self.partitions:
            if p.name == path:
                part = p
                break
            index += 1

        if not part:
            return

        if prefsize > maxsize:
            prefsize = maxsize

        new_size = part.size - prefsize
        part.size = prefsize
        part.minsize = minsize
        part.maxsize = maxsize
        part.prefsize = prefsize

        self.resize_part = part

        if part.next == None or part.next.index != -1:
            #if our resize partition is at the end or the next one is not free space
            p = Partition('Kubuntu', new_size, 'auto')
            p.next = part.next
            part.next = p

            #insert a new fake partition after the resize partition
            self.partitions.insert(index + 1, p)
        else:
            #we had a next partition that was free space, use that
            #set the size of the next partition accordingly
            part.next.size += new_size

        # need mouse tracking to be able to change the cursor
        self.setMouseTracking(True)

    def mousePressEvent(self, qMouseEvent):
        if self.resize_part:
            # if pressed on bar
            if abs(qMouseEvent.x() - self.resize_loc) < 3:
                self.resizing = True

    def mouseMoveEvent(self, qMouseEvent):
        if self.resizing:
            start = 0
            for p in self.partitions:
                if p == self.resize_part:
                    break
                start += p.size

            ew = self.width() - 1
            bpp = self.diskSize / float(ew)

            # mouse position in bytes within this partition
            mx = qMouseEvent.x() * bpp - start

            #make sure we are within resize range
            if mx < self.resize_part.minsize:
                mx = self.resize_part.minsize
            elif mx > self.resize_part.maxsize:
                mx = self.resize_part.maxsize

            #chagne the partition sizes
            span = self.resize_part.prefsize
            percent = mx / float(span)
            oldsize = self.resize_part.size
            self.resize_part.size = int(round(span * percent))
            self.resize_part.next.size -= self.resize_part.size - oldsize

            #sum the partitions and make sure the disk size is still the same
            #this is a precautionary measure
            t = 0
            for p in self.partitions:
                t = t + p.size
            assert t == self.diskSize

            self.update()

            #using PyQt object to avoid wrapping the size otherwise qt truncates to 32bit int
            self.partitionResized.emit(self.resize_part.name, self.resize_part.size)
        else:
            if self.resize_part:
                if abs(qMouseEvent.x() - self.resize_loc) < 3:
                    self.setCursor(Qt.SplitHCursor)
                elif self.cursor != Qt.ArrowCursor:
                    self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, qMouseEvent):
        self.resizing = False
