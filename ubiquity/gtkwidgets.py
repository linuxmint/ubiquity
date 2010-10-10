#!/usr/bin/python

import gtk
import gobject
import cairo
import pango

import dbus
import glib

from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

def auto_shrink(widget):
    widget.resize(*widget.size_request())

def format_size(size):
    """Format a partition size."""
    if size < 1000:
        unit = 'B'
        factor = 1
    elif size < 1000 * 1000:
        unit = 'kB'
        factor = 1000
    elif size < 1000 * 1000 * 1000:
        unit = 'MB'
        factor = 1000 * 1000
    elif size < 1000 * 1000 * 1000 * 1000:
        unit = 'GB'
        factor = 1000 * 1000 * 1000
    else:
        unit = 'TB'
        factor = 1000 * 1000 * 1000 * 1000
    return '%.1f %s' % (float(size) / factor, unit)

def draw_round_rect(c, r, x, y, w, h):
    c.move_to(x+r,y)
    c.line_to(x+w-r,y);   c.curve_to(x+w,y,x+w,y,x+w,y+r)
    c.line_to(x+w,y+h-r); c.curve_to(x+w,y+h,x+w,y+h,x+w-r,y+h)
    c.line_to(x+r,y+h);   c.curve_to(x,y+h,x,y+h,x,y+h-r)
    c.line_to(x,y+r);     c.curve_to(x,y,x,y,x+r,y)
    c.close_path()

def gtk_to_cairo_color(c):
    color = gtk.gdk.color_parse(c)
    s = 1.0/65535.0
    r = color.red * s
    g = color.green * s
    b = color.blue * s
    return r, g, b

class StylizedFrame(gtk.Bin):
    __gtype_name__ = 'StylizedFrame'
    __gproperties__ = {
        'radius'  : (gobject.TYPE_INT,
                    'Radius',
                    'The radius of the rounded corners.',
                    0, 32767, 10, gobject.PARAM_READWRITE),
        'width'   : (gobject.TYPE_INT,
                    'Width',
                    'The width of the outline.',
                    0, 32767, 1, gobject.PARAM_READWRITE),
        'padding' : (gobject.TYPE_INT,
                    'Padding',
                    'The padding between the bin and the outline.',
                    0, 32767, 2, gobject.PARAM_READWRITE)
    }
    
    def do_get_property(self, prop):
        return getattr(self, prop.name)

    def do_set_property(self, prop, value):
        setattr(self, prop.name, value)

    def __init__(self):
        gtk.Bin.__init__(self)
        self.child = None
        self.radius = 10
        self.width = 1
        self.padding = 2

    #def do_realize(self):
    #    self.set_flags(gtk.REALIZED)

    #    self.window = gtk.gdk.Window(
    #        self.get_parent_window(),
    #        width=self.allocation.width,
    #        height=self.allocation.height,
    #        window_type=gtk.gdk.WINDOW_CHILD,
    #        wclass=gtk.gdk.INPUT_OUTPUT,
    #        event_mask=self.get_events() | gtk.gdk.EXPOSURE_MASK)

    #    self.window.set_user_data(self)
    #    self.style.attach(self.window)
    #    self.style.set_background(self.window, gtk.STATE_NORMAL)
    #    self.window.move_resize(*self.allocation)
    #    gtk.Bin.do_realize(self)

    def do_size_request(self, req):
        w, h = 1, 1
        if self.child:
            w, h = self.child.size_request()
        req.width = w + (self.width * 2) + (self.padding * 2)
        req.height = h + (self.width * 2) + (self.padding * 2)

    def do_size_allocate(self, alloc):
        self.allocation = alloc
        self.child.size_allocate(alloc)

    def do_forall(self, include_internals, callback, user_data):
        if self.child:
            callback (self.child, user_data)

    def paint_background(self, c):
        c.set_source_rgb(*gtk_to_cairo_color('#fbfbfb'))
        draw_round_rect(c, self.radius, self.allocation.x + self.width,
                        self.allocation.y + self.width,
                        self.allocation.width - (self.width * 2),
                        self.allocation.height - (self.width * 2))
        c.fill_preserve()

    def do_expose_event(self, event):
        x, y, w, h = self.allocation
        c = self.window.cairo_create()
        c.rectangle(x, y, w, h)
        c.clip()
        # Background
        self.paint_background(c)
        # Edge
        c.set_source_rgb(*gtk_to_cairo_color('#c7c7c6'))
        c.set_line_width(self.width)
        c.stroke()
        gtk.Bin.do_expose_event(self, event)

