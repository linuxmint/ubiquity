#!/usr/bin/python

from gi.repository import Gtk, Gdk, GObject, Pango
from gi.repository import UbiquityWebcam, GdkPixbuf
from ubiquity import misc
import cairo, os

def draw_round_rect(c, r, x, y, w, h):
    c.move_to(x+r,y)
    c.line_to(x+w-r,y);   c.curve_to(x+w,y,x+w,y,x+w,y+r)
    c.line_to(x+w,y+h-r); c.curve_to(x+w,y+h,x+w,y+h,x+w-r,y+h)
    c.line_to(x+r,y+h);   c.curve_to(x,y+h,x,y+h,x,y+h-r)
    c.line_to(x,y+r);     c.curve_to(x,y,x,y,x+r,y)
    c.close_path()

def gtk_to_cairo_color(c):
    color = Gdk.color_parse(c)
    s = 1.0/65535.0
    r = color.red * s
    g = color.green * s
    b = color.blue * s
    return r, g, b

class StylizedFrame(Gtk.Alignment):
    __gtype_name__ = 'StylizedFrame'
    __gproperties__ = {
        'radius': (GObject.TYPE_INT, 'Radius',
                   'The radius of the rounded corners.', 0,
                   GObject.constants.G_MAXINT, 10, GObject.PARAM_READWRITE),
        'width' : (GObject.TYPE_INT, 'Width', 'The width of the outline.',
                   0, GObject.constants.G_MAXINT, 1,
                   GObject.PARAM_READWRITE),
    }
    
    def __init__(self):
        Gtk.Alignment.__init__(self)
        self.radius = 10
        self.width = 1

    def do_get_property(self, prop):
        if prop.name in ('radius', 'width'):
            return getattr(self, prop.name)
        else:
            return Gtk.Alignment.do_get_property(self, prop)

    def do_set_property(self, prop, value):
        if prop.name in ('radius', 'width'):
            setattr(self, prop.name, value)
            self.queue_draw()
        else:
            Gtk.Alignment.do_set_property(self, prop, value)

    def paint_background(self, c):
        c.set_source_rgb(*gtk_to_cairo_color('#fbfbfb'))
        alloc = self.get_allocation()
        draw_round_rect(c, self.radius,
                        self.width / 2, self.width / 2,
                        alloc.width - self.width,
                        alloc.height - self.width)
        c.fill_preserve()

    def do_draw(self, c):
        # Background
        self.paint_background(c)
        # Edge
        c.set_source_rgb(*gtk_to_cairo_color('#c7c7c6'))
        c.set_line_width(self.width)
        c.stroke()
        if self.get_child():
            top, bottom, left, right = self.get_padding()
            c.translate(left, top)
            self.get_child().draw(c)

GObject.type_register(StylizedFrame)

class ResizeWidget(Gtk.HPaned):
    __gtype_name__ = 'ResizeWidget'
    __gproperties__ = {
        'part_size' : (GObject.TYPE_UINT64, 'Partition size',
                       'The size of the partition being resized', 1,
                       GObject.constants.G_MAXUINT64, 100,
                       GObject.PARAM_READWRITE),
        'min_size'  : (GObject.TYPE_UINT64, 'Minimum size',
                       'The minimum size that the existing partition can ' \
                       'be resized to', 0, GObject.constants.G_MAXUINT64, 0,
                       GObject.PARAM_READWRITE),
        'max_size'  : (GObject.TYPE_UINT64, 'Maximum size',
                       'The maximum size that the existing partition can ' \
                       'be resized to', 1, GObject.constants.G_MAXUINT64,
                       100, GObject.PARAM_READWRITE)
    }
    
    def do_get_property(self, prop):
        return getattr(self, prop.name.replace('-', '_'))

    def do_set_property(self, prop, value):
        setattr(self, prop.name.replace('-', '_'), value)

    def __init__(self, part_size=100, min_size=0, max_size=100,
                 existing_part=None, new_part=None):
        Gtk.HPaned.__init__(self)
        assert min_size <= max_size <= part_size
        assert part_size > 0
        # The size (b) of the existing partition.
        self.part_size = part_size
        # The min size (b) that the existing partition can be resized to.
        self.min_size = min_size
        # The max size (b) that the existing partition can be resized to.
        self.max_size = max_size

        # FIXME: Why do we still need these event boxes to get proper bounds
        # for the linear gradient?
        self.existing_part = existing_part or PartitionBox()
        eb = Gtk.EventBox()
        eb.add(self.existing_part)
        self.pack1(eb, resize=False, shrink=False)
        self.new_part = new_part or PartitionBox()
        eb = Gtk.EventBox()
        eb.add(self.new_part)
        self.pack2(eb, resize=False, shrink=False)
        self.show_all()
        # FIXME hideous, but do_realize fails inexplicably.
        self.connect('realize', self.realize)

    def realize(self, w):
        # TEST: Make sure the value of the minimum size and maximum size
        # equal the value of the widget when pushed to the min/max.
        total = (self.new_part.get_allocation().width +
                 self.existing_part.get_allocation().width)
        tmp = float(self.min_size) / self.part_size
        pixels = int(tmp * total)
        self.existing_part.set_size_request(pixels, -1)

        tmp = ((float(self.part_size) - self.max_size) / self.part_size)
        pixels = int(tmp * total)
        self.new_part.set_size_request(pixels, -1)

    def do_draw(self, cr):
        s1 = self.existing_part.get_allocation().width
        s2 = self.new_part.get_allocation().width
        total = s1 + s2

        percent = (float(s1) / float(total))
        self.existing_part.set_size(percent * self.part_size)
        percent = (float(s2) / float(total))
        self.new_part.set_size(percent * self.part_size)

    def set_pref_size(self, size):
        s1 = self.existing_part.get_allocation().width
        s2 = self.new_part.get_allocation().width
        total = s1 + s2

        percent = (float(size) / float(self.part_size))
        val = percent * total
        self.set_position(int(val))

    def get_size(self):
        '''Returns the size of the old partition,
           clipped to the minimum and maximum sizes.
        '''
        s1 = self.existing_part.get_allocation().width
        s2 = self.new_part.get_allocation().width
        totalwidth = s1 + s2
        size = int(float(s1) * self.part_size / float(totalwidth))
        if size < self.min_size:
            return self.min_size
        elif size > self.max_size:
            return self.max_size
        else:
            return size


