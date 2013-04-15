from gi.repository import Gtk, GObject, Gdk

from ubiquity import keyboard_detector


class Keyrow(Gtk.Box):
    def __init__(self):
        GObject.GObject.__init__(self, spacing=24)

    def add_character(self, key):
        l = Gtk.Label(label='<big>%s</big>' % key)
        l.set_use_markup(True)
        self.pack_start(l, True, True, 0)
        l.show()

    def clear(self):
        for ch in self.get_children():
            self.remove(ch)


class KeyboardQuery(Gtk.Window):
    __gtype_name__ = 'KeyboardQuery'
    __gsignals__ = {
        'layout_result': (
            GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, frontend):
        Gtk.Window.__init__(self)

        self.set_title(
            frontend.get_string('ubiquity/text/keyboard_query_title'))
        self.set_keep_above(True)
        self.set_modal(True)
        self.set_border_width(20)
        self.set_property('resizable', False)
        # TODO if we can allocate the space we'll need ahead of time, we can
        # use center_on_parent here.
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.vbox = Gtk.Box(spacing=10)
        self.vbox.set_orientation(Gtk.Orientation.VERTICAL)

        self.press_string = \
            frontend.get_string('ubiquity/text/keyboard_query_press')
        self.present_string = \
            frontend.get_string('ubiquity/text/keyboard_query_present')
        self.heading = Gtk.Label(label=self.press_string)
        self.heading.set_alignment(0, 0.5)
        self.vbox.pack_start(self.heading, False, True, 0)

        self.keyrow = Keyrow()
        self.vbox.pack_start(self.keyrow, False, True, 0)

        self.buttons = Gtk.ButtonBox()
        self.buttons.set_spacing(12)
        self.buttons.set_layout(Gtk.ButtonBoxStyle.START)
        # FIXME evand 2009-12-16: i18n
        no = Gtk.Button(stock=Gtk.STOCK_NO)
        yes = Gtk.Button(stock=Gtk.STOCK_YES)
        self.buttons.add(no)
        self.buttons.add(yes)
        self.vbox.add(self.buttons)

        self.add(self.vbox)

        yes.connect('clicked', self.have_key)
        no.connect('clicked', self.no_have_key)
        self.connect('key_press_event', self.key_press_event)

        self.keyboard_detect = keyboard_detector.KeyboardDetector()
        self.buttons.hide()

    def run(self, *args):
        self.show_all()
        r = self.keyboard_detect.read_step(0)
        self.process(r)

    def process(self, r):
        self.keyrow.clear()
        for k in self.keyboard_detect.symbols:
            self.keyrow.add_character(k)
        if r == keyboard_detector.KeyboardDetector.PRESS_KEY:
            self.heading.set_label(self.press_string)
            self.buttons.hide()
        elif (r == keyboard_detector.KeyboardDetector.KEY_PRESENT or
              r == keyboard_detector.KeyboardDetector.KEY_PRESENT_P):
            self.heading.set_label(self.present_string)
            self.buttons.show()
        elif r == keyboard_detector.KeyboardDetector.RESULT:
            self.emit('layout_result', self.keyboard_detect.result)
            self.hide()
        else:
            raise Exception('should not have got here')

    def have_key(self, *args):
        try:
            r = self.keyboard_detect.read_step(self.keyboard_detect.present)
            self.process(r)
        except:
            self.hide()

    def no_have_key(self, *args):
        try:
            r = self.keyboard_detect.read_step(
                self.keyboard_detect.not_present)
            self.process(r)
        except:
            self.hide()

    def key_press_event(self, widget, event):
        # FIXME need to account for possible remapping.  Find the API to
        # translate kernel keycodes to X keycodes (xkb).
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

GObject.type_register(KeyboardQuery)
