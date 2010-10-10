# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2009 Canonical Ltd.
# Written by Evan Dandrea <evand@ubuntu.com>.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

# A simple timezone map that highlights timezone bands.

import math
import cairo
import gtk
import glib
import gobject
import os
import datetime
from ubiquity.segmented_bar import CairoExtensions

# We need a color coded map so we can only select from the list of points that
# are in the time zone band the user clicked on.  It would be odd if the user
# clicked within UTC-5, but it selected a point in UTC-6 because it was closer
# to the mouse.
color_codes = {
# We don't handle UTC-12, but as that's just the US Minor Outlying Islands, I
# think we're ok, as Wikipedia says, "As of 2008, none of the islands has any
# permanent residents."
'-11.0' : [43, 0, 0, 255],
'-10.0' : [85, 0, 0, 255],
'-9.5' : [102, 255, 0, 255],
'-9.0' : [128, 0, 0, 255],
'-8.0' : [170, 0, 0, 255],
'-7.0' : [212, 0, 0, 255],
'-6.0|north' : [255, 0, 1, 255],
'-6.0|south' : [255, 0, 0, 255],
'-5.0' : [255, 42, 42, 255],
'-4.5' : [192, 255, 0, 255],
'-4.0' : [255, 85, 85, 255],
'-3.5' : [0, 255, 0, 255],
'-3.0' : [255, 128, 128, 255],
'-2.0' : [255, 170, 170, 255],
'-1.0' : [255, 213, 213, 255],
'0.0' : [43, 17, 0, 255],
'1.0' : [85, 34, 0, 255],
'2.0' : [128, 51, 0, 255],
'3.0' : [170, 68, 0, 255],
'3.5' : [0, 255, 102, 255],
'4.0' : [212, 85, 0, 255],
'4.5' : [0, 204, 255, 255],
'5.0' : [255, 102, 0, 255],
'5.5' : [0, 102, 255, 255],
'5.75' : [0, 238, 207, 247],
'6.0' : [255, 127, 42, 255],
'6.5' : [204, 0, 254, 254],
'7.0' : [255, 153, 85, 255],
'8.0' : [255, 179, 128, 255],
'9.0' : [255, 204, 170, 255],
'9.5' : [170, 0, 68, 250],
'10.0' : [255, 230, 213, 255],
'10.5' : [212, 124, 21, 250],
'11.0' : [212, 170, 0, 255],
'11.5' : [249, 25, 87, 253],
'12.0' : [255, 204, 0, 255],
'12.75' : [254, 74, 100, 248],
'13.0' : [255, 85, 153, 250],
}