gobject.type_register(StylizedFrame)

# c3032
# TODO Glade gets really slow when dealing with uint64 properties.
# Investigate.
class ResizeWidget(gtk.HPaned):
    __gtype_name__ = 'ResizeWidget'
    __gproperties__ = {
        'part_size' : (gobject.TYPE_UINT64,
                    'Partition size',
                    'The size of the partition being resized',
                    1, 2**64-1, 100, gobject.PARAM_READWRITE),
        'min_size'  : (gobject.TYPE_UINT64,
                    'Minimum size',
                    'The minimum size that the existing partition can be '\
                    'resized to',
                    0, 2**64-1, 0, gobject.PARAM_READWRITE),
        'max_size'  : (gobject.TYPE_UINT64,
                    'Maximum size',
                    'The maximum size that the existing partition can be ' \
                    'resized to',
                    1, 2**64-1, 100, gobject.PARAM_READWRITE)
    }
    
    def do_get_property(self, prop):
        return getattr(self, prop.name.replace('-', '_'))

    def do_set_property(self, prop, value):
        setattr(self, prop.name.replace('-', '_'), value)

    # TODO: Should this be automatically composed of an existing_part and
    # new_part, given that it cannot function without them.  This could then be
    # exposed in Glade, so both widgets could be named, and then the ubiquity
    # code would simply have to call set_* functions.  Or, if that doesn't work
    # (because you don't want to be able to delete them), add a get_children()
    # function.  Yes.
    def __init__(self, part_size=100, min_size=0, max_size=100, existing_part=None, new_part=None):
        gtk.HPaned.__init__(self)
        assert min_size <= max_size <= part_size
        assert part_size > 0
        # The size (b) of the existing partition.
        self.part_size = part_size
        # The minimum size (b) that the existing partition can be resized to.
        self.min_size = min_size
        # The maximum size (b) that the existing partition can be resized to.
        self.max_size = max_size

        # FIXME: Why do we still need these event boxes to get proper bounds
        # for the linear gradient?
        self.existing_part = existing_part or PartitionBox()
        eb = gtk.EventBox()
        eb.add(self.existing_part)
        self.pack1(eb, shrink=False)
        self.new_part = new_part or PartitionBox()
        eb = gtk.EventBox()
        eb.add(self.new_part)
        self.pack2(eb, shrink=False)
        self.show_all()

    def do_realize(self):
        # TEST: Make sure the value of the minimum size and maximum size equal
        # the value of the widget when pushed to the min/max.
        total = (self.new_part.get_allocation().width +
                 self.existing_part.get_allocation().width)
        tmp = float(self.min_size) / self.part_size
        pixels = int(tmp * total)
        self.existing_part.set_size_request(pixels, -1)

        tmp = ((float(self.part_size) - self.max_size) / self.part_size)
        pixels = int(tmp * total)
        self.new_part.set_size_request(pixels, -1)

        gtk.HPaned.do_realize(self)

    def do_expose_event(self, event):
        s1 = self.existing_part.get_allocation().width
        s2 = self.new_part.get_allocation().width
        total = s1 + s2

        percent = (float(s1) / float(total))
        self.existing_part.set_size(percent * self.part_size)
        
        percent = (float(s2) / float(total))
        self.new_part.set_size(percent * self.part_size)
        gtk.HPaned.do_expose_event(self, event)

    def set_pref_size(self, size):
        s1 = self.existing_part.get_allocation().width
        s2 = self.new_part.get_allocation().width
        total = s1 + s2

        percent = (float(size) / float(self.part_size))
        val = percent * total
        self.set_position(int(val))

    def get_size(self):
        '''Returns the size of the old partition, clipped to the minimum and
           maximum sizes.'''
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


gobject.type_register(ResizeWidget)

class DiskBox(gtk.HBox):
    __gtype_name__ = 'DiskBox'

    def add(self, partition, size):
        gtk.HBox.add(self, partition, expand=False)
        partition.set_size_request(size, -1)

    def clear(self):
        self.forall(lambda x: self.remove(x))

gobject.type_register(DiskBox)

