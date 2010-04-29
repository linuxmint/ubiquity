# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
# «LabelledEntry» - GtkEntry with an interior label.
#
# Copyright (C) 2010 Canonical Ltd.
#
# Authors:
#
# - Evan Dandrea <evand@ubuntu.com>
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

import gtk, gobject
class LabelledEntry(gtk.Entry):
    __gtype_name__ = 'LabelledEntry'
    def __init__(self, inactive_message=''):
        gtk.Entry.__init__(self)
        self.inactive_message = inactive_message
        self.inactive_color = self.style.fg[gtk.STATE_INSENSITIVE]

    def set_inactive_message(self, message):
        self.inactive_message = message or ''

    def do_expose_event(self, event):
        gtk.Entry.do_expose_event(self, event)
        # Get the text_area.
        win = self.window.get_children()[0]
        if self.get_text() or self.is_focus():
            return
        gc = win.new_gc()
        layout = self.create_pango_layout('')
        # XXX don't use self.inactive_color for now as it's too dark.
        layout.set_markup('<span foreground="%s">%s</span>' %
            ('#b8b1a8', self.inactive_message))
        win.draw_layout(gc, 1, 1, layout)

gobject.type_register(LabelledEntry)