olsen_map_timezones = [
"Africa/Abidjan",
"Africa/Accra",
"Africa/Addis_Ababa",
"Africa/Algiers",
"Africa/Asmara",
"Africa/Bamako",
"Africa/Bangui",
"Africa/Banjul",
"Africa/Bissau",
"Africa/Blantyre",
"Africa/Brazzaville",
"Africa/Bujumbura",
"Africa/Cairo",
"Africa/Casablanca",
"Africa/Conakry",
"Africa/Dakar",
"Africa/Dar_es_Salaam",
"Africa/Djibouti",
"Africa/Douala",
"Africa/El_Aaiun",
"Africa/Freetown",
"Africa/Gaborone",
"Africa/Harare",
"Africa/Johannesburg",
"Africa/Kampala",
"Africa/Khartoum",
"Africa/Kigali",
"Africa/Kinshasa",
"Africa/Lagos",
"Africa/Libreville",
"Africa/Lome",
"Africa/Luanda",
"Africa/Lubumbashi",
"Africa/Lusaka",
"Africa/Malabo",
"Africa/Maputo",
"Africa/Maseru",
"Africa/Mbabane",
"Africa/Mogadishu",
"Africa/Monrovia",
"Africa/Nairobi",
"Africa/Ndjamena",
"Africa/Niamey",
"Africa/Nouakchott",
"Africa/Ouagadougou",
"Africa/Porto-Novo",
"Africa/Sao_Tome",
"Africa/Tripoli",
"Africa/Tunis",
"Africa/Windhoek",
"America/Adak",
"America/Anguilla",
"America/Antigua",
"America/Araguaina",
"America/Argentina/Buenos_Aires",
"America/Argentina/Catamarca",
"America/Argentina/Cordoba",
"America/Argentina/Jujuy",
"America/Argentina/La_Rioja",
"America/Argentina/Mendoza",
"America/Argentina/Rio_Gallegos",
"America/Argentina/San_Juan",
"America/Argentina/San_Luis",
"America/Argentina/Tucuman",
"America/Argentina/Ushuaia",
"America/Aruba",
"America/Asuncion",
"America/Atikokan",
"America/Bahia",
"America/Barbados",
"America/Belem",
"America/Belize",
"America/Blanc-Sablon",
"America/Boa_Vista",
"America/Bogota",
"America/Boise",
"America/Cambridge_Bay",
"America/Campo_Grande",
"America/Cancun",
"America/Caracas",
"America/Cayenne",
"America/Cayman",
"America/Chicago",
"America/Chihuahua",
"America/Coral_Harbour",
"America/Costa_Rica",
"America/Cuiaba",
"America/Curacao",
"America/Dawson",
"America/Dawson_Creek",
"America/Denver",
"America/Dominica",
"America/Edmonton",
"America/Eirunepe",
"America/El_Salvador",
"America/Fortaleza",
"America/Glace_Bay",
"America/Goose_Bay",
"America/Grand_Turk",
"America/Grenada",
"America/Guadeloupe",
"America/Guatemala",
"America/Guayaquil",
"America/Guyana",
"America/Halifax",
"America/Havana",
"America/Hermosillo",
"America/Indiana/Indianapolis",
"America/Indiana/Knox",
"America/Indiana/Marengo",
"America/Indiana/Petersburg",
"America/Indiana/Vevay",
"America/Indiana/Vincennes",
"America/Indiana/Winamac",
"America/Inuvik",
"America/Iqaluit",
"America/Jamaica",
"America/Juneau",
"America/Kentucky/Louisville",
"America/Kentucky/Monticello",
"America/La_Paz",
"America/Lima",
"America/Los_Angeles",
"America/Maceio",
"America/Managua",
"America/Manaus",
"America/Marigot",
"America/Martinique",
"America/Mazatlan",
"America/Menominee",
"America/Merida",
"America/Mexico_City",
"America/Miquelon",
"America/Moncton",
"America/Monterrey",
"America/Montevideo",
"America/Montreal",
"America/Montserrat",
"America/Nassau",
"America/New_York",
"America/Nipigon",
"America/Noronha",
"America/North_Dakota/Center",
"America/North_Dakota/Salem",
"America/Panama",
"America/Pangnirtung",
"America/Paramaribo",
"America/Phoenix",
"America/Port-au-Prince",
"America/Port_of_Spain",
"America/Porto_Velho",
"America/Puerto_Rico",
"America/Rainy_River",
"America/Rankin_Inlet",
"America/Recife",
"America/Regina",
"America/Resolute",
"America/Rio_Branco",
"America/Santarem",
"America/Santiago",
"America/Santo_Domingo",
"America/Sao_Paulo",
"America/St_Barthelemy",
"America/St_Johns",
"America/St_Kitts",
"America/St_Lucia",
"America/St_Thomas",
"America/St_Vincent",
"America/Tegucigalpa",
"America/Thunder_Bay",
"America/Tijuana",
"America/Toronto",
"America/Tortola",
"America/Vancouver",
"America/Whitehorse",
"America/Winnipeg",
"America/Yellowknife",
"Ameriica/Swift_Current",
"Arctic/Longyearbyen",
"Asia/Aden",
"Asia/Almaty",
"Asia/Amman",
"Asia/Anadyr",
"Asia/Aqtau",
"Asia/Aqtobe",
"Asia/Ashgabat",
"Asia/Baghdad",
"Asia/Bahrain",
"Asia/Baku",
"Asia/Bangkok",
"Asia/Beirut",
"Asia/Bishkek",
"Asia/Brunei",
"Asia/Choibalsan",
"Asia/Chongqing",
"Asia/Colombo",
"Asia/Damascus",
"Asia/Dhaka",
"Asia/Dili",
"Asia/Dubai",
"Asia/Dushanbe",
"Asia/Gaza",
"Asia/Harbin",
"Asia/Ho_Chi_Minh",
"Asia/Hong_Kong",
"Asia/Hovd",
"Asia/Irkutsk",
"Asia/Jakarta",
"Asia/Jayapura",
"Asia/Jerusalem",
"Asia/Kabul",
"Asia/Kamchatka",
"Asia/Karachi",
"Asia/Kashgar",
"Asia/Katmandu",
"Asia/Kolkata",
"Asia/Krasnoyarsk",
"Asia/Kuala_Lumpur",
"Asia/Kuching",
"Asia/Kuwait",
"Asia/Macau",
"Asia/Magadan",
"Asia/Makassar",
"Asia/Manila",
"Asia/Muscat",
"Asia/Nicosia",
"Asia/Novosibirsk",
"Asia/Omsk",
"Asia/Oral",
"Asia/Phnom_Penh",
"Asia/Pontianak",
"Asia/Pyongyang",
"Asia/Qatar",
"Asia/Qyzylorda",
"Asia/Rangoon",
"Asia/Riyadh",
"Asia/Sakhalin",
"Asia/Samarkand",
"Asia/Seoul",
"Asia/Shanghai",
"Asia/Singapore",
"Asia/Taipei",
"Asia/Tashkent",
"Asia/Tbilisi",
"Asia/Tehran",
"Asia/Thimphu",
"Asia/Tokyo",
"Asia/Ulaanbaatar",
"Asia/Urumqi",
"Asia/Vientiane",
"Asia/Vladivostok",
"Asia/Yakutsk",
"Asia/Yekaterinburg",
"Asia/Yerevan",
"Atlantic/Azores",
"Atlantic/Bermuda",
"Atlantic/Canary",
"Atlantic/Cape_Verde",
"Atlantic/Faroe",
"Atlantic/Madeira",
"Atlantic/Reykjavik",
"Atlantic/South_Georgia",
"Atlantic/St_Helena",
"Atlantic/Stanley",
"Australia/Adelaide",
"Australia/Brisbane",
"Australia/Broken_Hill",
"Australia/Currie",
"Australia/Darwin",
"Australia/Eucla",
"Australia/Hobart",
"Australia/Lindeman",
"Australia/Lord_Howe",
"Australia/Melbourne",
"Australia/Perth",
"Australia/Sydney",
"Europe/Amsterdam",
"Europe/Andorra",
"Europe/Athens",
"Europe/Belgrade",
"Europe/Berlin",
"Europe/Bratislava",
"Europe/Brussels",
"Europe/Bucharest",
"Europe/Budapest",
"Europe/Chisinau",
"Europe/Copenhagen",
"Europe/Dublin",
"Europe/Gibraltar",
"Europe/Guernsey",
"Europe/Helsinki",
"Europe/Isle_of_Man",
"Europe/Istanbul",
"Europe/Jersey",
"Europe/Kaliningrad",
"Europe/Kiev",
"Europe/Lisbon",
"Europe/Ljubljana",
"Europe/London",
"Europe/Luxembourg",
"Europe/Madrid",
"Europe/Malta",
"Europe/Marienhamn",
"Europe/Minsk",
"Europe/Monaco",
"Europe/Moscow",
"Europe/Oslo",
"Europe/Paris",
"Europe/Podgorica",
"Europe/Prague",
"Europe/Riga",
"Europe/Rome",
"Europe/Samara",
"Europe/San_Marino",
"Europe/Sarajevo",
"Europe/Simferopol",
"Europe/Skopje",
"Europe/Sofia",
"Europe/Stockholm",
"Europe/Tallinn",
"Europe/Tirane",
"Europe/Uzhgorod",
"Europe/Vaduz",
"Europe/Vatican",
"Europe/Vienna",
"Europe/Vilnius",
"Europe/Volgograd",
"Europe/Warsaw",
"Europe/Zagreb",
"Europe/Zaporozhye",
"Europe/Zurich",
"Indian/Antananarivo",
"Indian/Chagos",
"Indian/Christmas",
"Indian/Cocos",
"Indian/Comoro",
"Indian/Kerguelen",
"Indian/Mahe",
"Indian/Maldives",
"Indian/Mauritius",
"Indian/Mayotte",
"Indian/Reunion",
"Pacific/Apia",
"Pacific/Auckland",
"Pacific/Chatham",
"Pacific/Easter",
"Pacific/Efate",
"Pacific/Enderbury",
"Pacific/Fakaofo",
"Pacific/Fiji",
"Pacific/Funafuti",
"Pacific/Galapagos",
"Pacific/Gambier",
"Pacific/Guadalcanal",
"Pacific/Guam",
"Pacific/Honolulu",
"Pacific/Johnston",
"Pacific/Kiritimati",
"Pacific/Kosrae",
"Pacific/Kwajalein",
"Pacific/Majuro",
"Pacific/Marquesas",
"Pacific/Midway",
"Pacific/Nauru",
"Pacific/Niue",
"Pacific/Norfolk",
"Pacific/Noumea",
"Pacific/Pago_Pago",
"Pacific/Palau",
"Pacific/Pitcairn",
"Pacific/Ponape",
"Pacific/Port_Moresby",
"Pacific/Rarotonga",
"Pacific/Saipan",
"Pacific/Tahiti",
"Pacific/Tarawa",
"Pacific/Tongatapu",
"Pacific/Truk",
"Pacific/Wake",
"Pacific/Wallis"
]

