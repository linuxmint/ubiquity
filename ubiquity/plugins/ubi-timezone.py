# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006, 2007, 2008 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
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

from __future__ import print_function

import os
import re
import time
from urllib.parse import quote

import debconf
import icu

from ubiquity import i18n, misc, plugin
import ubiquity.tz


NAME = 'timezone'
#after partman for default install, but language for oem install
AFTER = ['partman', 'language']
WEIGHT = 10

_geoname_url = 'http://geoname-lookup.ubuntu.com/?query=%s&release=%s'


class PageGtk(plugin.PluginUI):
    plugin_title = 'ubiquity/text/timezone_heading_label'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        from gi.repository import Gtk
        builder = Gtk.Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], 'stepLocation.ui'))
        builder.connect_signals(self)
        self.page = builder.get_object('stepLocation')
        self.city_entry = builder.get_object('timezone_city_entry')
        self.map_window = builder.get_object('timezone_map_window')
        self.setup_page()
        self.timezone = None
        self.zones = []
        self.plugin_widgets = self.page
        self.geoname_cache = {}
        self.geoname_session = None
        self.geoname_timeout_id = None
        self.online = False

    def plugin_set_online_state(self, state):
        self.online = state

    def plugin_translate(self, lang):
        #c = self.controller
        #if c.get_string('ubiquity/imported/time-format', lang) == '12-hour':
        #    fmt = c.get_string('ubiquity/imported/12-hour', lang)
        #else:
        #    fmt = c.get_string('ubiquity/imported/24-hour', lang)
        #self.tzmap.set_time_format(fmt)
        inactive = self.controller.get_string(
            'timezone_city_entry_inactive_label', lang)
        self.city_entry.set_placeholder_text(inactive)

    def set_timezone(self, timezone):
        self.zones = self.controller.dbfilter.build_timezone_list()
        self.tzmap.set_timezone(timezone)

    def get_timezone(self):
        return self.timezone

    def select_city(self, unused_widget, city):
        city = city.get_property('zone')
        loc = self.tzdb.get_loc(city)
        if not loc:
            self.controller.allow_go_forward(False)
        else:
            self.city_entry.set_text(loc.human_zone)
            self.city_entry.set_position(-1)
            self.timezone = city
            self.controller.allow_go_forward(True)

    def changed(self, entry):
        from gi.repository import Gtk, GObject, GLib, Soup

        text = misc.utf8(self.city_entry.get_text())
        if not text:
            return
        # TODO if the completion widget has a selection, return?  How do we
        # determine this?
        if text in self.geoname_cache:
            model = self.geoname_cache[text]
            self.city_entry.get_completion().set_model(model)
        else:
            model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING,
                                  GObject.TYPE_STRING, GObject.TYPE_STRING,
                                  GObject.TYPE_STRING)

            if self.geoname_session is None:
                self.geoname_session = Soup.SessionAsync()
            url = _geoname_url % (quote(text), misc.get_release().version)
            message = Soup.Message.new('GET', url)
            message.request_headers.append('User-agent', 'Ubiquity/1.0')
            self.geoname_session.abort()
            if self.geoname_timeout_id is not None:
                GLib.source_remove(self.geoname_timeout_id)
            self.geoname_timeout_id = \
                GLib.timeout_add_seconds(2, self.geoname_timeout,
                                         (text, model))
            self.geoname_session.queue_message(message, self.geoname_cb,
                                               (text, model))

    def geoname_add_tzdb(self, text, model):
        if len(model):
            # already added
            return

        # TODO benchmark this
        results = [
            (name, self.tzdb.get_loc(city))
            for name, city in [
                (x[0], x[1])
                for x in self.zones
                if x[0].lower().split('(', 1)[-1].startswith(text.lower())]]
        for result in results:
            # We use name rather than loc.human_zone for i18n.
            # TODO this looks pretty awful for US results:
            # United States (New York) (United States)
            # Might want to match the debconf format.
            name, loc = result
            model.append([name, '', loc.human_country,
                          str(loc.latitude), str(loc.longitude)])

    def geoname_timeout(self, user_data):
        text, model = user_data
        self.geoname_add_tzdb(text, model)
        self.geoname_timeout_id = None
        self.city_entry.get_completion().set_model(model)
        return False

    def geoname_cb(self, session, message, user_data):
        import syslog
        import json
        from gi.repository import GLib, Soup

        text, model = user_data

        if self.geoname_timeout_id is not None:
            GLib.source_remove(self.geoname_timeout_id)
            self.geoname_timeout_id = None
        self.geoname_add_tzdb(text, model)

        if message.status_code == Soup.KnownStatusCode.CANCELLED:
            # Silently ignore cancellation.
            pass
        elif message.status_code != Soup.KnownStatusCode.OK:
            # Log but otherwise ignore failures.
            syslog.syslog(
                'Geoname lookup for "%s" failed: %d %s' %
                (text, message.status_code, message.reason_phrase))
        else:
            try:
                for result in json.loads(message.response_body.data):
                    model.append([
                        result['name'], result['admin1'], result['country'],
                        result['latitude'], result['longitude']])

                # Only cache positive results.
                self.geoname_cache[text] = model

            except ValueError:
                syslog.syslog(
                    'Server return does not appear to be valid JSON.')

        self.city_entry.get_completion().set_model(model)

    def setup_page(self):
        # TODO Put a frame around the completion to add contrast (LP: #605908)
        from gi.repository import Gtk, GLib
        from gi.repository import TimezoneMap
        self.tzdb = ubiquity.tz.Database()
        self.tzmap = TimezoneMap.TimezoneMap()
        self.tzmap.connect('location-changed', self.select_city)
        self.map_window.add(self.tzmap)
        self.tzmap.show()

        def is_separator(m, i):
            return m[i][0] is None

        self.timeout_id = 0

        def queue_entry_changed(entry):
            if self.timeout_id:
                GLib.source_remove(self.timeout_id)
            self.timeout_id = GLib.timeout_add(300, self.changed, entry)

        self.city_entry.connect('changed', queue_entry_changed)
        completion = Gtk.EntryCompletion()
        self.city_entry.set_completion(completion)
        completion.set_inline_completion(True)
        completion.set_inline_selection(True)

        def match_selected(completion, model, iterator):
            # Select on map.
            lat = float(model[iterator][3])
            lon = float(model[iterator][4])
            self.tzmap.set_coords(lon, lat)

            self.city_entry.set_text(model[iterator][0])
            self.city_entry.set_position(-1)
            return True
        completion.connect('match-selected', match_selected)

        def match_func(completion, key, iterator, data):
            # We've already determined that it's a match in entry_changed.
            return True

        def data_func(column, cell, model, iterator, data):
            row = model[iterator]
            if row[1]:
                # The result came from geonames, and thus has an administrative
                # zone attached to it.
                text = '%s <small>(%s, %s)</small>' % (row[0], row[1], row[2])
            else:
                text = '%s <small>(%s)</small>' % (row[0], row[2])
            cell.set_property('markup', text)
        cell = Gtk.CellRendererText()
        completion.pack_start(cell, True)
        completion.set_match_func(match_func, None)
        completion.set_cell_data_func(cell, data_func, None)