class PartitionBox(StylizedFrame):
    __gtype_name__ = 'PartitionBox'
    __gproperties__ = {
        'title'  : (gobject.TYPE_STRING,
                    'Title',
                    None,
                    'Title',
                    gobject.PARAM_READWRITE),
        'icon-name' : (gobject.TYPE_STRING,
                    'Icon Name',
                    None,
                    'distributor-logo',
                    gobject.PARAM_READWRITE),
        'extra'  : (gobject.TYPE_STRING,
                    'Extra Text',
                    None,
                    '',
                    gobject.PARAM_READWRITE),
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
            self.logo.set_from_icon_name(value, gtk.ICON_SIZE_DIALOG)
            return
        elif prop.name == 'extra':
            self.extra.set_markup('<small>%s</small>' % (value and value or ' '))
            return
        setattr(self, prop.name, value)

    # TODO: A keyword argument default of a widget seems silly.  Use a string.
    def __init__(self, title='', extra='', icon_name='distributor-logo'):
        # 10 px above the topmost element
        # 6 px between the icon and the title
        # 4 px between the title and the extra heading
        # 5 px between the extra heading and the size
        # 12 px below the bottom-most element
        StylizedFrame.__init__(self)
        vbox = gtk.VBox()
        self.logo = gtk.image_new_from_icon_name(icon_name, gtk.ICON_SIZE_DIALOG)
        align = gtk.Alignment(0.5, 0.5, 0.5, 0.5)
        align.set_padding(10, 0, 0, 0)
        align.add(self.logo)
        vbox.pack_start(align, expand=False)

        self.ostitle = gtk.Label()
        self.ostitle.set_ellipsize(pango.ELLIPSIZE_END)
        align = gtk.Alignment(0.5, 0.5, 0.5, 0.5)
        align.set_padding(6, 0, 0, 0)
        align.add(self.ostitle)
        vbox.pack_start(align, expand=False)

        self.extra = gtk.Label()
        self.extra.set_ellipsize(pango.ELLIPSIZE_END)
        align = gtk.Alignment(0.5, 0.5, 0.5, 0.5)
        align.set_padding(4, 0, 0, 0)
        align.add(self.extra)
        vbox.pack_start(align, expand=False)

        self.size = gtk.Label()
        self.size.set_ellipsize(pango.ELLIPSIZE_END)
        align = gtk.Alignment(0.5, 0.5, 0.5, 0.5)
        align.set_padding(5, 12, 0, 0)
        align.add(self.size)
        vbox.pack_start(align, expand=False)
        self.add(vbox)

        self.ostitle.set_markup('<b>%s</b>' % title)
        #self.set_tooltip_text(title)
        # Take up the space that would otherwise be used to create symmetry.
        self.extra.set_markup('<small>%s</small>' % (extra and extra or ' '))
        self.show_all()

    def set_size(self, size):
        size = format_size(size)
        self.size.set_markup('<span size="x-large">%s</span>' % size)

    def render_dots(self):
        # FIXME: Dots are rendered over the frame.
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2, 2)
        cr = cairo.Context(s)
        cr.set_source_rgb(*gtk_to_cairo_color('#b6b0a9'))
        #cr.set_source_rgb(*gtk_to_cairo_color('black'))
        cr.rectangle(1, 1, 1, 1)
        cr.fill()
        pattern = cairo.SurfacePattern(s)
        return pattern

    def paint_background(self, c):
        StylizedFrame.paint_background(self, c)
        x,y,w,h = self.allocation
        #c.save()
        #c.rectangle(x+10, y+10, w-20, h-20)
        #c.clip_preserve()
        w, h = self.allocation.width, self.allocation.height
        pattern = self.render_dots()
        pattern.set_extend(cairo.EXTEND_REPEAT)
        c.set_source(pattern)
        #c.paint()
        c.fill_preserve()

        g = cairo.RadialGradient(w/2, h/2, 0, w/2, h/2, w > h and w or h)
        g.add_color_stop_rgba(0.00, 1, 1, 1, 1)
        g.add_color_stop_rgba(0.25, 1, 1, 1, 0.75)
        g.add_color_stop_rgba(0.4, 1, 1, 1, 0)
        c.set_source(g)
        #c.paint()
        c.fill_preserve()
        #c.restore()

gobject.type_register(PartitionBox)

class StateBox(StylizedFrame):
    __gtype_name__ = 'StateBox'
    __gproperties__ = {
        'label'  : (gobject.TYPE_STRING,
                    'Label',
                    None,
                    'label', gobject.PARAM_READWRITE),
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
        alignment = gtk.Alignment()
        alignment.set_padding(7, 7, 15, 15)
        hbox = gtk.HBox()
        hbox.set_spacing(10)
        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.label = gtk.Label(text)
        
        self.label.set_alignment(0, 0.5)
        hbox.pack_start(self.image, expand=False)
        hbox.pack_start(self.label)
        alignment.add(hbox)
        self.add(alignment)
        self.show_all()

        self.status = True

    def set_state(self, state):
        self.status = state
        if state:
            self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
        else:
            self.image.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_LARGE_TOOLBAR)

    def get_state(self):
        return self.status

