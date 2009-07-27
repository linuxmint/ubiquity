# Original authors:
#   Alex Graveley
#   Christian Hammond <chipx86@chipx86.com>
#   Philip Langdale
#   Régis Duchesne
#
# Translated to Python by:
#   Evan Dandrea <evand@ubuntu.com>
#
# Copyright (C) 2005 VMware, Inc.
# Copyright (C) 2009 Canonical Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import gobject
import pygtk
import gtk
import pango

class WrapLabel(gtk.Label):
    __gtype_name__ = 'WrapLabel'
    def __init__(self, text = ''):
        gtk.Label.__init__(self)
        self.m_wrap_width = 0

        self.get_layout().set_wrap(pango.WRAP_WORD_CHAR)
        self.set_alignment(0.0, 0.0)
        self.set_markup(text)
        self.connect('size-request', self.on_size_request)
        self.connect('size-allocate', self.on_size_allocate)

    def set_text(self, text):
        gtk.Label.set_text(self, text)
        self.set_wrap_width(self.m_wrap_width)

    def set_markup(self, text):
        gtk.Label.set_markup(self, text)
        self.set_wrap_width(self.m_wrap_width)

    def on_size_request(self, widget, requisition):
        width, height = self.get_layout().get_pixel_size()
        requisition.width = 0
        requisition.height = height

    def on_size_allocate(self, widget, allocation):
        gtk.Label.size_allocate(self, allocation)
        self.set_wrap_width(allocation.width)

    def set_wrap_width(self, width):
        if width == 0:
            return

        self.get_layout().set_width(width * pango.SCALE)
        if self.m_wrap_width != width:
            self.m_wrap_width = width
            self.queue_resize()

gobject.type_register(WrapLabel)

if __name__ == '__main__':
    w = gtk.Window(gtk.WINDOW_TOPLEVEL)
    l = WrapLabel("This is a very long label that should span many lines. "
        "It's a good example of what the WrapLabel can do, and "
        "includes formatting, like <b>bold</b>, <i>italic</i>, "
        "and <u>underline</u>. The window can be wrapped to any "
        "width, unlike the standard Gtk::Label, which is set to "
        "a certain wrap width.")
    w.add(l)
    w.show_all()
    gtk.main()
