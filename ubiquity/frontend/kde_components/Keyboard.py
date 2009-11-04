# -*- coding: utf-8 -*-

import subprocess
import re
import PyQt4
import os

from PyQt4 import QtCore
from PyQt4 import uic
from PyQt4.QtCore import Qt
from PyQt4.QtGui import *

uidir = "/usr/share/ubiquity/qt/"

class Keyboard(QWidget):
    def __init__(self, parent = None):
        QWidget.__init__(self, parent)
        
        self.regularCodes = []
        self.shiftCodes = []
        self.layout = None
        self.variant = None
        self.showShift = False
        
        #load the ui
        uic.loadUi(os.path.join(uidir, "keyboard.ui"), self)
        
        self.keys = []
        for row in self.children():
            for key in row.children():
                if type(key) == QPushButton:
                    index = "0%s" % key.objectName()
                    if "0x00" in index:
                        continue
                    self.keys.append((key, int(index, 16)))
                    
        self.x36.pressed.connect(self.shiftOn)
        self.x2a.pressed.connect(self.shiftOn)
        self.x36.released.connect(self.shiftOff)
        self.x2a.released.connect(self.shiftOff)
        
    def shiftOn(self):
        self.showShift = True
        self.redrawKeys()
        
    def shiftOff(self):
        self.showShift = False
        self.redrawKeys()
            
    def redrawKeys(self):
        source = self.regular_text
        if self.showShift:
            source = self.shift_text
            
        for k in self.keys:
            k[0].setText(source(k[1]).replace("&", "&&"))
        
        
    def setLayout(self, layout):
        self.layout = layout
        
    def setVariant(self, variant):
        self.variant = variant
        self.loadCodes()
        
        self.redrawKeys()
                    
    #given a keyboard index? scancode?
    #return the unicode character
    def regular_text(self, index):
        
        if index == 0xe: #backspace
            return "<"
        elif index == 0x2a or index == 0x36:
            return "Shift"
        elif index == 0x1c:
            return "Enter"
        elif index == 0x1d:
            return "Ctrl"
        elif index == 0xf:
            return "Tab"
        elif index == 0x3a:
            return "Caps"
        elif index == 0x38:
            return "Alt"

        full = self.regularCodes[index]
        code = full
        
        if (0xf000 & full):
            type = (full >> 8) & 0xff
            code = full & 0xff
            
        return unichr(code)
        
    def shift_text(self, index):
        
        if index == 0xe: #backspace
            return "<"
        elif index == 0x2a or index == 0x36:
            return "Shift"
        elif index == 0x1c:
            return "Enter"
        elif index == 0x1d:
            return "Ctrl"
        elif index == 0xf:
            return "Tab"
        elif index == 0x3a:
            return "Caps"
        elif index == 0x38:
            return "Alt"

        full = self.shiftCodes[index]
        code = full
        
        if (0xf000 & full):
            type = (full >> 8) & 0xff
            code = full & 0xff
            
        return unichr(code)
        
    def printCodes(self):
        counter=1
        for c in self.regularCodes:
            if counter % 9 == 0:
                counter = 1
                print ""
            
            print "0x%x" % c,
            counter += 1
        
    def loadCodes(self):
        if self.layout is None:
            return
            
        variantParam = ""
        
        if self.variant:
            variantParam = "-variant %s" % self.variant;
            
        cmd="ckbcomp -model pc105 -layout %s %s" % (self.layout, variantParam)
        print cmd
        cmd2="loadkeys -mu"
        
        #setup pipe between the two programs
        pipe = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        pipe2 = subprocess.Popen(cmd2, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        ret = pipe2.communicate(pipe.communicate()[0])

        cfile = ret[0]
        
        #clear the current codes
        del self.regularCodes[:]
        del self.shiftCodes[:]

        inNormal = False;
        inShift = False;
        lines = cfile.split('\n')
        for l in lines:
            if inNormal and "}" in l:
                inNormal = False;
            
            if inShift and "}" in l:
                inShift = False;
                break
            
            if inNormal or inShift:
                for code in l.split(','):
                    if len(code) > 0:
                        if inNormal:
                            self.regularCodes.append(int(code.strip(), 16))
                        else:
                            self.shiftCodes.append(int(code.strip(), 16))
            
            if "u_short plain_map[NR_KEYS] = {" in l:
                inNormal = True;
                
            if "static u_short shift_map[NR_KEYS] = {" in l:
                inShift = True;
                