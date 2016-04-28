from __future__ import print_function

import sys
import os.path

from PyQt4.QtGui import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt4.QtSvg import QSvgWidget


class SquareSvgWidget(QSvgWidget):
    def __init__(self, parent=None):
        QSvgWidget.__init__(self, parent)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHeightForWidth(True)
        self.setSizePolicy(sizePolicy)

    def heightForWidth(self, width):
        return width


class StateBox(QWidget):
    def __init__(self, parent, text=''):
        QWidget.__init__(self, parent)

        self.label = QLabel(text, self)
        self.image = SquareSvgWidget(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image)
        layout.addWidget(self.label)
        layout.addStretch()

        self.set_state(True)

    def set_state(self, state):
        self.status = state
        if state:
            # A tickmark
            name = "dialog-ok-apply.svg"
        else:
            # A cross
            name = "edit-delete.svg"
        icon = "/usr/share/icons/breeze/actions/22/" + name
        if not os.path.isfile(icon):
            icon = "/usr/share/icons/breeze/actions/toolbar/" + name
        self.image.load(icon)

    def get_state(self):
        return self.status

    def set_property(self, prop, value):
        if prop == "label":
            self.label.setText(value)
        else:
            print("qtwidgets.StateBox set_property() only implemented for "
                  "label", file=sys.stderr)
