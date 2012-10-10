#!/usr/bin/python3

import os
import sys

os.environ['GI_TYPELIB_PATH'] = './'
from gi.repository import UbiquityWebcam, Gst, Gtk

Gst.init(sys.argv)
w = Gtk.Window()
webcam = UbiquityWebcam.Webcam()
w.add(webcam)
w.show_all()
webcam.test()
w.connect('destroy', Gtk.main_quit)
Gtk.main()