gobject.type_register(StateBox)

# TODO: Doesn't show correctly in Glade.
class LabelledEntry(gtk.Entry):
    __gtype_name__ = 'LabelledEntry'
    __gproperties__ = {
        'label'  : (gobject.TYPE_STRING,
                    'Label',
                    None,
                    'label', gobject.PARAM_READWRITE),
        'persist' : (gobject.TYPE_BOOLEAN,
                     'Persist', 'Show the label even when there is text.',
                     False,
                     gobject.PARAM_READWRITE),
    }

    def do_get_property(self, prop):
        if prop.name == 'label':
            return self.get_label()
        elif prop.name == 'persist':
            return self.get_persist()
        else:
            return getattr(self, prop.name)

    def do_set_property(self, prop, value):
        if prop.name == 'label':
            self.set_label(value)
        elif prop.name == 'persist':
            self.set_persist(value)
        else:
            setattr(self, prop.name, value)

    def __init__(self, label='', persist=False):
        gtk.Entry.__init__(self)
        self.label = label
        self.persist = persist
        self.inactive_color = self.style.fg[gtk.STATE_INSENSITIVE]

    def set_label(self, label):
        self.label = label or ''

    def get_label(self):
        return self.label

    def set_persist(self, persist):
        self.persist = persist

    def get_persist(self):
        return self.persist

    def do_expose_event(self, event):
        gtk.Entry.do_expose_event(self, event)
        # Get the text_area.
        win = self.window.get_children()[0]
        if self.has_focus():
            return
        elif not self.get_persist() and self.get_text():
            return
        gc = win.new_gc()
        layout = self.create_pango_layout('')
        # XXX don't use self.inactive_color for now as it's too dark.
        layout.set_markup('<span foreground="%s">%s</span>' %
            ('#b8b1a8', self.label))
        # FIXME RTL support
        if self.persist:
            w = self.get_layout().get_pixel_size()[0] + 6 # padding
        else:
            w = 1
        win.draw_layout(gc, w, 2, layout)

gobject.type_register(LabelledEntry)

class LabelledComboBoxEntry(gtk.ComboBoxEntry):
    __gtype_name__ = 'LabelledComboBoxEntry'
    __gproperties__ = {
        'label'  : (gobject.TYPE_STRING,
                    'Label',
                    None,
                    'label', gobject.PARAM_READWRITE),
    }

    def do_get_property(self, prop):
        if prop.name == 'label':
            return self.child.get_label()
        return getattr(self, prop.name)

    def do_set_property(self, prop, value):
        if prop.name == 'label':
            self.child.set_label(value)
            return
        setattr(self, prop.name, value)

    def __init__(self, model=None, column=-1):
        #gtk.ComboBoxEntry.__init__(self, model, column)
        gtk.ComboBox.__init__(self)
        l = LabelledEntry()
        l.show()
        self.add(l)
gobject.type_register(LabelledComboBoxEntry)