# The South Pole is transformed from 0.0, -90.0 to 0.5, 1 before being adjusted
# for the shifted and missing arctic section of the map.

#def convert_longitude_to_x(longitude, map_width):
#    # Miller cylindrical map projection is just the longitude as the
#    # calculation is the longitude from the central meridian of the projection.
#    # Convert to radians.
#    x = (longitude * (math.pi / 180)) + math.pi # 0 ... 2pi
#    # Convert to a percentage.
#    x = x / (2 * math.pi)
#    x = x * map_width
#    # Adjust for the visible map starting near 170 degrees.
#    # Percentage shift required, grabbed from measurements using The GIMP.
#    x = x - (map_width * 0.039073402)
#    return x

def convert_longitude_to_x(longitude, map_width):
    xdeg_offset = -6
    x = (map_width * (180.0 + longitude) / 360.0) + (map_width * xdeg_offset / 180.0)
    x = x % map_width
    return x

#def convert_latitude_to_y(latitude, map_height):
#    # Miller cylindrical map projection, as used in the source map from the CIA
#    # world factbook.  Convert latitude to radians.
#    y = 1.25 * math.log(math.tan((0.25 * math.pi) + \
#        (0.4 * (latitude * (math.pi / 180)))))
#    # Convert to a percentage.
#    y = abs(y - 2.30341254338) # 0 ... 4.606825
#    y = y / 4.6068250867599998
#    # Adjust for the visible map not including anything beyond 60 degrees south
#    # (150 degrees vs 180 degrees).
#    y = y * (map_height * 1.2)
#    return y