class PageKde(plugin.PluginUI):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_timezone'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        try:
            from PyQt4 import uic
            from ubiquity.frontend.kde_components.Timezone import TimezoneMap

            self.page = uic.loadUi('/usr/share/ubiquity/qt/stepLocation.ui')
            self.tzmap = TimezoneMap(self.page.map_frame)
            self.page.map_frame.layout().addWidget(self.tzmap)

            self.tzmap.zoneChanged.connect(self.mapZoneChanged)
            self.page.timezone_zone_combo.currentIndexChanged[int].connect(
                self.regionChanged)
            self.page.timezone_city_combo.currentIndexChanged[int].connect(
                self.cityChanged)
        except Exception as e:
            self.debug('Could not create timezone page: %s', e)
            self.page = None

        self.plugin_widgets = self.page
        self.online = False

    def plugin_set_online_state(self, state):
        self.online = state

    @plugin.only_this_page
    def refresh_timezones(self):
        lang = os.environ['LANG'].split('_', 1)[0]
        shortlist = self.controller.dbfilter.build_shortlist_region_pairs(lang)
        longlist = self.controller.dbfilter.build_region_pairs()

        self.page.timezone_zone_combo.clear()
        for pair in shortlist:
            self.page.timezone_zone_combo.addItem(pair[0], pair[1])
        self.page.timezone_zone_combo.insertSeparator(
            self.page.timezone_zone_combo.count())
        for pair in longlist:
            self.page.timezone_zone_combo.addItem(pair[0], pair[2])

    @plugin.only_this_page
    def populateCities(self, regionIndex):
        self.page.timezone_city_combo.clear()

        code = str(
            self.page.timezone_zone_combo.itemData(regionIndex).toPyObject())
        countries = self.controller.dbfilter.get_countries_for_region(code)
        if not countries:  # must have been a country code itself
            countries = [code]

        shortlist, longlist = self.controller.dbfilter.build_timezone_pairs(
            countries)

        for pair in shortlist:
            self.page.timezone_city_combo.addItem(pair[0], pair[1])
        if shortlist:
            self.page.timezone_city_combo.insertSeparator(
                self.page.timezone_city_combo.count())
        for pair in longlist:
            self.page.timezone_city_combo.addItem(pair[0], pair[1])

        return (len(countries) == 1 and
                self.controller.dbfilter.get_default_for_region(countries[0]))

    # called when the region(zone) combo changes
    @plugin.only_this_page
    def regionChanged(self, regionIndex):
        if self.controller.dbfilter is None:
            return

        self.page.timezone_city_combo.blockSignals(True)
        #self.page.timezone_city_combo.currentIndexChanged[int].disconnect(
        #    self.cityChanged)
        default = self.populateCities(regionIndex)
        self.page.timezone_city_combo.blockSignals(False)
        #self.page.timezone_city_combo.currentIndexChanged[int].connect(
        #    self.cityChanged)

        if default:
            self.tzmap.set_timezone(default)
        else:
            self.cityChanged(0)

    # called when the city combo changes
    def cityChanged(self, cityindex):
        zone = str(
            self.page.timezone_city_combo.itemData(cityindex).toPyObject())
        self.tzmap.zoneChanged.disconnect(self.mapZoneChanged)
        self.tzmap.set_timezone(zone)
        self.tzmap.zoneChanged.connect(self.mapZoneChanged)

    @plugin.only_this_page
    def mapZoneChanged(self, loc, zone):
        self.page.timezone_zone_combo.blockSignals(True)
        self.page.timezone_city_combo.blockSignals(True)

        for i in range(self.page.timezone_zone_combo.count()):
            code = str(self.page.timezone_zone_combo.itemData(i).toPyObject())
            countries = self.controller.dbfilter.get_countries_for_region(code)
            if not countries:  # must have been a country code itself
                countries = [code]
            if loc.country in countries:
                self.page.timezone_zone_combo.setCurrentIndex(i)
                self.populateCities(i)
                break

        for i in range(self.page.timezone_city_combo.count()):
            code = str(self.page.timezone_city_combo.itemData(i).toPyObject())
            if zone == code:
                self.page.timezone_city_combo.setCurrentIndex(i)
                self.cityChanged(i)
                break

        self.page.timezone_zone_combo.blockSignals(False)
        self.page.timezone_city_combo.blockSignals(False)

    def set_timezone(self, timezone):
        self.refresh_timezones()
        self.tzmap.set_timezone(timezone)

    def get_timezone(self):
        return self.tzmap.get_timezone()


