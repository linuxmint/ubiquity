import gtk, gobject
from ubiquity.keyboard_detector import *

class Keyrow(gtk.HBox):
    def __init__(self):
        gtk.HBox.__init__(self, spacing=24)

    def add_character(self, key):
        l = gtk.Label('<big>%s</big>' % key)
        l.set_use_markup(True)
        self.add(l)
        l.show()

    def clear(self):
        for ch in self.get_children():
            self.remove(ch)

class KeyboardQuery(gtk.Window):
    __gtype_name__ = 'KeyboardQuery'
    __gsignals__ = { 'layout_result' : (gobject.SIGNAL_RUN_FIRST,
                    gobject.TYPE_NONE, (gobject.TYPE_STRING,)) }
    def __init__(self, frontend):
        gtk.Window.__init__(self)

        self.set_title(
            frontend.get_string('ubiquity/text/keyboard_query_title'))
        self.set_keep_above(True)
        self.set_modal(True)
        self.set_border_width(20)
        self.set_property('allow_grow', False)
        # TODO if we can allocate the space we'll need ahead of time, we can
        # use center_on_parent here.
        self.set_position(gtk.WIN_POS_CENTER_ALWAYS)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.vbox = gtk.VBox(spacing=10)

        self.press_string = \
            frontend.get_string('ubiquity/text/keyboard_query_press')
        self.present_string = \
            frontend.get_string('ubiquity/text/keyboard_query_present')
        self.heading = gtk.Label(self.press_string)
        self.heading.set_alignment(0, 0.5)
        self.vbox.pack_start(self.heading, expand=False)

        self.keyrow = Keyrow()
        self.vbox.pack_start(self.keyrow, expand=False)

        self.buttons = gtk.HButtonBox()
        self.buttons.set_spacing(12)
        self.buttons.set_layout(gtk.BUTTONBOX_START)
        # FIXME evand 2009-12-16: i18n
        no = gtk.Button(stock=gtk.STOCK_NO)
        yes = gtk.Button(stock=gtk.STOCK_YES)
        self.buttons.add(no)
        self.buttons.add(yes)
        self.vbox.add(self.buttons)

        self.add(self.vbox)

        yes.connect('clicked', self.have_key)
        no.connect('clicked', self.no_have_key)
        self.connect('key_press_event', self.key_press_event)

        self.keyboard_detect = KeyboardDetector()
        self.buttons.hide()

    def run(self, *args):
        self.show_all()
        r = self.keyboard_detect.read_step(0)
        self.process(r)

    def process(self, r):
        self.keyrow.clear()
        for k in self.keyboard_detect.symbols:
            self.keyrow.add_character(k)
        if r == KeyboardDetector.PRESS_KEY:
            self.heading.set_label(self.press_string)
            self.buttons.hide()
        elif (r == KeyboardDetector.KEY_PRESENT or
              r == KeyboardDetector.KEY_PRESENT_P):
            self.heading.set_label(self.present_string)
            self.buttons.show()
        elif r == KeyboardDetector.RESULT:
            self.emit('layout_result', self.keyboard_detect.result)
            self.hide()
        else:
            raise Exception, 'should not have got here'

    def have_key(self, *args):
        try:
            r = self.keyboard_detect.read_step(self.keyboard_detect.present)
            self.process(r)
        except:
            self.hide()

    def no_have_key(self, *args):
        try:
            r = self.keyboard_detect.read_step(self.keyboard_detect.not_present)
            self.process(r)
        except:
            self.hide()

    def key_press_event(self, widget, event):
        # FIXME need to account for possible remapping.  Find the API to translate
        # kernel keycodes to X keycodes (xkb).
        # MIN_KEYCODE = 8

        # FIXME escape should close the window.

        code = event.hardware_keycode - 8
        if code > 255:
            return
        if code in self.keyboard_detect.keycodes:
            # XKB doesn't support keycodes > 255.
            c = self.keyboard_detect.keycodes[code]
            try:
                r = self.keyboard_detect.read_step(c)
                self.process(r)
            except:
                self.hide()

gobject.type_register(KeyboardQuery)
