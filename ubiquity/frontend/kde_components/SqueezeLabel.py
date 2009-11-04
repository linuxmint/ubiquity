# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

#idea from
#http://trac.transmissionbt.com/browser/trunk/qt/squeezelabel.cc
class SqueezeLabel(QLabel):
    def __init__(self, parent = None):
        QLabel.__init__(self, parent)
        
    def paintEvent(self, pe):
        fm = self.fontMetrics()
        if fm.width(self.text()) > self.contentsRect().width():
            oldText = self.text()
            elided = fm.elidedText(oldText, Qt.ElideRight, self.width())
            self.setText(elided)
            self.setToolTip(oldText)
            QLabel.paintEvent(self, pe)
            self.setText(oldText)
        else:
            QLabel.paintEvent(self, pe)