# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

class ProgressDialog(QDialog):
    def __init__(self, min, max, parent = None):
        QDialog.__init__(self, parent)
        
        self.progressBar = QProgressBar(self)
        self.progressBar.setMinimum(min)
        self.setMaximum(max)
        
        self.cancelButton = QPushButton()
        self.cancelButton.clicked.connect(self.reject)
        
        self.extraFrame = QFrame()
        self.extraFrame.setFrameStyle(QFrame.StyledPanel)
        self.extraFrame.setFrameShadow(QFrame.Sunken)
        self.extraFrame.setLayout(QVBoxLayout())
        self.extraFrame.layout().setContentsMargins(0,0,0,0)
        self.extraFrame.setVisible(False)
        
        self.progressLabel = QLabel(self)
        
        self.setLayout(QVBoxLayout())
        
        self.layout().addWidget(self.progressLabel)
        self.layout().addWidget(self.progressBar)
        self.layout().addWidget(self.extraFrame)
        self.layout().addWidget(self.cancelButton)
        
        self.reset()
        
        self.rejected.connect(self.rejectedSlot)
        
    def rejectedSlot(self):
        self.cancelFlag = True
        
    def reset(self):
        self.cancelFlag = False
        self.progressLabel.setText("")
        self.progressBar.setValue(0)
        self.setVisible(False)
        
    def wasCanceled(self):
        return self.cancelFlag
        
    def setCancelText(self, string):
        self.cancelButton.setText(string)
        
    def setCancellable(self, val):
        self.cancelButton.setVisible(val)
        
    def setMaximum(self, val):
        self.progressBar.setMaximum(val)
    
    def setProgressLabel(self, string):
        self.progressLabel.setText(string)
    
    def setProgressValue(self, val):
        self.progressBar.setValue(val)
    
    def maximum(self):
        return self.progressBar.maximum()
        
    