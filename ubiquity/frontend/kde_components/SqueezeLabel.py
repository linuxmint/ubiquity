# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore

#idea from
#http://trac.transmissionbt.com/browser/trunk/qt/squeezelabel.cc
class SqueezeLabel(QtGui.QLabel):
    def __init__(self, parent = None):
        QtGui.QLabel.__init__(self, parent)

    def paintEvent(self, pe):
        fm = self.fontMetrics()
        if fm.width(self.text()) > self.contentsRect().width():
            oldText = self.text()
            elided = fm.elidedText(oldText, QtCore.Qt.ElideRight, self.width())
            self.setText(elided)
            self.setToolTip(oldText)
            QtGui.QLabel.paintEvent(self, pe)
            self.setText(oldText)
        else:
            QtGui.QLabel.paintEvent(self, pe)