# Modified from John Stowers' client-side-windows demo.
class GreyableBin(gtk.Bin):
    __gsignals__ = {
        "damage_event"  :   "override"
    }
    __gproperties__ = {
        'greyed'  : (gobject.TYPE_BOOLEAN,
                    'Greyed', 'greyed', False, gobject.PARAM_READWRITE),
    }
    __gtype_name__ = 'GreyableBin'

    def __init__(self):
        gtk.Bin.__init__(self)

        self.child = None
        self.offscreen_window = None
        self.greyed = False

        self.unset_flags(gtk.NO_WINDOW)

    def do_set_property(self, pspec, value):
        setattr(self, pspec.name, value)

    def do_get_property(self, pspec):
        return getattr(self, pspec.name)

    def _to_child(self, widget_x, widget_y):
        return widget_x, widget_y

    def _to_parent(self, offscreen_x, offscreen_y):
        return offscreen_x, offscreen_y

    def _pick_offscreen_child(self, offscreen_window, widget_x, widget_y):
        if self.child and self.child.flags() & gtk.VISIBLE:
            x,y = self._to_child(widget_x, widget_y)
            ca = self.child.allocation
            if (x >= 0 and x < ca.width and y >= 0 and y < ca.height):
                return self.offscreen_window
        return None

    def _offscreen_window_to_parent(self, offscreen_window, offscreen_x, offscreen_y, parent_x, parent_y):
        x,y = self._to_parent(offscreen_x, offscreen_y)
        offscreen_x = parent_x
        offscreen_y = offscreen_x

    def _offscreen_window_from_parent(self, parent_window, parent_x, parent_y, offscreen_x, offscreen_y):
        x,y = self._to_child(parent_x, parent_y)
        offscreen_x = parent_x
        offscreen_y = offscreen_x

    def do_realize(self):
        self.set_flags(gtk.REALIZED)

        border_width = self.border_width

        w = self.allocation.width - 2*border_width
        h = self.allocation.height - 2*border_width

        self.window = gtk.gdk.Window(
                self.get_parent_window(),
                x=self.allocation.x + border_width,
                y=self.allocation.y + border_width,
                width=w,
                height=h,
                window_type=gtk.gdk.WINDOW_CHILD,
                event_mask=self.get_events() 
                        | gtk.gdk.EXPOSURE_MASK
                        | gtk.gdk.POINTER_MOTION_MASK
                        | gtk.gdk.BUTTON_PRESS_MASK
                        | gtk.gdk.BUTTON_RELEASE_MASK
                        | gtk.gdk.SCROLL_MASK
                        | gtk.gdk.ENTER_NOTIFY_MASK
                        | gtk.gdk.LEAVE_NOTIFY_MASK,
                visual=self.get_visual(),
                colormap=self.get_colormap(),
                wclass=gtk.gdk.INPUT_OUTPUT)

        self.window.set_user_data(self)
        self.window.connect("pick-embedded-child", self._pick_offscreen_child)

        if self.child and self.child.flags() & gtk.VISIBLE:
            w = self.child.allocation.width
            h = self.child.allocation.height

        self.offscreen_window = gtk.gdk.Window(
                self.get_root_window(),
                x=self.allocation.x + border_width,
                y=self.allocation.y + border_width,
                width=w,
                height=h,
                window_type=gtk.gdk.WINDOW_OFFSCREEN,
                event_mask=self.get_events() 
                        | gtk.gdk.EXPOSURE_MASK
                        | gtk.gdk.POINTER_MOTION_MASK
                        | gtk.gdk.BUTTON_PRESS_MASK
                        | gtk.gdk.BUTTON_RELEASE_MASK
                        | gtk.gdk.SCROLL_MASK
                        | gtk.gdk.ENTER_NOTIFY_MASK
                        | gtk.gdk.LEAVE_NOTIFY_MASK,
                visual=self.get_visual(),
                colormap=self.get_colormap(),
                wclass=gtk.gdk.INPUT_OUTPUT)
        self.offscreen_window.set_user_data(self)

        if self.child:
            self.child.set_parent_window(self.offscreen_window)

        gtk.gdk.offscreen_window_set_embedder(self.offscreen_window, self.window)

        self.offscreen_window.connect("to-embedder", self._offscreen_window_to_parent)
        self.offscreen_window.connect("from-embedder", self._offscreen_window_from_parent)

        self.style.attach(self.window)
        self.style.set_background(self.window, gtk.STATE_NORMAL)
        self.style.set_background(self.offscreen_window, gtk.STATE_NORMAL)

        self.offscreen_window.show()

    def do_child_type(self):
        #FIXME: This never seems to get called...
        if self.child:
            return None
        return gtk.Widget.__gtype__

    def do_unrealize(self):
        self.offscreen_window.set_user_data(None)
        self.offscreen_window = None

    def do_add(self, widget):
        if not self.child:
            widget.set_parent_window(self.offscreen_window)
            widget.set_parent(self)
            self.child = widget
        else:
            print "Cannot have more than one child"

    def do_remove(self, widget):
        was_visible = widget.flags() & gtk.VISIBLE
        if self.child == widget:
            widget.unparent()
            self.child = None
            if was_visible and (self.flags() & gtk.VISIBLE):
                self.queue_resize()

    def do_forall(self, internal, callback, data):
        if self.child:
            callback(self.child, data)

    def do_size_request(self, r):
        cw, ch = 0,0;
        if self.child and (self.child.flags() & gtk.VISIBLE):
            cw, ch =  self.child.size_request()

        # FIXME: what do we need border_width and an extra
        # 10px for?
        r.width = self.border_width + cw + 10
        r.height = self.border_width + ch + 10

    def do_size_allocate(self, allocation):
        self.allocation = allocation

        border_width = self.border_width
        w = self.allocation.width - border_width
        h = self.allocation.height - border_width

        if self.flags() & gtk.REALIZED:
            self.window.move_resize(
                            allocation.x + border_width,
                            allocation.y + border_width,
                            w,h)

        if self.child and self.child.flags() & gtk.VISIBLE:
            ca = gtk.gdk.Rectangle(x=0,y=0,width=w,height=h)

            if self.flags() & gtk.REALIZED:
                self.offscreen_window.move_resize(
                            allocation.x + border_width,
                            allocation.y + border_width,
                            w, h)

            self.child.size_allocate(ca)

    # FIXME this does not play well with the automatic partitioning page
    # (expose events to the max, causes lockup)
    def do_damage_event(self, eventexpose):
        # invalidate the whole window
        self.window.invalidate_rect(None, False)
        return True

    def do_expose_event(self, event):
        if self.flags() & gtk.VISIBLE and self.flags() & gtk.MAPPED:
            if event.window == self.window:
                pm = gtk.gdk.offscreen_window_get_pixmap(self.offscreen_window)
                w,h = pm.get_size()

                cr = event.window.cairo_create()
                if self.greyed:
                    cr.save()
                cr.rectangle(0,0,w,h)
                cr.clip()

                # paint the offscreen child
                cr.set_source_pixmap(pm, 0, 0)
                cr.paint()

                if self.greyed:
                    cr.restore()
                    cr.set_source_rgba(0,0,0,0.5)
                    cr.rectangle(0, 0, *event.window.get_geometry()[2:4])
                    cr.paint()

            elif event.window == self.offscreen_window:
                self.style.paint_flat_box(
                                event.window,
                                gtk.STATE_NORMAL, gtk.SHADOW_NONE,
                                event.area, self, "blah",
                                0, 0, -1, -1)
                if self.child:
                    self.propagate_expose(self.child, event)

        return False

