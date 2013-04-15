from __future__ import print_function

import sys

from PyQt4.QtGui import QWidget, QHBoxLayout, QLabel, QPixmap


class StateBox(QWidget):
    def __init__(self, parent, text=''):
        QWidget.__init__(self, parent)

        self.label = QLabel(text, self)
        self.image = QLabel(self)

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
            name = "dialog-ok-apply.png"
        else:
            # A cross
            name = "edit-delete.png"
        name = "/usr/share/icons/oxygen/22x22/actions/" + name
        self.image.setPixmap(QPixmap(name))

    def get_state(self):
        return self.status

    def set_property(self, prop, value):
        if prop == "label":
            self.label.setText(value)
        else:
            print("qtwidgets.StateBox set_property() only implemented for "
                  "label", file=sys.stderr)