def convert_latitude_to_y(latitude, map_height):
    bottom_lat = -59
    top_lat = 81
    top_per = top_lat / 180.0
    y = 1.25 * math.log(math.tan(math.pi / 4.0 + 0.4 * math.radians(latitude)))
    full_range = 4.6068250867599998
    top_offset = full_range * top_per
    map_range = abs(1.25 * math.log(math.tan(math.pi / 4.0 + 0.4 * math.radians(bottom_lat))) - top_offset)
    y = abs(y - top_offset)
    y = y / map_range
    y = y * map_height
    return y

class TimezoneMap(gtk.Widget):
    __gtype_name__ = 'TimezoneMap'
    __gsignals__ = {
        'city-selected' : (gobject.SIGNAL_RUN_FIRST,
                             gobject.TYPE_NONE,
                             (gobject.TYPE_STRING,))
    }

    def __init__(self, database, image_path):
        gtk.Widget.__init__(self)
        self.tzdb = database
        self.image_path = image_path
        self.time_fmt = '%X'
        self.orig_background = \
            gtk.gdk.pixbuf_new_from_file(os.path.join(self.image_path,
            'bg.png'))
        self.orig_color_map = \
            gtk.gdk.pixbuf_new_from_file(os.path.join(self.image_path,
            'cc.png'))
        self.connect('button-press-event', self.button_press)
        self.connect('map-event', self.mapped)
        self.connect('unmap-event', self.unmapped)
        self.selected_offset = None

        self.selected = None
        self.update_timeout = None

        self.distances = []
        self.previous_click = (-1, -1)
        self.dist_pos = 0
        
        # olsendb color coded map.
        # TODO in Natty, drop the timezone band colored map for this.
        self.olsen_map = gtk.gdk.pixbuf_new_from_file(os.path.join(
                                                      self.image_path,
                                                      'olsen_map.png'))
        self.olsen_map_channels = self.olsen_map.get_n_channels()
        self.olsen_map_pixels = self.olsen_map.get_pixels()
        self.olsen_map_rowstride = self.olsen_map.get_rowstride()

    def set_time_format(self, time_fmt):
        self.time_fmt = time_fmt

    def do_size_request(self, requisition):
        requisition.width = self.orig_background.get_width() / 2
        requisition.height = self.orig_background.get_height() / 2
        gtk.Widget.do_size_request(self, requisition)

    def do_size_allocate(self, allocation):
        self.background = self.orig_background.scale_simple(allocation.width,
            allocation.height, gtk.gdk.INTERP_BILINEAR)

        color_map = self.orig_color_map.scale_simple(allocation.width,
            allocation.height, gtk.gdk.INTERP_BILINEAR)
        self.visible_map_pixels = color_map.get_pixels()
        self.visible_map_rowstride = color_map.get_rowstride()
        gtk.Widget.do_size_allocate(self, allocation)

    def do_realize(self):
        self.set_flags(self.flags() | gtk.REALIZED)
        self.window = gtk.gdk.Window(
            self.get_parent_window(),
            width=self.allocation.width,
            height=self.allocation.height,
            window_type=gtk.gdk.WINDOW_CHILD,
            wclass=gtk.gdk.INPUT_OUTPUT,
            event_mask=self.get_events() |
                        gtk.gdk.EXPOSURE_MASK |
                        gtk.gdk.BUTTON_PRESS_MASK)
        self.window.set_user_data(self)
        self.style.attach(self.window)
        self.style.set_background(self.window, gtk.STATE_NORMAL)
        self.window.move_resize(*self.allocation)
        cursor = gtk.gdk.Cursor(gtk.gdk.HAND2)
        self.window.set_cursor(cursor)

    def do_expose_event(self, unused_event):
        cr = self.window.cairo_create()
        cr.set_source_pixbuf(self.background, 0, 0)
        cr.paint()

        # Render highlight.
        # Possibly not the best solution, though in my head it seems better
        # than keeping two copies (original and resized) of every timezone in
        # memory.
        pixbuf = None
        if self.selected_offset != None:
            try:
                pixbuf = gtk.gdk.pixbuf_new_from_file(os.path.join(self.image_path,
                    'timezone_%s.png' % self.selected_offset.split('|')[0]))
                pixbuf = pixbuf.scale_simple(self.allocation.width,
                    self.allocation.height, gtk.gdk.INTERP_BILINEAR)
                cr.set_source_pixbuf(pixbuf, 0, 0)
                cr.paint()
            except glib.GError, e:
                print 'Error setting the time zone band highlight:', str(e)
                return

        # Plot city and time.
        height = self.background.get_height()
        width = self.background.get_width()

        loc = self.selected and self.tzdb.get_loc(self.selected)
        if loc:
            pointx = convert_longitude_to_x(loc.longitude, width)
            pointy = convert_latitude_to_y(loc.latitude, height)

            cr.set_source_color(gtk.gdk.color_parse('#1e1e1e'))
            cr.arc(pointx, pointy, 4.5, 0, 2 * math.pi)
            cr.set_line_width(1.5)
            cr.fill_preserve()
            cr.set_source_color(gtk.gdk.color_parse('white'))
            cr.stroke()

            # Draw the time.
            now = datetime.datetime.now(loc.info)
            time_text = now.strftime(self.time_fmt)
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12.0)
            xbearing, ybearing, width, height, xadvance, yadvance = \
                cr.text_extents(time_text)
            newy = pointy - (ybearing / 2)
            if pointx + width + 10 > self.allocation.width:
                newx = pointx - 12 - width - 4
            else:
                newx = pointx + 12
            cr.move_to(newx, newy)
            cr.set_source_color(gtk.gdk.color_parse('#1e1e1e'))
            CairoExtensions.rounded_rectangle(cr, newx - 5, newy + ybearing - 6, width + 10, height + 12, height / 6)
            cr.fill_preserve()
            cr.stroke()
            cr.set_source_color(gtk.gdk.color_parse('white'))
            cr.move_to(newx, newy)
            cr.show_text(time_text)
            cr.stroke()

        # Fufill the CC by Attribution license requirements for the Geonames lookup
        text = 'Geonames.org'
        xbearing, ybearing, width, height, xadvance, yadvance = \
            cr.text_extents(text)
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(12.0)
        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.move_to(self.allocation.width - xadvance + xbearing - 5,
                   self.allocation.height - height - ybearing - 5)
        cr.show_text(text)
        cr.stroke()

    def timeout(self):
        self.queue_draw()
        return True

    def mapped(self, unused_widget, unused_event):
        if self.update_timeout is None:
            self.update_timeout = gobject.timeout_add(1000, self.timeout)

    def unmapped(self, unused_widget, unused_event):
        if self.update_timeout is not None:
            gobject.source_remove(self.update_timeout)
            self.update_timeout = None

    def select_city(self, city):
        self.selected = city
        loc = self.tzdb.get_loc(city)
        if loc:
            offset = (loc.raw_utc_offset.days * 24) + \
                (loc.raw_utc_offset.seconds / 60.0 / 60.0)
            self.selected_offset = str(offset)
        self.queue_draw()

    def convert_xy_to_offset(self, x, y):
        pixels = self.visible_map_pixels
        rowstride = self.visible_map_rowstride
        x = int(x)
        y = int(y)
        try:
            c = []
            c.append(ord(pixels[(rowstride * y + x * 4)]))
            c.append(ord(pixels[(rowstride * y + x * 4)+1]))
            c.append(ord(pixels[(rowstride * y + x * 4)+2]))
            c.append(ord(pixels[(rowstride * y + x * 4)+3]))
            for offset in color_codes:
                if color_codes[offset] == c:
                    return offset
        except IndexError:
            print 'Mouse click outside of the map.'
        return None

    def button_press(self, unused_widget, event):
        x = int(event.x)
        y = int(event.y)
        self.select_xy(x, y)

    def select_coords(self, lat, lon):
        city = None
        try:
            x = int(2048.0 / 360.0 * (180.0 + lon))
            y = int(1024.0 / 180.0 * (90.0 - lat))
            color = [ord(self.olsen_map_pixels[
                        (self.olsen_map_rowstride * y + x
                         * self.olsen_map_channels) + z]
                    ) for z in range(4)]
            zone = ((color[0] & 248) << 1) + ((color[1] >>4) & 15)
            if zone < len(olsen_map_timezones):
                city = olsen_map_timezones[zone]
        except Exception, e:
            print 'Exception caught with the Olsen database color map.', str(e)
        if city:
            self.select_city(city)
            self.emit('city-selected', city)
        else:
            height = self.background.get_height()
            width = self.background.get_width()
            x = convert_longitude_to_x(lon, width)
            y = convert_latitude_to_y(lat, height)
            self.select_xy(x, y)

    def select_xy(self, x, y):
        o = self.convert_xy_to_offset(x, y)
        if not o:
            return

        self.selected_offset = o

        if (x, y) == self.previous_click and self.distances:
            self.dist_pos = (self.dist_pos + 1) % len(self.distances)
            zone = self.distances[self.dist_pos][1].zone
        else:
            self.distances = []
            height = self.background.get_height()
            width = self.background.get_width()
            has_context = self.selected_offset.count('|') > 0
            for loc in self.tzdb.locations:
                offset = (loc.raw_utc_offset.days * 24) + \
                    (loc.raw_utc_offset.seconds / 60.0 / 60.0)
                if str(offset) != self.selected_offset.split('|')[0]:
                    continue
                pointx = convert_longitude_to_x(loc.longitude, width)
                pointy = convert_latitude_to_y(loc.latitude, height)
                if has_context:
                    pointo = self.convert_xy_to_offset(pointx, pointy)
                    same_context = pointo == o
                else:
                    same_context = True
                dx = pointx - x
                dy = pointy - y
                dist = dx * dx + dy * dy
                self.distances.append((dist, loc, same_context))
            self.distances.sort()
            # If this zone takes context into consideration (like
            # distinguishing sides of MX/US border), then move the
            # nearest city in the same context to the front.  We
            # only do this for the first city (i.e. the first click).
            for i in range(len(self.distances)):
                if self.distances[i][2]:
                    if i > 0:
                        self.distances.insert(0, self.distances.pop(i))
                    break
            # Disable for now.  As there are only a handful of cities in each
            # time zone band, it seemingly makes sense to cycle through all of
            # them.
            #self.distances = self.distances[:5]
            self.previous_click = (x, y)
            self.dist_pos = 0
            zone = self.distances[0][1].zone
        self.emit('city-selected', zone)
        self.queue_draw()

gobject.type_register(TimezoneMap)