gobject.type_register(GreyableBin)

WM = 'com.ubuntu.ubiquity.WirelessManager'
WM_PATH = '/com/ubuntu/ubiquity/WirelessManager'

# Taken from software-center.
class CellRendererPixbufWithOverlay(gtk.CellRendererText):
    """ A CellRenderer with support for a pixbuf and a overlay icon
    
    It also supports "markup" and "text" so that orca and friends can
    read the content out
    """


    # FIXME get these from the icons
    # offset of the install overlay icon
    OFFSET_X = 3
    OFFSET_Y = 3

    # size of the install overlay icon
    OVERLAY_SIZE = 18

    __gproperties__ = {
        'overlay' : (bool, 'overlay', 'show an overlay icon', False,
                     gobject.PARAM_READWRITE),
        'pixbuf'  : (gtk.gdk.Pixbuf, 'pixbuf', 'pixbuf',
                     gobject.PARAM_READWRITE)
    }
    __gtype_name__ = 'CellRendererPixbufWithOverlay'

    def __init__(self, overlay_icon_name):
        gtk.CellRendererText.__init__(self)
        icons = gtk.icon_theme_get_default()
        self.overlay = False
        try:
            self._installed = icons.load_icon(overlay_icon_name,
                                          self.OVERLAY_SIZE, 0)
        except glib.GError:
            # icon not present in theme, probably because running uninstalled
            self._installed = icons.load_icon('emblem-system',
                                          self.OVERLAY_SIZE, 0)
    def do_set_property(self, pspec, value):
        setattr(self, pspec.name, value)

    def do_get_property(self, pspec):
        return getattr(self, pspec.name)

    def do_get_size(self, w, cell_area):
        # FIXME get this from the icon itself
        width = 22
        height = 22
        return (0, 0, width, height)
    def do_render(self, window, widget, background_area, cell_area,
                  expose_area, flags):

        # always render icon app icon centered with respect to an unexpanded CellRendererAppView
        ypad = self.get_property('ypad')

        area = (cell_area.x,
                cell_area.y+ypad,
                # FIXME
                22,
                22)
                #AppStore.ICON_SIZE,
                #AppStore.ICON_SIZE)

        dest_x = cell_area.x
        dest_y = cell_area.y
        window.draw_pixbuf(None,
                           self.pixbuf, # icon
                           0, 0,            # src pixbuf
                           dest_x, dest_y,  # dest in window
                           -1, -1,          # size
                           0, 0, 0)         # dither

        if self.overlay:
            dest_x += self.OFFSET_X
            dest_y += self.OFFSET_Y
            window.draw_pixbuf(None,
                               self._installed, # icon
                               0, 0,            # src pixbuf
                               dest_x, dest_y,  # dest in window
                               -1, -1,          # size
                               0, 0, 0)         # dither