class PageDebconf(plugin.PluginUI):
    plugin_title = 'ubiquity/text/timezone_heading_label'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        self.online = False

    def plugin_set_online_state(self, state):
        self.online = state


class PageNoninteractive(plugin.PluginUI):
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        self.online = False

    def plugin_set_online_state(self, state):
        self.online = state

    def set_timezone(self, timezone):
        """Set the current selected timezone."""
        self.timezone = timezone

    def get_timezone(self):
        """Get the current selected timezone."""
        return self.timezone


class Page(plugin.Plugin):
    def prepare(self, unfiltered=False):
        # TODO: This can go away once we have the ability to abort wget/rdate
        if not self.ui.online:
            self.preseed('tzsetup/geoip_server', '')
            self.preseed('clock-setup/ntp', 'false')

        clock_script = '/usr/share/ubiquity/clock-setup'
        env = {'PATH': '/usr/share/ubiquity:' + os.environ['PATH']}

        # TODO: replace with more general version pushed down into
        # is_automatic or similar
        try:
            self.automatic_page = (
                self.db.get("ubiquity/automatic/timezone") == "true")
        except debconf.DebconfError:
            self.automatic_page = False

        if unfiltered:
            # In unfiltered mode, localechooser is responsible for selecting
            # the country, so there's no need to repeat the job here.
            env['TZSETUP_NO_LOCALECHOOSER'] = '1'
            return ([clock_script], ['CAPB', 'PROGRESS'], env)

        self.timezones = []
        self.regions = {}
        self.tzdb = ubiquity.tz.Database()
        self.multiple = False
        try:
            # Strip .UTF-8 from locale, icu doesn't parse it
            locale = os.environ['LANG'].rsplit('.', 1)[0]
            self.collator = icu.Collator.createInstance(icu.Locale(locale))
        except:
            self.collator = None
        if self.is_automatic or self.automatic_page:
            if self.db.fget('time/zone', 'seen') == 'true':
                self.set_di_country(self.db.get('time/zone'))
        else:
            self.db.fset('time/zone', 'seen', 'false')
            cc = self.db.get('debian-installer/country')
            try:
                self.db.get('tzsetup/country/%s' % cc)
                # ... and if that succeeded:
                self.multiple = True
            except debconf.DebconfError:
                pass
        self.preseed('tzsetup/selected', 'false')
        questions = ['^time/zone$', '^tzsetup/detected$', 'CAPB', 'PROGRESS']
        return [clock_script], questions, env

    def capb(self, capabilities):
        self.frontend.debconf_progress_cancellable(
            'progresscancel' in capabilities)

    def run(self, priority, question):
        if question == 'tzsetup/detected':
            zone = self.db.get('time/zone')
            self.ui.set_timezone(zone)
        elif question == 'time/zone':
            if self.multiple:
                # Work around a debconf bug: REGISTER does not appear to
                # give a newly-registered question the same default as the
                # question associated with its template, unless we also
                # RESET it.
                self.db.reset(question)
            zone = self.db.get(question)
            # Some countries don't have a default zone, so just pick the
            # first choice in the list.
            if not zone:
                choices_c = self.choices_untranslated(question)
                if choices_c:
                    zone = choices_c[0]
            self.ui.set_timezone(zone)

        if self.automatic_page:
            # TODO: invade frontend's privacy to avoid entering infinite
            # loop when trying to back up over timezone question (which
            # isn't possible anyway since it's just after partitioning);
            # this needs to be tidied up substantially when generalising
            # ubiquity/automatic/*
            self.frontend.backup = False
            return True
        else:
            return plugin.Plugin.run(self, priority, question)

    def get_default_for_region(self, region):
        try:
            return self.db.get('tzsetup/country/%s' % region)
        except debconf.DebconfError:
            return None

    def collation_key(self, s):
        if self.collator:
            try:
                return self.collator.getCollationKey(s[0]).getByteArray()
            except:
                pass
        return s[0]

    def get_countries_for_region(self, region):
        if region in self.regions:
            return self.regions[region]

        try:
            codes = self.choices_untranslated(
                'localechooser/countrylist/%s' % region)
        except debconf.DebconfError:
            codes = []
        self.regions[region] = codes
        return codes

    # Returns ['timezone', ...]
    def build_timezone_list(self):
        total = []
        continents = self.choices_untranslated('localechooser/continentlist')
        for continent in continents:
            country_codes = self.choices_untranslated(
                'localechooser/countrylist/%s' % continent.replace(' ', '_'))
            for c in country_codes:
                shortlist = self.build_shortlist_timezone_pairs(c, sort=False)
                longlist = self.build_longlist_timezone_pairs(c, sort=False)
                shortcopy = shortlist[:]
                # TODO set() | set() instead.
                for short_item in shortcopy:
                    for long_item in longlist:
                        if short_item[1] == long_item[1]:
                            shortlist.remove(short_item)
                            break
                total += shortlist + longlist
        return total

    # Returns [('translated country name', None, 'region code')...] list
    def build_region_pairs(self):
        continents = self.choices_display_map('localechooser/continentlist')
        names, codes = list(zip(*continents.items()))
        codes = [c.replace(' ', '_') for c in codes]

        nones = [None for _ in continents]
        pairs = list(zip(names, nones, codes))
        pairs.sort(key=self.collation_key)
        return pairs

    # Returns [('translated short list of countries', 'timezone')...] list
    def build_shortlist_region_pairs(self, language_code):
        try:
            shortlist = self.choices_display_map(
                'localechooser/shortlist/%s' % language_code)
            # Remove any 'other' entry
            for pair in shortlist.items():
                if pair[1] == 'other':
                    del shortlist[pair[0]]
                    break
            names, codes = list(zip(*shortlist.items()))
            nones = [None for _ in names]
            shortlist = list(zip(names, codes, nones))
            shortlist.sort(key=self.collation_key)
            return shortlist
        except debconf.DebconfError:
            return []

    # Returns (shortlist, longlist)
    def build_timezone_pairs(self, country_codes):
        if len(country_codes) == 1:
            shortlist = self.build_shortlist_timezone_pairs(country_codes[0])
        else:
            shortlist = []

        longlist = []
        for country_code in country_codes:
            longlist += self.build_longlist_timezone_pairs(
                country_code, sort=False)
        longlist.sort(key=self.collation_key)

        # There may be duplicate entries in the shortlist and longlist.
        # Basically, the shortlist is most useful when there are non-city
        # timezones that may be more familiar to denizens of that country.
        # Big examples are the US in which people tend to think in terms of
        # Eastern/Mountain/etc.  If we see a match in tz code, prefer the
        # longlist's translation and strip it from the shortlist.
        # longlist tends to be more complete in terms of translation coverage
        # (i.e. libicu is more translated than tzsetup)
        shortcopy = shortlist[:]
        for short_item in shortcopy:
            for long_item in longlist:
                if short_item[1] == long_item[1]:
                    shortlist.remove(short_item)
                    break

        return (shortlist, longlist)

    def build_shortlist_timezone_pairs(self, country_code, sort=True):
        try:
            shortlist = self.choices_display_map(
                'tzsetup/country/%s' % country_code)
            for pair in list(shortlist.items()):
                # Remove any 'other' entry, we don't need it
                if pair[1] == 'other':
                    del shortlist[pair[0]]
            shortlist = list(shortlist.items())
            if sort:
                shortlist.sort(key=self.collation_key)
            return shortlist
        except debconf.DebconfError:
            return []

    def get_country_name(self, country):
        # Relatively expensive algorithmically, but we don't call this often.
        try:
            continents = self.choices_untranslated(
                'localechooser/continentlist')
            for continent in continents:
                choices = self.choices_display_map(
                    'localechooser/countrylist/%s' %
                    continent.replace(' ', '_'))
                for name, code in choices.items():
                    if code == country:
                        return name
        except debconf.DebconfError as e:
            print("Couldn't get country name for %s: %s" % (country, e))
        return None

    def get_city_name_from_tzdata(self, tz):
        city = tz.split('/', 1)[1]
        # Iterate through tzdata's regions, check each region's tz list for
        # our city.  Like get_country_name, this is inefficient (we could
        # cache this info), but we don't need to run this often.
        try:
            areas = self.choices_untranslated('tzdata/Areas')
            for area in areas:
                zones = self.choices_display_map('tzdata/Zones/%s' % area)
                for name, code in zones.items():
                    if code == city:
                        return name
        except debconf.DebconfError as e:
            print("Couldn't get city name for %s: %s" % (tz, e))
        return None

    def get_fallback_translation_for_tz(self, country, tz):
        # We want to return either 'Country' or 'Country (City)', translated
        # First, get country name.  We need that regardless
        country_name = self.get_country_name(country)
        if country_name is None:
            return None
        show_city = len(self.tzdb.cc_to_locs[country]) > 1
        if show_city:
            # First, try tzdata's translation.
            city_name = self.get_city_name_from_tzdata(tz)
            if city_name is None:
                city_name = tz  # fall back to ASCII name
            city_name = city_name.split('/')[-1]
            return "%s (%s)" % (country_name, city_name)
        else:
            return country_name

    # Returns [('translated long list of timezones', 'timezone')...] list
    def build_longlist_timezone_pairs(self, country_code, sort=True):
        if 'LANG' not in os.environ:
            return []  # ?!
        locale = os.environ['LANG'].rsplit('.', 1)[0]
        tz_format = icu.SimpleDateFormat('VVVV', icu.Locale(locale))
        now = time.time() * 1000
        rv = []
        try:
            locs = self.tzdb.cc_to_locs[country_code]  # BV failed?
        except:
            # Some countries in tzsetup don't exist in zone.tab...
            # Specifically BV (Bouvet Island) and
            # HM (Heard and McDonald Islands).  Both are uninhabited.
            locs = []
        for location in locs:
            timezone = icu.TimeZone.createTimeZone(location.zone)
            if timezone.getID() == 'Etc/Unknown':
                translated = None
            else:
                tz_format.setTimeZone(timezone)
                translated = tz_format.format(now)
            # Check if icu had a valid translation for this timezone.  If it
            # doesn't, the returned string will look like GMT+0002 or somesuch.
            # Sometimes the GMT is translated (like in Chinese), so we check
            # for the number part.  icu does not indicate a 'translation
            # failure' like this in any way...
            if (translated is None or
                    re.search('.*[-+][0-9][0-9]:?[0-9][0-9]$', translated)):
                # Wasn't something that icu understood...
                name = self.get_fallback_translation_for_tz(
                    country_code, location.zone)
                rv.append((name, location.zone))
            else:
                rv.append((translated, location.zone))
        if sort:
            rv.sort(key=self.collation_key)
        return rv

    # Returns [('translated long list of timezones', 'timezone')...] list
    def build_longlist_timezone_pairs_by_continent(self, continent):
        if 'LANG' not in os.environ:
            return []  # ?
        rv = []
        try:
            regions = self.choices_untranslated(
                'localechooser/countrylist/%s' % continent)
            for region in regions:
                rv += self.build_longlist_timezone_pairs(region, sort=False)
            rv.sort(key=self.collation_key)
        except debconf.DebconfError:
            pass
        return rv

    def set_di_country(self, zone):
        location = self.tzdb.get_loc(zone)
        if location:
            self.preseed('debian-installer/country', location.country)

    def ok_handler(self):
        zone = self.ui.get_timezone()
        if zone is None:
            zone = self.db.get('time/zone')
        else:
            self.preseed('time/zone', zone)
        self.set_di_country(zone)
        plugin.Plugin.ok_handler(self)

    def cleanup(self):
        plugin.Plugin.cleanup(self)
        self.ui.controller.set_locale(i18n.reset_locale(self.frontend))


class Install(plugin.InstallPlugin):
    def prepare(self, unfiltered=False):
        tzsetup_script = '/usr/lib/ubiquity/tzsetup/post-base-installer'
        clock_script = '/usr/share/ubiquity/clock-setup-apply'

        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            tzsetup_script += '-oem'

        return (['sh', '-c', '%s && %s' % (tzsetup_script, clock_script)], [])

    def install(self, target, progress, *args, **kwargs):
        progress.info('ubiquity/install/timezone')
        return plugin.InstallPlugin.install(
            self, target, progress, *args, **kwargs)
