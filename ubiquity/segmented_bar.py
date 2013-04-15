# segmented_bar.py
#
# Original author:
#   Aaron Bockover <abockover@novell.com>
#
# Translated to Python and further modifications by:
#   Evan Dandrea <ev@ubuntu.com>
#
# Copyright (C) 2008 Novell, Inc.
# Copyright (C) 2008 Canonical Ltd.
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

import math

import cairo
from gi.repository import GObject, Gdk, Gtk, PangoCairo

from ubiquity.misc import find_in_os_prober, format_size


class Color:
    def __init__(self, r, g, b, a=1.0):
        self.r = r
        self.g = g
        self.b = b
        self.a = a


class CairoCorners:
    no_corners = 0
    top_left = 1
    top_right = 2
    bottom_left = 4
    bottom_right = 8
    all = 15


class CairoExtensions:
    @staticmethod
    def modula(number, divisor):
        return int((number % divisor) + (number - int(number)))

    @staticmethod
    def color_from_hsb(hue, saturation, brightness):
        hue_shift = [0, 0, 0]
        color_shift = [0, 0, 0]
        if brightness <= 0.5:
            m2 = brightness * (1 + saturation)
        else:
            m2 = brightness + saturation - brightness * saturation
        m1 = 2 * brightness - m2
        hue_shift[0] = hue + 120
        hue_shift[1] = hue
        hue_shift[2] = hue - 120
        color_shift[0] = brightness
        color_shift[1] = brightness
        color_shift[2] = brightness
        if saturation == 0:
            i = 3
        else:
            i = 0
        while i < 3:
            m3 = hue_shift[i]
            if m3 > 360:
                m3 = CairoExtensions.modula(m3, 360)
            elif m3 < 0:
                m3 = 360 - CairoExtensions.modula(abs(m3), 360)

            if m3 < 60:
                color_shift[i] = m1 + (m2 - m1) * m3 / 60
            elif m3 < 180:
                color_shift[i] = m2
            elif m3 < 240:
                color_shift[i] = m1 + (m2 - m1) * (240 - m3) / 60
            else:
                color_shift[i] = m1
            i = i + 1

        return Color(color_shift[0], color_shift[1], color_shift[2])

    @staticmethod
    def hsb_from_color(color):
        red = color.r
        green = color.g
        blue = color.b
        hue = 0
        saturation = 0
        brightness = 0

        if red > green:
            ma = max(red, blue)
            mi = min(green, blue)
        else:
            ma = max(green, blue)
            mi = min(red, blue)

        brightness = (ma + mi) / 2

        if abs(ma - mi) < 0.0001:
            hue = 0
            saturation = 0
        else:
            if brightness <= 0.5:
                saturation = (ma - mi) / (ma + mi)
            else:
                saturation = (ma - mi) / (2 - ma - mi)
            delta = ma - mi
            if red == max:
                hue = (green - blue) / delta
            elif green == max:
                hue = 2 + (blue - red) / delta
            elif blue == max:
                hue = 4 + (red - green) / delta
            hue = hue * 60
            if hue < 0:
                hue = hue + 360
        return (hue, saturation, brightness)

    @staticmethod
    def color_shade(color, ratio):
        # FIXME evand 2008-07-19: This function currently produces only deep
        # reds for non-white colors.
        return color
        h, s, b = CairoExtensions.hsb_from_color(color)
        b = max(min(b * ratio, 1), 0)
        s = max(min(s * ratio, 1), 0)
        c = CairoExtensions.color_from_hsb(h, s, b)
        c.a = color.a
        return c

    @staticmethod
    def rgba_to_color(color):
        # FIXME evand 2008-07-19: We should probably match the input of
        # rgb_to_color.
        a = ((color >> 24) & 0xff) / 255.0
        b = ((color >> 16) & 0xff) / 255.0
        c = ((color >> 8) & 0xff) / 255.0
        d = (color & 0x000000ff) / 255.0
        return Color(a, b, c, d)

    @staticmethod
    def rgb_to_color(color):
        # FIXME evand 2008-07-19: Should we assume a hex string or should we
        # copy Hyena and require a hex number?
        r, g, b = color[:2], color[2:4], color[4:]
        r, g, b = [(int(n, 16) / 255.0) for n in (r, g, b)]
        return Color(r, g, b)
        #return CairoExtensions.rgba_to_color((color << 8) | 0x000000ff)

    @staticmethod
    def rounded_rectangle(cr, x, y, w, h, r, corners=CairoCorners.all,
                          top_bottom_falls_through=False):
        if top_bottom_falls_through and corners == CairoCorners.no_corners:
            cr.move_to(x, y - r)
            cr.line_to(x, y + h + r)
            cr.move_to(x + w, y - r)
            cr.line_to(x + w, y + h + r)
        elif r < 0.0001 or corners == CairoCorners.no_corners:
            cr.rectangle(x, y, w, h)

        corners_top = CairoCorners.top_left | CairoCorners.top_right
        if (corners & corners_top) == 0 and top_bottom_falls_through:
            y = y - r
            h = h + r
            cr.move_to(x + w, y)
        else:
            if (corners & CairoCorners.top_left) != 0:
                cr.move_to(x + r, y)
            else:
                cr.move_to(x, y)

            if (corners & CairoCorners.top_right) != 0:
                cr.arc(x + w - r, y + r, r, math.pi * 1.5, math.pi * 2)
            else:
                cr.line_to(x + w, y)

        corners_bottom = CairoCorners.bottom_left | CairoCorners.bottom_right
        if (corners & corners_bottom) == 0 and top_bottom_falls_through:
            h = h + r
            cr.line_to(x + w, y + h)
            cr.move_to(x, y + h)
            cr.line_to(x, y + r)
            cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
        else:
            if (corners & CairoCorners.bottom_right) != 0:
                cr.arc(x + w - r, y + h - r, r, 0, math.pi * 0.5)
            else:
                cr.line_to(x + w, y + h)

            if (corners & CairoCorners.bottom_left) != 0:
                cr.arc(x + r, y + h - r, r, math.pi * 0.5, math.pi)
            else:
                cr.line_to(x, y + h)

            if (corners & CairoCorners.top_left) != 0:
                cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
            else:
                cr.line_to(x, y)