gobject.type_register(CellRendererPixbufWithOverlay)

class WirelessTreeView(gtk.TreeView):
    __gtype_name__ = 'WirelessTreeView'
    def __init__(self, bus):
        self.model = gtk.ListStore(str)
        gtk.TreeView.__init__(self, self.model)

        self.cache = {}
        self.bus = bus
        self.set_headers_visible(False)

        col = gtk.TreeViewColumn()
        cell_pixbuf = CellRendererPixbufWithOverlay('nm-secure-lock')
        cell_pixbuf.set_property('overlay', True)
        cell = gtk.CellRendererText()
        col.pack_start(cell_pixbuf, False)
        col.pack_start(cell, True)
        col.set_cell_data_func(cell, self.column_data_func, 0)
        col.set_cell_data_func(cell_pixbuf, self.pixbuf_data_func)
        self.append_column(col)
        
        it = gtk.icon_theme_get_default()
        self.icons = {}
        map = {'wifi-020': 'nm-signal-00',
               'wifi-040': 'nm-signal-25',
               'wifi-060': 'nm-signal-50',
               'wifi-080': 'nm-signal-75',
               'wifi-100': 'nm-signal-100'}
        for n in map:
            if it.has_icon(n):
                ico = it.lookup_icon(n, 22, 0)
            else:
                ico = it.lookup_icon(map[n], 22, 0)
            if ico:
                ico = ico.load_icon()
                self.icons[n] = ico

    def scan(self):
        o = self.bus.get_object(WM, WM_PATH)
        self.interface = dbus.Interface(o, WM)
        for ap in self.interface.GetAPs():
            self.cache[ap] = self.interface.GetProperties(ap)
            self.model.append([ap])
        self.bus.add_signal_receiver(self.strength_changed, 'StrengthChanged', WM, WM)
        self.bus.add_signal_receiver(self.added, 'Added', WM, WM)
        self.bus.add_signal_receiver(self.removed, 'Removed', WM, WM)

    def do_expose_event(self, event):
        # TODO if connecting ...
        # Use an offscreen window to create the overlay.
        cr = self.window.cairo_create()
        cr.set_source_rgb(0,0,0)
        cr.rectangle(0, 0, *self.window.get_geometry()[2:4])
        cr.paint()
        gtk.TreeView.do_expose_event(self, event)

    def added(self, ap):
        self.cache[ap] = self.interface.GetProperties(ap)
        self.model.append([ap])

    def removed(self, ap):
        iterator = self.model.get_iter_first()
        while iterator is not None:
            if self.model.get_value(iterator, 0) == ap:
                break
            iterator = self.model.iter_next(iterator)
        if iterator:
            self.model.remove(iterator)

    def strength_changed(self, ap, value):
        iterator = self.model.get_iter_first()
        while iterator is not None:
            if self.model.get_value(iterator, 0) == ap:
                break
            iterator = self.model.iter_next(iterator)
        if ap in self.cache and iterator:
            self.cache[ap]['Strength'] = value
            self.model.row_changed(self.model.get_path(iterator), iterator)
    
    def get_passphrase(self, ap):
        return self.cache[ap]['Passphrase']

    def get_locked(self, ap):
        return self.cache[ap]['Locked']

    def pixbuf_data_func(self, column, cell, model, iterator):
        ap = model[iterator][0]
        ap = self.cache[ap]
        # Need custom icons for wifi on light background.
        strength = ap['Strength']
        if strength < 30:
            icon = 'wifi-020'
        elif strength < 50:
            icon = 'wifi-040'
        elif strength < 70:
            icon = 'wifi-060'
        elif strength < 90:
            icon = 'wifi-080'
        else:
            icon = 'wifi-100'
        if self.icons.has_key(icon):
            cell.set_property('pixbuf', self.icons[icon])
        cell.set_property('overlay', ap['Locked'])

    def column_data_func(self, layout, cell, model, iterator, column):
        ap = model[iterator][0]
        ap = self.cache[ap]
        cell.set_property('text', ap['Ssid'])

    def do_row_activated(self, path, column):
        # This should be external to the class, so we can wire it to the entry.
        # And perhaps that should be part of a container class to simplify
        # insertion into the ubiquity code / glade.
        ap = self.model[self.model.get_iter(path)][0]
        self.interface.Connect(ap)
    # Need to watch state change so we can enable the next button.