GObject.type_register(ResizeWidget)

class DiskBox(Gtk.HBox):
    __gtype_name__ = 'DiskBox'

    def add(self, partition, size):
        Gtk.HBox.add(self, partition, expand=False)
        partition.set_size_request(size, -1)

    def clear(self):
        self.forall(lambda x: self.remove(x))

GObject.type_register(DiskBox)

class PartitionBox(StylizedFrame):
    __gtype_name__ = 'PartitionBox'
    __gproperties__ = {
        'title'     : (GObject.TYPE_STRING, 'Title', None, 'Title',
                       GObject.PARAM_READWRITE),
        'icon-name' : (GObject.TYPE_STRING, 'Icon Name', None,
                       'distributor-logo', GObject.PARAM_READWRITE),
        'extra'     : (GObject.TYPE_STRING, 'Extra Text', None, '',
                       GObject.PARAM_READWRITE),
    }
    
    def do_get_property(self, prop):
        if prop.name == 'title':
            return self.ostitle.get_text()
        elif prop.name == 'icon-name':
            return self.logo.get_icon_name()
        elif prop.name == 'extra':
            return self.extra.get_text()
        return getattr(self, prop.name)

    def do_set_property(self, prop, value):
        if prop.name == 'title':
            self.ostitle.set_markup('<b>%s</b>' % value)
            return
        elif prop.name == 'icon-name':
            self.logo.set_from_icon_name(value, Gtk.IconSize.DIALOG)
            return
        elif prop.name == 'extra':
            self.extra.set_markup('<small>%s</small>' %
                                  (value and value or ' '))
            return
        setattr(self, prop.name, value)

    def __init__(self, title='', extra='', icon_name='distributor-logo'):
        # 10 px above the topmost element
        # 6 px between the icon and the title
        # 4 px between the title and the extra heading
        # 5 px between the extra heading and the size
        # 12 px below the bottom-most element
        StylizedFrame.__init__(self)
        vbox = Gtk.VBox()
        self.logo = Gtk.Image.new_from_icon_name(icon_name,
                                                 Gtk.IconSize.DIALOG)
        align = Gtk.Alignment.new(0.5, 0.5, 0.5, 0.5)
        align.set_padding(10, 0, 0, 0)
        align.add(self.logo)
        vbox.pack_start(align, False, True, 0)

        self.ostitle = Gtk.Label()
        self.ostitle.set_ellipsize(Pango.EllipsizeMode.END)
        align = Gtk.Alignment.new(0.5, 0.5, 0.5, 0.5)
        align.set_padding(6, 0, 0, 0)
        align.add(self.ostitle)
        vbox.pack_start(align, False, True, 0)

        self.extra = Gtk.Label()
        self.extra.set_ellipsize(Pango.EllipsizeMode.END)
        align = Gtk.Alignment.new(0.5, 0.5, 0.5, 0.5)
        align.set_padding(4, 0, 0, 0)
        align.add(self.extra)
        vbox.pack_start(align, False, True, 0)

        self.size = Gtk.Label()
        self.size.set_ellipsize(Pango.EllipsizeMode.END)
        align = Gtk.Alignment.new(0.5, 0.5, 0.5, 0.5)
        align.set_padding(5, 12, 0, 0)
        align.add(self.size)
        vbox.pack_start(align, False, True, 0)
        self.add(vbox)

        self.ostitle.set_markup('<b>%s</b>' % title)
        # Take up the space that would otherwise be used to create symmetry.
        self.extra.set_markup('<small>%s</small>' % extra and extra or ' ')
        self.show_all()

    def set_size(self, size):
        size = misc.format_size(size)
        self.size.set_markup('<span size="x-large">%s</span>' % size)

    def render_dots(self):
        # FIXME: Dots are rendered over the frame.
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2, 2)
        cr = cairo.Context(s)
        cr.set_source_rgb(*gtk_to_cairo_color('#b6b0a9'))
        cr.rectangle(1, 1, 1, 1)
        cr.fill()
        pattern = cairo.SurfacePattern(s)
        return pattern

    def paint_background(self, c):
        StylizedFrame.paint_background(self, c)
        a = self.get_allocation()
        pattern = self.render_dots()
        pattern.set_extend(cairo.EXTEND_REPEAT)
        c.set_source(pattern)
        c.fill_preserve()

        g = cairo.RadialGradient(a.width / 2, a.height / 2, 0, a.width / 2,
                                 a.height / 2,
                                 a.width > a.height and a.width or a.height)
        g.add_color_stop_rgba(0.00, 1, 1, 1, 1.00)
        g.add_color_stop_rgba(0.25, 1, 1, 1, 0.75)
        g.add_color_stop_rgba(0.40, 1, 1, 1, 0.00)
        c.set_source(g)
        c.fill_preserve()

