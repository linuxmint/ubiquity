# -*- coding: utf-8 -*-

import os
from PyQt4 import uic
from PyQt4.QtGui import *

from ubiquity.frontend.kde_components.PartitionBar import PartitionsBar
from ubiquity.misc import *

_uidir="/usr/share/ubiquity/qt/"

def addBars(parent, before_bar, after_bar):
    frame = QWidget(parent)
    frame.setLayout(QVBoxLayout())
    frame.layout().setSpacing(0)

    # TODO
    #frame.layout().addWidget(QLabel(get_string('ubiquity/text/partition_layout_before')))
    frame.layout().addWidget(QLabel("Before:"))
    frame.layout().addWidget(before_bar)
    #frame.layout().addWidget(QLabel(get_string('ubiquity/text/partition_layout_after')))
    frame.layout().addWidget(QLabel("After:"))
    frame.layout().addWidget(after_bar)

    parent.layout().addWidget(frame)
    return frame

class PartAuto(QWidget):

    def __init__(self):
        QWidget.__init__(self)

        uic.loadUi(os.path.join(_uidir,'stepPartAuto.ui'), self)

        self.diskLayout = None

        self.autopartition_buttongroup = QButtonGroup(self)

        self._clearInfo()

    def _clearInfo(self):
        self.extra_bar_frames = []
        self.autopartitionTexts = []
        self.extraChoicesText = {}

        self.resizeSize = None
        self.resizeChoice = None
        self.manualChoice = None

    def setDiskLayout(self, diskLayout):
        self.diskLayout = diskLayout

    def setupChoices (self, choices, extra_options,
                                   resize_choice, manual_choice,
                                   biggest_free_choice):
        self._clearInfo()

        self.resizeChoice = resize_choice
        self.manualChoice = manual_choice

        # remove any previous autopartition selections
        for child in self.autopart_selection_frame.children():
            if isinstance(child, QWidget):
                child.setParent(None)
                del child

        for child in self.barsFrame.children():
            if isinstance(child, QWidget):
                self.barsFrame.layout().removeWidget(child)
                child.setParent(None)
                del child

        release_name = get_release_name()

        bId = 0
        for choice in choices:
            button = QRadioButton(choice, self.autopart_selection_frame)
            self.autopart_selection_frame.layout().addWidget(button)
            self.autopartition_buttongroup.addButton(button, bId)
            bId += 1

            #Qt changes the string by adding accelerators,
            #so keep pristine string here as is returned later to partman
            self.autopartitionTexts.append(choice)

            ## these three things are toggled by each option
            # extra options frame for the option
            #frame = None
            bar_frame = QFrame()
            bar_frame.setLayout(QVBoxLayout())
            bar_frame.setVisible(False)
            bar_frame.layout().setSpacing(0)
            self.barsFrame.layout().addWidget(bar_frame)

            button.toggled[bool].connect(bar_frame.setVisible)

            # if we have more information about the choice
            # i.e. various hard drives to install onto
            if choice in extra_options:
                # label for the before device
                dev = None

                if choice == biggest_free_choice:
                    biggest_free_id = extra_options[choice]
                    dev = None

                    try:
                        resize_path = biggest_free_id[3]
                        dev = self.diskLayout[resize_path.replace("/", "=").rstrip("1234567890")]
                    except Exception: pass

                    if dev:
                        #create partition bars for graphical before/after display
                        before_bar = PartitionsBar()
                        after_bar = PartitionsBar()

                        for p in dev:
                            before_bar.addPartition(p[0], int(p[1]), p[3])
                            if p[1] == biggest_free_id:
                                after_bar.addPartition(release_name, int(p[1]), 'auto')
                            else:
                                after_bar.addPartition(p[0], int(p[1]), p[3])

                        addBars(bar_frame, before_bar, after_bar)

                # install side by side/resize
                elif choice == resize_choice:
                    # information about what can be resized
                    extraInfo = extra_options[choice]

                    min_size, max_size, pref_size, resize_path = extraInfo
                    self.resizeSize = pref_size

                    try:
                        dev = self.diskLayout[resize_path.replace("/", "=").rstrip("1234567890")]
                    except Exception: pass

                    if dev:
                        before_bar = PartitionsBar()
                        after_bar = PartitionsBar()

                        for p in dev:
                            #addPartition(name, size, fs):
                            before_bar.addPartition(p[0], int(p[1]), p[3])
                            after_bar.addPartition(p[0], int(p[1]), p[3])

                        after_bar.setResizePartition(resize_path,
                            min_size, max_size, pref_size, release_name)
                        after_bar.partitionResized.connect(self.on_partitionResized)

                        addBars(bar_frame, before_bar, after_bar)

                #full disk install
                elif choice != manual_choice:
                    # setup new frame to hold combo box
                    # this allows us to make the combo box indented over
                    # as well as not stretch to full width as it would do in the
                    # vertical layout
                    frame = QFrame()
                    self.autopart_selection_frame.layout().addWidget(frame)

                    frame_layout = QHBoxLayout(frame)
                    self.extra_combo = QComboBox()
                    self.extra_combo.setEnabled(False)

                    self.autopart_selection_frame.layout().addWidget(self.extra_combo)

                    frame_layout.addSpacing(20)
                    frame_layout.addWidget(self.extra_combo)
                    frame_layout.addStretch(1)

                    self.extra_bar_frames = []
                    comboTexts = []

                    button.toggled[bool].connect(self.extra_combo.setEnabled)

                    for extra in extra_options[choice]:
                        #each extra choice needs to toggle a change in the before bar
                        #extra is just a string with a general description
                        #each extra choice needs to be a before/after bar option
                        if extra == '':
                            continue

                        extra_bar_frame = None

                        # add the extra disk to the combo box
                        self.extra_combo.addItem(extra)
                        self.extra_combo.currentIndexChanged[int].connect(self.on_extra_combo_changed)

                        #find the device to make a partition bar out of it
                        dev = None
                        for d in self.diskLayout:
                            disk = d
                            if disk.startswith('=dev='):
                                disk = disk[5:]
                            if "(%s)" % disk in extra:
                                dev = self.diskLayout[d]
                                break

                        #add the bars if we found the device
                        if dev:
                            before_bar = PartitionsBar()
                            after_bar = PartitionsBar()

                            for p in dev:
                                before_bar.addPartition(p[0], int(p[1]), p[3])

                            if before_bar.diskSize > 0:
                                after_bar.addPartition(release_name, before_bar.diskSize, 'auto')
                            else:
                                after_bar.addPartition(release_name, 1, 'auto')

                            extra_bar_frame = addBars(bar_frame, before_bar, after_bar)
                            if len(self.extra_bar_frames) > 0:
                                extra_bar_frame.setVisible(False)

                        if extra_bar_frame is not None:
                            self.extra_bar_frames.append(extra_bar_frame)

                        # Qt changes the string by adding accelerators,
                        # so keep the pristine string here to be
                        # returned to partman later.
                        comboTexts.append(extra)

                    self.extraChoicesText[choice] = comboTexts

        #select the first button
        b = self.autopartition_buttongroup.button(0)
        if b:
            b.setChecked(True)

    # slot for when partition is resized on the bar
    def on_partitionResized(self, path, size):
        #self.resizePath = path
        self.resizeSize = size

    def getChoice (self):
        bId = self.autopartition_buttongroup.checkedId()
        if bId > -1:
            choice = unicode(self.autopartitionTexts[bId])
        else:
            raise AssertionError, "no active autopartitioning choice"

        if choice == self.resizeChoice:
            # resize choice should have been hidden otherwise
            assert self.resizeSize is not None
            return choice, '%d B' % self.resizeSize
        elif (choice != self.manualChoice and
            self.extraChoicesText.has_key(choice)):
            comboId = self.extra_combo.currentIndex()
            disk_texts = self.extraChoicesText[choice]
            return choice, unicode(disk_texts[comboId])
        else:
            return choice, None

    def on_extra_combo_changed(self, index):
        for e in self.extra_bar_frames:
            e.setVisible(False)
        self.extra_bar_frames[index].setVisible(True)