gobject.type_register(WirelessTreeView)

# TODO: Show a helpful note if we don't see any wifi networks and a card is
# disabled.
class WirelessWidget(gtk.VBox):
    __gtype_name__ = 'WirelessWidget'
    def __init__(self):
        gtk.VBox.__init__(self, spacing=6)
        bus = dbus.SystemBus()
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.treeview = WirelessTreeView(bus)
        #box = GreyableBin()
        #box.set_property('greyed', False)
        sw.add(self.treeview)
        #box.add(sw)
        #self.pack_start(box)
        self.pack_start(sw)
        hbox = gtk.HBox(spacing=6)
        self.pack_start(hbox, expand=False)
        # TODO i18n
        l = gtk.Label('Password:')
        hbox.pack_start(l, False)
        self.entry = gtk.Entry()
        hbox.pack_start(self.entry)
        # TODO i18n
        cb = gtk.CheckButton('Display password')
        cb.set_active(True)
        hbox.pack_start(cb)
        self.treeview.get_selection().connect('changed', self.changed)
        cb.connect('toggled', self.show_passphrase)
        self.show_all()

    def show_passphrase(self, cb):
        self.entry.set_visibility(not self.entry.get_visibility())

    def changed(self, selection):
        model, iterator = selection.get_selected()
        if not iterator:
            return
        ap = model[iterator][0]
        passphrase = self.treeview.get_passphrase(ap)
        self.entry.set_text(passphrase)
        # if not passphrase and lock set, next.set_sensitive(False)

gobject.type_register(WirelessWidget)

if __name__ == "__main__":
    options = ('that you have at least 3GB available drive space',
               'that you are plugged in to a power source',
               'that you are connected to the Internet with an ethernet cable')
    w = gtk.Window()
    w.connect('destroy', gtk.main_quit)
    b = GreyableBin()
    a = gtk.VBox()
    a.set_spacing(5)
    a.set_border_width(20)
    
    # Prepare to install Ubuntu.
    space = StateBox(options[0])
    power = StateBox(options[1])
    inet = StateBox(options[2])
    for widget in (space, power, inet):
        a.pack_start(widget, expand=False)

    # Partition resizing.
    existing_part = PartitionBox('Files (20 MB)', '', 'folder')
    new_part = PartitionBox('Ubuntu 10.10', '/dev/sda2 (btrfs)', 'distributor-logo')
    hb = ResizeWidget(2**64, 2**64/4, 2**64/1.25, existing_part, new_part)
    a.pack_start(hb, expand=False)
    button = gtk.Button('Install')
    def func(*args):
        print 'Size:', hb.get_size()
    button.connect('clicked', func)
    a.pack_start(button, expand=False)

    le = LabelledEntry('A labelled entry')
    a.pack_start(le, expand=False)

    lcbe = LabelledComboBoxEntry()
    a.pack_start(lcbe, expand=False)

    bus = dbus.SystemBus()
    upower = bus.get_object('org.freedesktop.UPower', '/org/freedesktop/UPower')
    upower = dbus.Interface(upower, 'org.freedesktop.DBus.Properties')
    def power_state_changed():
        power.set_state(upower.Get('/org/freedesktop/UPower', 'OnBattery') == False)
    bus.add_signal_receiver(power_state_changed, 'Changed', 'org.freedesktop.UPower', 'org.freedesktop.UPower')
    power_state_changed()
    
    w2 = gtk.Window()
    w2.set_transient_for(w)
    w2.set_modal(True)
    w2.show()
    #w.add(b)
    b.set_property('greyed', True)
    b.add(a)
    wireless = WirelessWidget()
    a.pack_start(wireless)
    w.add(b)
    w.show_all()
    gtk.main()

# TODO: Process layered on top of os-prober (or function) that:
#       - Calls os-prober to find the OS name.
#       - If the above fails, gives us the free space on a partition by
#         mounting it read-only in a separate kernel space.

# TODO: We should be able to construct any widget without passing parameters to
# its constructor.

# TODO: Bring in the timezone_map, but keep it in a separate file and make it
# so the tz database can be None, in which case it just prints the map
# background.  Give it its own gdk.window or EventBox.