GObject.type_register(PartitionBox)

class StateBox(StylizedFrame):
    __gtype_name__ = 'StateBox'
    __gproperties__ = {
        'label'  : (GObject.TYPE_STRING, 'Label', None, 'label',
                    GObject.PARAM_READWRITE),
    }
    
    def do_get_property(self, prop):
        if prop.name == 'label':
            return self.label.get_text()
        return getattr(self, prop.name)

    def do_set_property(self, prop, value):
        if prop.name == 'label':
            self.label.set_text(value)
            return
        setattr(self, prop.name, value)
    
    def __init__(self, text=''):
        StylizedFrame.__init__(self)
        alignment = Gtk.Alignment()
        alignment.set_padding(7, 7, 15, 15)
        hbox = Gtk.HBox()
        hbox.set_spacing(10)
        self.image = Gtk.Image()
        self.image.set_from_stock(Gtk.STOCK_YES, Gtk.IconSize.LARGE_TOOLBAR)
        self.label = Gtk.Label(label=text)
        
        self.label.set_alignment(0, 0.5)
        hbox.pack_start(self.image, False, True, 0)
        hbox.pack_start(self.label, True, True, 0)
        alignment.add(hbox)
        self.add(alignment)
        self.show_all()

        self.status = True

    def set_state(self, state):
        self.status = state
        if state:
            self.image.set_from_stock(Gtk.STOCK_YES,
                                      Gtk.IconSize.LARGE_TOOLBAR)
        else:
            self.image.set_from_stock(Gtk.STOCK_NO,
                                      Gtk.IconSize.LARGE_TOOLBAR)

    def get_state(self):
        return self.status

GObject.type_register(StateBox)

FACES_PATH = '/usr/share/pixmaps/faces'

class FaceSelector(Gtk.VBox):
    __gtype_name__ = 'FaceSelector'
    def __init__(self):
        Gtk.VBox.__init__(self)
        self.set_spacing(12)

        vb_left = Gtk.VBox.new(False, 3)
        # TODO i18n
        l = Gtk.Label('Take a photo:')
        vb_left.pack_start(l, False, False, 0)
        f = Gtk.Frame()
        self.webcam = UbiquityWebcam.Webcam()
        self.webcam.connect('image-captured', self.image_captured)
        f.add(self.webcam)
        vb_left.add(f)

        vb_right = Gtk.VBox.new(False, 3)
        # TODO i18n
        l = Gtk.Label('Or choose an existing picture:')
        vb_right.pack_start(l, False, False, 0)
        iv = Gtk.IconView()
        iv.connect('selection-changed', self.selection_changed)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(iv)
        vb_right.add(sw)

        hb = Gtk.HBox.new(True, 30)
        hb.add(vb_left)
        hb.add(vb_right)
        self.add(hb)

        self.selected_image = Gtk.Image()
        self.selected_image.set_size_request(96, 96)
        self.add(self.selected_image)

        m = Gtk.ListStore(GObject.type_from_name('GdkPixbuf'))
        iv.set_model(m)
        iv.set_pixbuf_column(0)
        if os.path.exists(FACES_PATH):
            for path in os.listdir(FACES_PATH):
                pb = GdkPixbuf.Pixbuf.new_from_file(
                                    os.path.join(FACES_PATH, path))
                m.append([pb])

    def webcam_play(self):
        self.webcam.play()

    def webcam_stop(self):
        self.webcam.stop()

    def save_to(self, path):
        pb = self.selected_image.get_pixbuf()
        if not pb:
            return False

        d = os.path.dirname(path)
        with misc.raised_privileges():
            if not os.path.exists(d):
                os.makedirs(d)
            pb.savev(path, 'png', [], [])

    def image_captured(self, unused, path):
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, 96, 96);
        self.selected_image.set_from_pixbuf(pb)

    def selection_changed(self, iv):
        selection = iv.get_selected_items()
        if not selection:
            return
        selection = selection[0]
        m = iv.get_model()
        self.selected_image.set_from_pixbuf(m[selection][0])

GObject.type_register(FaceSelector)