class SegmentedBar(Gtk.DrawingArea):
    __gtype_name__ = 'SegmentedBar'

    def __init__(self):
        GObject.GObject.__init__(self)

        # State
        self.segments = []
        self.layout_width = 0
        self.layout_height = 0

        # Properties
        self.bar_height = 13
        # Vertical space between the bar and the label.
        self.bar_label_spacing = 8
        # Horizontal space between the label and the next box.
        self.segment_label_spacing = 16
        self.segment_box_size = 12
        self.segment_box_spacing = 6
        self.h_padding = 0
        self.center_labels = False

        self.show_labels = True
        self.reflect = True
        self.remainder_color = 'eeeeee'

        self.disk_size = 0
        self.context = None
        self.fd = None

        test_window = Gtk.Window()
        test_label = Gtk.Label()
        test_window.add(test_label)
        style = test_label.get_style_context()
        self.text_color = style.get_color(Gtk.StateFlags.NORMAL)
        self.subtext_color = style.get_color(Gtk.StateFlags.INSENSITIVE)

    def add_segment(self, title, size, color, show_in_bar=True):
        self.do_size_allocate(self.get_allocation())
        self.disk_size += size
        self.segments.append(self.Segment(title, size, color, show_in_bar))
        self.queue_draw()

    def remove_all(self):
        self.segments = []
        self.disk_size = 0
        self.queue_draw()

    def add_segment_rgb(self, title, size, rgb_color):
        self.add_segment(title, size, CairoExtensions.rgb_to_color(rgb_color))

    def do_size_request(self, requisition):
        requisition.width = 200
        requisition.height = 0

    def compute_layout_size(self):
        self.layout_height = 0
        self.layout_width = 0

        layout = self.create_pango_layout('')
        for i in range(len(self.segments)):
            title = self.segments[i].title
            layout.set_markup('<b>%s</b>' % title, -1)
            aw, ah = layout.get_pixel_size()

            layout.set_markup(
                '<small>%s</small>' % self.segments[i].subtitle, -1)
            bw, bh = layout.get_pixel_size()

            w = max(aw, bw)
            h = ah + bh

            self.segments[i].layout_width = w
            self.segments[i].layout_height = max(h, self.segment_box_size * 2)

            if i < (len(self.segments) - 1):
                self.layout_width = self.layout_width + \
                    self.segments[i].layout_width + self.segment_box_size + \
                    self.segment_box_spacing + self.segment_label_spacing
            else:
                self.layout_width = self.layout_width + \
                    self.segments[i].layout_width + self.segment_box_size + \
                    self.segment_box_spacing + 0
            self.layout_height = max(
                self.layout_height, self.segments[i].layout_height)

    def do_size_allocate(self, allocation):
        if self.reflect:
            bar_height = int(math.ceil(self.bar_height * 1.75))
        else:
            bar_height = self.bar_height

        if self.show_labels:
            self.compute_layout_size()
            h = max(
                self.bar_height + self.bar_label_spacing + self.layout_height,
                bar_height)
            w = self.layout_width + (2 * self.h_padding)
            self.set_size_request(w, h)
        else:
            self.set_size_request(
                bar_height, self.bar_height + (2 * self.h_padding))
        Gtk.DrawingArea.do_size_allocate(self, allocation)

    def render_bar_segments(self, cr, w, h, r):
        grad = cairo.LinearGradient(0, 0, w, 0)
        last = 0.0

        for segment in self.segments:
            percent = segment.size / float(self.disk_size)
            if percent > 0:
                grad.add_color_stop_rgb(
                    last, segment.color.r, segment.color.g, segment.color.b)
                last = last + percent
                grad.add_color_stop_rgb(
                    last, segment.color.r, segment.color.g, segment.color.b)

        CairoExtensions.rounded_rectangle(
            cr, 0, 0, w, h, r, corners=CairoCorners.no_corners)
        cr.set_source(grad)
        cr.fill_preserve()

        grad = cairo.LinearGradient(0, 0, 0, h)
        grad.add_color_stop_rgba(0.0, 1, 1, 1, 0.125)
        grad.add_color_stop_rgba(0.35, 1, 1, 1, 0.255)
        grad.add_color_stop_rgba(1, 0, 0, 0, 0.4)

        cr.set_source(grad)
        cr.fill()

    def make_segment_gradient(self, h, color):
        grad = cairo.LinearGradient(0, 0, 0, h)
        c = CairoExtensions.color_shade(color, 1.1)
        grad.add_color_stop_rgba(0.0, c.r, c.g, c.b, c.a)
        c = CairoExtensions.color_shade(color, 1.2)
        grad.add_color_stop_rgba(0.35, c.r, c.g, c.b, c.a)
        c = CairoExtensions.color_shade(color, 0.8)
        grad.add_color_stop_rgba(1, c.r, c.g, c.b, c.a)
        return grad

    def render_bar_strokes(self, cr, w, h, r):
        stroke = self.make_segment_gradient(
            h, CairoExtensions.rgba_to_color(0x00000040))
        seg_sep_light = self.make_segment_gradient(
            h, CairoExtensions.rgba_to_color(0xffffff20))
        seg_sep_dark = self.make_segment_gradient(
            h, CairoExtensions.rgba_to_color(0x00000020))

        cr.set_line_width(1)
        seg_w = 20
        if seg_w > r:
            x = seg_w
        else:
            x = r

        while x <= w - r:
            cr.move_to(x - 0.5, 1)
            cr.line_to(x - 0.5, h - 1)
            cr.set_source(seg_sep_light)
            cr.stroke()

            cr.move_to(x + 0.5, 1)
            cr.line_to(x + 0.5, h - 1)
            cr.set_source(seg_sep_dark)
            cr.stroke()
            x = x + seg_w

        CairoExtensions.rounded_rectangle(
            cr, 0.5, 0.5, w - 1, h - 1, r, corners=CairoCorners.no_corners)
        cr.set_source(stroke)
        cr.stroke()

    def render_labels(self, cr):
        if len(self.segments) == 0:
            return
        box_stroke_color = Gdk.RGBA(0, 0, 0, 0.6)
        x = 0
        layout = self.create_pango_layout('')

        for segment in self.segments:
            cr.set_line_width(1)
            cr.rectangle(
                x + 0.5, 2 + 0.5, self.segment_box_size - 1,
                self.segment_box_size - 1)
            grad = self.make_segment_gradient(
                self.segment_box_size, segment.color)
            cr.set_source(grad)
            cr.fill_preserve()
            Gdk.cairo_set_source_rgba(cr, box_stroke_color)
            cr.stroke()

            x = x + self.segment_box_size + self.segment_box_spacing

            layout.set_markup('<b>%s</b>' % segment.title, -1)
            (lw, lh) = layout.get_pixel_size()

            cr.move_to(x, 0)
            Gdk.cairo_set_source_rgba(cr, self.text_color)
            PangoCairo.show_layout(cr, layout)
            cr.fill()

            layout.set_markup('<small>%s</small>' % segment.subtitle, -1)

            cr.move_to(x, lh)
            Gdk.cairo_set_source_rgba(cr, self.subtext_color)
            PangoCairo.show_layout(cr, layout)
            cr.fill()
            x = x + segment.layout_width + self.segment_label_spacing

    def render_bar(self, w, h):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(s)
        self.render_bar_segments(cr, w, h, h / 2)
        self.render_bar_strokes(cr, w, h, h / 2)
        pattern = cairo.SurfacePattern(s)
        return pattern

    def do_draw(self, cr):
        if self.reflect:
            cr.push_group()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.translate(
            self.get_allocation().x + self.h_padding, self.get_allocation().y)
        cr.rectangle(
            0, 0, self.get_allocation().width - self.h_padding,
            max(
                2 * self.bar_height,
                self.bar_height + self.bar_label_spacing + self.layout_height))
        cr.clip()

        bar = self.render_bar(
            self.get_allocation().width - 2 * self.h_padding, self.bar_height)

        cr.save()
        cr.set_source(bar)
        cr.paint()
        cr.restore()

        if self.reflect:
            cr.save()
            cr.rectangle(
                0, self.bar_height,
                self.get_allocation().width - self.h_padding, self.bar_height)
            cr.clip()
            matrix = cairo.Matrix(xx=1, yy=-1)
            matrix.translate(0, -(2 * self.bar_height) + 1)
            cr.transform(matrix)
            cr.set_source(bar)

            mask = cairo.LinearGradient(0, 0, 0, self.bar_height)
            c = Color(0, 0, 0, 0)
            mask.add_color_stop_rgba(0.25, c.r, c.g, c.b, c.a)
            c = Color(0, 0, 0, 0.125)
            mask.add_color_stop_rgba(0.5, c.r, c.g, c.b, c.a)
            c = Color(0, 0, 0, 0.4)
            mask.add_color_stop_rgba(0.75, c.r, c.g, c.b, c.a)
            c = Color(0, 0, 0, 0.7)
            mask.add_color_stop_rgba(1.0, c.r, c.g, c.b, c.a)

            cr.mask(mask)
            cr.restore()
            cr.pop_group_to_source()
            cr.paint()
        if self.show_labels:
            allocation = self.get_allocation()
            if self.reflect:
                if self.center_labels:
                    width = (allocation.width - self.layout_width) / 2
                    height = self.bar_height + self.bar_label_spacing
                    cr.translate(allocation.x + width, allocation.y + height)
                else:
                    height = self.bar_height + self.bar_label_spacing
                    cr.translate(
                        allocation.x + self.h_padding, allocation.y + height)
            else:
                width = (allocation.width - self.layout_width) / 2
                cr.translate(
                    -self.h_padding + width,
                    self.bar_height + self.bar_label_spacing)
            self.render_labels(cr)

        return True

    class Segment:
        def __init__(self, device, size, color, show_in_bar=True):
            self.device = device
            self.title = ''
            if device.startswith('/'):
                self.title = find_in_os_prober(device)
            if self.title:
                self.title = '%s (%s)' % (self.title, device)
            else:
                self.title = device
            self.set_size(size)
            self.color = color
            self.show_in_bar = show_in_bar

            self.layout_width = 0
            self.layout_height = 0

        def __eq__(self, obj):
            if self.device == obj:
                return True
            else:
                return False

        def set_size(self, size):
            self.size = size
            if size > 0:
                self.subtitle = format_size(self.size)
            else:
                self.subtitle = ''

GObject.type_register(SegmentedBar)
