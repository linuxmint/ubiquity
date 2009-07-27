# -*- coding: utf-8 -*-
#
# «gtk_ui» - GTK user interface
#
# Copyright (C) 2005 Junta de Andalucía
# Copyright (C) 2005, 2006, 2007, 2008, 2009 Canonical Ltd.
#
# Authors:
#
# - Javier Carranza <javier.carranza#interactors._coop>
# - Juan Jesús Ojeda Croissier <juanje#interactors._coop>
# - Antonio Olmo Titos <aolmo#emergya._info>
# - Gumer Coronel Pérez <gcoronel#emergya._info>
# - Colin Watson <cjwatson@ubuntu.com>
# - Evan Dandrea <evand@ubuntu.com>
# - Mario Limonciello <superm1@ubuntu.com>
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

import sys
import os
import datetime
import subprocess
import math
import traceback
import syslog
import atexit
import signal
import xml.sax.saxutils
import gettext

import pygtk
pygtk.require('2.0')
import pango
import gobject
import gtk.glade

import debconf

from ubiquity import filteredcommand, gconftool, i18n, osextras, validation, \
                     timezone_map, segmented_bar, wrap_label
from ubiquity.misc import *
from ubiquity.components import console_setup, language, timezone, usersetup, \
                                partman, partman_commit, \
                                summary, install, migrationassistant
import ubiquity.emap
import ubiquity.tz
import ubiquity.progressposition
from ubiquity.frontend.base import BaseFrontend

# Define global path
PATH = '/usr/share/ubiquity'

# Define glade path
GLADEDIR = os.path.join(PATH, 'glade')

# Define locale path
LOCALEDIR = "/usr/share/locale"

BREADCRUMB_STEPS = {
    "stepLanguage": 1,
    "stepLocation": 2,
    "stepKeyboardConf": 3,
    "stepPartAuto": 4,
    "stepPartAdvanced": 4,
    "stepUserInfo": 5,
    "stepMigrationAssistant": 6,
    "stepReady": 7
}
BREADCRUMB_MAX_STEP = 7

# Define what pages of the UI we want to load.  Note that most of these pages
# are required for the install to complete successfully.
SUBPAGES = [
    "stepWelcome",
    "stepLanguage",
    "stepLocation",
    "stepKeyboardConf",
    "stepPartAuto",
    "stepPartAdvanced",
    "stepUserInfo",
    "stepMigrationAssistant",
    "stepReady"
]

class Wizard(BaseFrontend):

    def __init__(self, distro):
        def add_subpage(self, steps, name):
            """Inserts a subpage into the notebook.  This assumes the file
            shares the same base name as the page you are looking for."""
            gladefile = GLADEDIR + '/' + name + '.glade'
            gladexml = gtk.glade.XML(gladefile, name)
            widget = gladexml.get_widget(name)
            steps.append_page(widget)
            add_widgets(self, gladexml)
            gladexml.signal_autoconnect(self)

        def add_widgets(self, glade):
            """Makes all widgets callable by the toplevel."""
            for widget in glade.get_widget_prefix(""):
                self.all_widgets.add(widget)
                setattr(self, widget.get_name(), widget)
                # We generally want labels to be selectable so that people can
                # easily report problems in them
                # (https://launchpad.net/bugs/41618), but GTK+ likes to put
                # selectable labels in the focus chain, and I can't seem to turn
                # this off in glade and have it stick. Accordingly, make sure
                # labels are unfocusable here.
                if isinstance(widget, gtk.Label):
                    widget.set_property('can-focus', False)

        BaseFrontend.__init__(self, distro)

        self.previous_excepthook = sys.excepthook
        sys.excepthook = self.excepthook

        # declare attributes
        self.all_widgets = set()
        self.gconf_previous = {}
        self.thunar_previous = {}
        self.language_questions = ('live_installer',
                                   'welcome_heading_label', 'welcome_text_label',
                                   'oem_id_label',
                                   'release_notes_label', 'release_notes_url',
                                   'step_label',
                                   'quit', 'back', 'next',
                                   'warning_dialog', 'warning_dialog_label',
                                   'cancelbutton', 'exitbutton')
        self.current_page = None
        self.first_seen_page = None
        self.backup = None
        self.allowed_change_step = True
        self.allowed_go_backward = True
        self.allowed_go_forward = True
        self.stay_on_page = False
        self.progress_position = ubiquity.progressposition.ProgressPosition()
        self.progress_cancelled = False
        self.default_keyboard_layout = None
        self.default_keyboard_variant = None
        self.autopartition_extras = {}
        self.resize_min_size = None
        self.resize_max_size = None
        self.resize_orig_size = None
        self.resize_path = ''
        self.new_size_scale = None
        self.ma_choices = []
        self.username_combo = None
        self.username_changed_id = None
        self.hostname_changed_id = None
        self.username_edited = False
        self.hostname_edited = False
        self.installing = False
        self.installing_no_return = False
        self.returncode = 0
        self.partition_bars = {}
        # FIXME: Grab this from the GTK theme.
	self.release_color = '87cf3e'
	self.auto_colors = ['8b94ef', 'eeef2f', 'ef8b8b']
	#self.release_color = 'D07316'
	#self.auto_colors = ['3465a4', '73d216', 'f57900']
        self.dev_colors = {}
        self.segmented_bar_vbox = None
        self.format_warnings = {}
        self.format_warning = None
        self.format_warning_align = None

        self.laptop = execute("laptop-detect")

        # set default language
        dbfilter = language.Language(self, self.debconf_communicator())
        dbfilter.cleanup()
        dbfilter.db.shutdown()

        gobject.timeout_add(30000, self.poke_screensaver)

        # To get a "busy mouse":
        self.watch = gtk.gdk.Cursor(gtk.gdk.WATCH)

        # set custom language
        self.set_locales()

        gtk.window_set_default_icon_from_file('/usr/share/pixmaps/'
                                              'ubiquity.png')

        # load the main interface
        self.glade = gtk.glade.XML('%s/ubiquity.glade' % GLADEDIR)
        add_widgets(self, self.glade)

        steps = self.glade.get_widget("steps")
        for page in SUBPAGES:
            add_subpage(self, steps, page)

        if 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
            self.pages = [language.Language, timezone.Timezone,
                console_setup.ConsoleSetup, partman.Partman,
                usersetup.UserSetup, migrationassistant.MigrationAssistant,
                summary.Summary]
        else:
            self.pages = [language.Language, timezone.Timezone,
                console_setup.ConsoleSetup, partman.Partman,
                usersetup.UserSetup, summary.Summary]

        self.translate_widgets()

        self.customize_installer()


    def excepthook(self, exctype, excvalue, exctb):
        """Crash handler."""

        if (issubclass(exctype, KeyboardInterrupt) or
            issubclass(exctype, SystemExit)):
            return

        tbtext = ''.join(traceback.format_exception(exctype, excvalue, exctb))
        syslog.syslog(syslog.LOG_ERR,
                      "Exception in GTK frontend (invoking crash handler):")
        for line in tbtext.split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
        print >>sys.stderr, ("Exception in GTK frontend"
                             " (invoking crash handler):")
        print >>sys.stderr, tbtext

        self.post_mortem(exctype, excvalue, exctb)

        if os.path.exists('/usr/share/apport/apport-gtk'):
            self.previous_excepthook(exctype, excvalue, exctb)
        else:
            self.crash_detail_label.set_text(tbtext)
            self.crash_dialog.run()
            self.crash_dialog.hide()

            sys.exit(1)


    def thunar_set_volmanrc (self, fields):
        previous = {}
        if 'SUDO_USER' in os.environ:
            thunar_dir = os.path.expanduser('~%s/.config/Thunar' %
                                            os.environ['SUDO_USER'])
        else:
            thunar_dir = os.path.expanduser('~/.config/Thunar')
        if os.path.isdir(thunar_dir):
            import ConfigParser
            thunar_volmanrc = '%s/volmanrc' % thunar_dir
            parser = ConfigParser.RawConfigParser()
            parser.optionxform = str # case-sensitive
            parser.read(thunar_volmanrc)
            if not parser.has_section('Configuration'):
                parser.add_section('Configuration')
            for key, value in fields.iteritems():
                if parser.has_option('Configuration', key):
                    previous[key] = parser.get('Configuration', key)
                else:
                    previous[key] = 'TRUE'
                parser.set('Configuration', key, value)
            try:
                thunar_volmanrc_new = open('%s.new' % thunar_volmanrc, 'w')
                parser.write(thunar_volmanrc_new)
                thunar_volmanrc_new.close()
                os.rename('%s.new' % thunar_volmanrc, thunar_volmanrc)
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                pass
        return previous

    # Disable gnome-volume-manager automounting to avoid problems during
    # partitioning.
    def disable_volume_manager(self):
        gvm_root = '/desktop/gnome/volume_manager'
        gvm_automount_drives = '%s/automount_drives' % gvm_root
        gvm_automount_media = '%s/automount_media' % gvm_root
        volumes_visible = '/apps/nautilus/desktop/volumes_visible'
        media_automount = '/apps/nautilus/preferences/media_automount'
        media_automount_open = '/apps/nautilus/preferences/media_automount_open'
        media_autorun_never = '/apps/nautilus/preferences/media_autorun_never'
        self.gconf_previous = {}
        for gconf_key in (gvm_automount_drives, gvm_automount_media,
                          volumes_visible,
                          media_automount, media_automount_open):
            self.gconf_previous[gconf_key] = gconftool.get(gconf_key)
            if self.gconf_previous[gconf_key] != 'false':
                gconftool.set(gconf_key, 'bool', 'false')
        for gconf_key in (media_autorun_never,):
            self.gconf_previous[gconf_key] = gconftool.get(gconf_key)
            if self.gconf_previous[gconf_key] != 'true':
                gconftool.set(gconf_key, 'bool', 'true')

        self.thunar_previous = self.thunar_set_volmanrc(
            {'AutomountDrives': 'FALSE', 'AutomountMedia': 'FALSE'})

        atexit.register(self.enable_volume_manager)

    def enable_volume_manager(self):
        gvm_root = '/desktop/gnome/volume_manager'
        gvm_automount_drives = '%s/automount_drives' % gvm_root
        gvm_automount_media = '%s/automount_media' % gvm_root
        volumes_visible = '/apps/nautilus/desktop/volumes_visible'
        media_automount = '/apps/nautilus/preferences/media_automount'
        media_automount_open = '/apps/nautilus/preferences/media_automount_open'
        media_autorun_never = '/apps/nautilus/preferences/media_autorun_never'
        for gconf_key in (gvm_automount_drives, gvm_automount_media,
                          volumes_visible,
                          media_automount, media_automount_open):
            if self.gconf_previous[gconf_key] == '':
                gconftool.unset(gconf_key)
            elif self.gconf_previous[gconf_key] != 'false':
                gconftool.set(gconf_key, 'bool',
                              self.gconf_previous[gconf_key])
        for gconf_key in (media_autorun_never,):
            if self.gconf_previous[gconf_key] == '':
                gconftool.unset(gconf_key)
            elif self.gconf_previous[gconf_key] != 'true':
                gconftool.set(gconf_key, 'bool',
                              self.gconf_previous[gconf_key])

        if self.thunar_previous:
            self.thunar_set_volmanrc(self.thunar_previous)


    def run(self):
        """run the interface."""

        if os.getuid() != 0:
            title = ('This installer must be run with administrative '
                     'privileges, and cannot continue without them.')
            dialog = gtk.MessageDialog(self.live_installer, gtk.DIALOG_MODAL,
                                       gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
                                       title)
            dialog.run()
            sys.exit(1)

        self.disable_volume_manager()

        # show interface
        got_intro = self.show_intro()
        self.allow_change_step(True)

        # Declare SignalHandler
        self.glade.signal_autoconnect(self)

        # Some signals need to be connected by hand so that we have the
        # handler ids.
        self.username_changed_id = self.username.connect(
            'changed', self.on_username_changed)
        self.hostname_changed_id = self.hostname.connect(
            'changed', self.on_hostname_changed)

        self.pagesindex = 0
        pageslen = len(self.pages)

        if 'UBIQUITY_AUTOMATIC' in os.environ:
            got_intro = False
            self.debconf_progress_start(0, pageslen,
                self.get_string('ubiquity/install/checking'))
            self.refresh()

        # Start the interface
        if got_intro:
            global BREADCRUMB_STEPS, BREADCRUMB_MAX_STEP
            for step in BREADCRUMB_STEPS:
                BREADCRUMB_STEPS[step] += 1
            BREADCRUMB_STEPS["stepWelcome"] = 1
            BREADCRUMB_MAX_STEP += 1
            first_step = self.stepWelcome
        else:
            first_step = self.stepLanguage
        self.set_current_page(self.steps.page_num(first_step))
        if got_intro:
            # intro_label was the only focusable widget, but got can-focus
            # removed, so we end up with no input focus and thus pressing
            # Enter doesn't activate the default widget. Work around this.
            self.next.grab_focus()
        else:
            # Similarly, the Quit button seems to end up with focus by
            # default, but we'd rather a navigable widget had it.
            self.language_treeview.grab_focus()

        if not 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
            self.steps.remove_page(self.steps.page_num(self.stepMigrationAssistant))
            for step in BREADCRUMB_STEPS:
                if (BREADCRUMB_STEPS[step] >
                    BREADCRUMB_STEPS["stepMigrationAssistant"]):
                    BREADCRUMB_STEPS[step] -= 1
            BREADCRUMB_MAX_STEP -= 1

        if got_intro:
            gtk.main()

        while(self.pagesindex < pageslen):
            if self.current_page == None:
                break

            old_dbfilter = self.dbfilter
            self.dbfilter = self.pages[self.pagesindex](self)

            self.prepare_page()

            # Non-debconf steps are no longer possible as the interface is now
            # driven by whether there is a question to ask.
            if self.dbfilter is not None and self.dbfilter != old_dbfilter:
                self.allow_change_step(False)
                self.dbfilter.start(auto_process=True)
            gtk.main()

            if self.backup or self.dbfilter_handle_status():
                if self.installing:
                    self.progress_loop()
                elif self.current_page is not None and not self.backup:
                    self.process_step()
                    if not self.stay_on_page:
                        self.pagesindex = self.pagesindex + 1
                    if 'UBIQUITY_AUTOMATIC' in os.environ:
                        # if no debconf_progress, create another one, set start to pageindex
                        self.debconf_progress_step(1)
                        self.refresh()
                if self.backup:
                    if self.pagesindex > 0:
                        step = self.step_name(self.steps.get_current_page())
                        if not step == 'stepPartAdvanced':
                            self.pagesindex = self.pagesindex - 1

            while gtk.events_pending():
                gtk.main_iteration()

            # needed to be here for --automatic as there might not be any
            # current page in the event all of the questions have been
            # preseeded.
            if self.pagesindex == pageslen:
                # Ready to install
                self.live_installer.hide()
                self.current_page = None
                self.installing = True
                self.progress_loop()
        return self.returncode


    def customize_installer(self):
        """Initial UI setup."""

        PIXMAPSDIR = os.path.join(PATH, 'pixmaps', self.distro)

        # set pixmaps
        if ( gtk.gdk.get_default_root_window().get_screen().get_width() > 1024 ):
            logo = os.path.join(PIXMAPSDIR, "logo_1280.jpg")
            photo = os.path.join(PIXMAPSDIR, "photo_1280.jpg")
        else:
            logo = os.path.join(PIXMAPSDIR, "logo_1024.jpg")
            photo = os.path.join(PIXMAPSDIR, "photo_1024.jpg")
        if not os.path.exists(logo):
            logo = None
        if not os.path.exists(photo):
            photo = None

        self.logo_image.set_from_file(logo)
        self.photo.set_from_file(photo)

        if 'UBIQUITY_ONLY' in os.environ:
            self.live_installer.fullscreen()

        if self.oem_config:
            self.live_installer.set_title(self.get_string('oem_config_title'))
            self.oem_id_vbox.show()
            try:
                self.oem_id_entry.set_text(
                    self.debconf_operation('get', 'oem-config/id'))
            except debconf.DebconfError:
                pass
            self.fullname.set_text('OEM Configuration (temporary user)')
            self.fullname.set_editable(False)
            self.fullname.set_sensitive(False)
            self.username.set_text('oem')
            self.username.set_editable(False)
            self.username.set_sensitive(False)
            self.username_edited = True
            if self.laptop:
                self.hostname.set_text('oem-laptop')
            else:
                self.hostname.set_text('oem-desktop')
            self.hostname_edited = True
            self.login_vbox.hide()
            # The UserSetup component takes care of preseeding passwd/user-uid.
            execute_root('apt-install', 'oem-config-gtk')

        if not 'UBIQUITY_AUTOMATIC' in os.environ:
            self.live_installer.show()
        self.allow_change_step(False)

        try:
            release_notes = open('/cdrom/.disk/release_notes_url')
            self.release_notes_url.set_uri(
                release_notes.read().rstrip('\n'))
            release_notes.close()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.release_notes_vbox.hide()
        gtk.link_button_set_uri_hook(self.link_button_browser)

        if 'UBIQUITY_OLD_TZMAP' in os.environ:
            self.tzmap = TimezoneMap(self)
            self.tzmap.tzmap.show()
        else:
            self.tzdb = ubiquity.tz.Database()
            self.tzmap = timezone_map.TimezoneMap(self.tzdb, '/usr/share/ubiquity/pixmaps/timezone')
            self.tzmap.connect('city-selected', self.select_city)
            self.timezone_map_window.add(self.tzmap)
            self.setup_timezone_page()
            self.tzmap.show()

        self.action_bar = segmented_bar.SegmentedBarSlider()
        self.action_bar.h_padding = self.action_bar.bar_height / 2
        sw = gtk.ScrolledWindow()
        sw.add_with_viewport(self.action_bar)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
        sw.child.set_shadow_type(gtk.SHADOW_NONE)
        sw.show_all()
        self.action_bar_eb.add(sw)
        
        self.before_bar = segmented_bar.SegmentedBar()
        self.before_bar.h_padding = self.before_bar.bar_height / 2
        sw = gtk.ScrolledWindow()
        sw.add_with_viewport(self.before_bar)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
        sw.child.set_shadow_type(gtk.SHADOW_NONE)
        sw.show_all()
        self.before_bar_eb.add(sw)

        if 'UBIQUITY_DEBUG' in os.environ:
            self.password_debug_warning_label.show()

        self.previous_partitioning_page = \
            self.steps.page_num(self.stepPartAuto)

        # set initial bottom bar status
        self.allow_go_backward(False)

    def setup_timezone_page(self):

        renderer = gtk.CellRendererText()
        self.timezone_zone_combo.pack_start(renderer, True)
        self.timezone_zone_combo.add_attribute(renderer, 'text', 0)
        list_store = gtk.ListStore(gobject.TYPE_STRING)
        self.timezone_zone_combo.set_model(list_store)
        self.timezone_zone_combo.connect('changed', self.zone_combo_selection_changed)
        self.timezone_city_combo.connect('changed', self.city_combo_selection_changed)

        renderer = gtk.CellRendererText()
        self.timezone_city_combo.pack_start(renderer, True)
        self.timezone_city_combo.add_attribute(renderer, 'text', 0)
        city_store = gtk.ListStore(gobject.TYPE_STRING)
        self.timezone_city_combo.set_model(city_store)
        
        self.regions = {}
        for location in self.tzdb.locations:
            region, city = location.zone.replace('_', ' ').split('/', 1)
            if region in self.regions:
                self.regions[region].append(city)
            else:
                self.regions[region] = [city]

        r = self.regions.keys()
        r.sort()
        for region in r:
            list_store.append([region])

    def zone_combo_selection_changed(self, widget):
        i = self.timezone_zone_combo.get_active()
        m = self.timezone_zone_combo.get_model()
        region = m[i][0]
        
        m = self.timezone_city_combo.get_model()
        m.clear()
        for city in self.regions[region]:
            m.append([city])

    def city_combo_selection_changed(self, widget):
        i = self.timezone_zone_combo.get_active()
        m = self.timezone_zone_combo.get_model()
        region = m[i][0]
        
        i = self.timezone_city_combo.get_active()
        if i < 0:
            # There's no selection yet.
            return
        m = self.timezone_city_combo.get_model()
        city = m[i][0].replace(' ', '_')
        city = region + '/' + city
        self.tzmap.select_city(city)

    def select_city(self, widget, city):
        region, city = city.replace('_', ' ').split('/', 1)
        m = self.timezone_zone_combo.get_model()
        iterator = m.get_iter_first()
        while iterator:
            if m[iterator][0] == region:
                self.timezone_zone_combo.set_active_iter(iterator)
                break
            iterator = m.iter_next(iterator)
        
        m = self.timezone_city_combo.get_model()
        iterator = m.get_iter_first()
        while iterator:
            if m[iterator][0] == city:
                self.timezone_city_combo.set_active_iter(iterator)
                break
            iterator = m.iter_next(iterator)


    def poke_screensaver(self):
        """Attempt to make sure that the screensaver doesn't kick in."""
        if os.path.exists('/usr/bin/gnome-screensaver-command'):
            command = ["gnome-screensaver-command", "--poke"]
        elif os.path.exists('/usr/bin/xscreensaver-command'):
            command = ["xscreensaver-command", "--deactivate"]
        else:
            return

        env = ['LC_ALL=C']
        for key, value in os.environ.iteritems():
            if key != 'LC_ALL':
                env.append('%s=%s' % (key, value))
        gobject.spawn_async(command, envp=env,
                            flags=(gobject.SPAWN_SEARCH_PATH |
                                   gobject.SPAWN_STDOUT_TO_DEV_NULL |
                                   gobject.SPAWN_STDERR_TO_DEV_NULL))
        return True


    def set_window_hints(self, widget):
        if 'UBIQUITY_ONLY' in os.environ:
            # Disable minimise button.
            widget.window.set_functions(
                gtk.gdk.FUNC_RESIZE | gtk.gdk.FUNC_MOVE)


    def set_locales(self):
        """internationalization config. Use only once."""

        domain = self.distro + '-installer'
        gettext.bindtextdomain(domain, LOCALEDIR)
        gtk.glade.bindtextdomain(domain, LOCALEDIR )
        gtk.glade.textdomain(domain)
        gettext.textdomain(domain)
        gettext.install(domain, LOCALEDIR, unicode=1)


    def translate_widgets(self):
        if self.locale is None:
            languages = []
        else:
            languages = [self.locale]
        core_names = ['ubiquity/text/%s' % q for q in self.language_questions]
        core_names.append('ubiquity/text/oem_config_title')
        for stock_item in ('cancel', 'close', 'go-back', 'go-forward',
                           'ok', 'quit'):
            core_names.append('ubiquity/imported/%s' % stock_item)
        i18n.get_translations(languages=languages, core_names=core_names)

        for widget in self.all_widgets:
            self.translate_widget(widget, self.locale)

        self.partition_button_undo.set_label(
            self.get_string('partman/text/undo_everything'))

    def translate_widget(self, widget, lang):
        if isinstance(widget, gtk.Button) and widget.get_use_stock():
            widget.set_label(widget.get_label())

        text = self.get_string(widget.get_name(), lang)
        if text is None:
            return
        name = widget.get_name()

        if isinstance(widget, gtk.Label):
            if name == 'step_label':
                global BREADCRUMB_STEPS, BREADCRUMB_MAX_STEP
                curstep = '?'
                if self.current_page is not None:
                    current_name = self.step_name(self.current_page)
                    if current_name in BREADCRUMB_STEPS:
                        curstep = str(BREADCRUMB_STEPS[current_name])
                text = text.replace('${INDEX}', curstep)
                text = text.replace('${TOTAL}', str(BREADCRUMB_MAX_STEP))
            widget.set_text(text)

            # Ideally, these attributes would be in the glade file somehow ...
            textlen = len(text.encode("UTF-8"))
            if 'heading_label' in name:
                attrs = pango.AttrList()
                attrs.insert(pango.AttrScale(pango.SCALE_LARGE, 0, textlen))
                attrs.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, textlen))
                widget.set_attributes(attrs)
            elif 'extra_label' in name:
                attrs = pango.AttrList()
                attrs.insert(pango.AttrScale(pango.SCALE_SMALL, 0, textlen))
                widget.set_attributes(attrs)
            elif ('group_label' in name or 'warning_label' in name or
                  name in ('drives_label', 'partition_method_label')):
                attrs = pango.AttrList()
                attrs.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, textlen))
                widget.set_attributes(attrs)

        elif isinstance(widget, gtk.Button):
            # TODO evand 2007-06-26: LP #122141 causes a crash unless we keep a
            # reference to the button image.
            tempref = widget.get_image()

            question = i18n.map_widget_name(widget.get_name())
            widget.set_label(text)
            
            # Workaround for radio button labels disappearing on second
            # translate when not visible. LP: #353090
            widget.realize()
            
            if question.startswith('ubiquity/imported/'):
                stock_id = question[18:]
                widget.set_use_stock(False)
                widget.set_image(gtk.image_new_from_stock(
                    'gtk-%s' % stock_id, gtk.ICON_SIZE_BUTTON))

        elif isinstance(widget, gtk.Window):
            if name == 'live_installer' and self.oem_config:
                text = self.get_string('oem_config_title', lang)
            widget.set_title(text)


    def allow_change_step(self, allowed):
        if allowed:
            cursor = None
        else:
            cursor = self.watch
        if self.live_installer.window:
            self.live_installer.window.set_cursor(cursor)
        self.back.set_sensitive(allowed and self.allowed_go_backward)
        self.next.set_sensitive(allowed and self.allowed_go_forward)
        # Work around http://bugzilla.gnome.org/show_bug.cgi?id=56070
        if (self.back.get_property('visible') and
            allowed and self.allowed_go_backward):
            self.back.hide()
            self.back.show()
        if (self.next.get_property('visible') and
            allowed and self.allowed_go_forward):
            self.next.hide()
            self.next.show()
            self.next.grab_default()
        self.allowed_change_step = allowed

    def allow_go_backward(self, allowed):
        self.back.set_sensitive(allowed and self.allowed_change_step)
        # Work around http://bugzilla.gnome.org/show_bug.cgi?id=56070
        if (self.back.get_property('visible') and
            allowed and self.allowed_change_step):
            self.back.hide()
            self.back.show()
        self.allowed_go_backward = allowed

    def allow_go_forward(self, allowed):
        self.next.set_sensitive(allowed and self.allowed_change_step)
        # Work around http://bugzilla.gnome.org/show_bug.cgi?id=56070
        if (self.next.get_property('visible') and
            allowed and self.allowed_change_step):
            self.next.hide()
            self.next.show()
            self.next.grab_default()
        self.allowed_go_forward = allowed


    def dbfilter_handle_status(self):
        """If a dbfilter crashed, ask the user if they want to continue anyway.

        Returns True to continue, or False to try again."""

        if not self.dbfilter_status or self.current_page is None:
            return True

        syslog.syslog('dbfilter_handle_status: %s' % str(self.dbfilter_status))

        # TODO cjwatson 2007-04-04: i18n
        text = ('%s failed with exit code %s. Further information may be '
                'found in /var/log/syslog. Do you want to try running this '
                'step again before continuing? If you do not, your '
                'installation may fail entirely or may be broken.' %
                (self.dbfilter_status[0], self.dbfilter_status[1]))
        dialog = gtk.Dialog('%s crashed' % self.dbfilter_status[0],
                            self.live_installer, gtk.DIALOG_MODAL,
                            (gtk.STOCK_QUIT, gtk.RESPONSE_CLOSE,
                             'Continue anyway', 1,
                             'Try again', 2))
        self.dbfilter_status = None
        label = gtk.Label(text)
        label.set_line_wrap(True)
        label.set_selectable(True)
        dialog.vbox.add(label)
        dialog.show_all()
        response = dialog.run()
        dialog.hide()
        syslog.syslog('dbfilter_handle_status: response %d' % response)
        if response == 1:
            return True
        elif response == gtk.RESPONSE_CLOSE:
            self.quit_installer()
        else:
            step = self.step_name(self.steps.get_current_page())
            if step.startswith("stepPart"):
                print('dbfilter_handle_status stepPart')
                self.set_current_page(self.steps.page_num(self.stepPartAuto))
            return False


    def show_intro(self):
        """Show some introductory text, if available."""

        intro = os.path.join(PATH, 'intro.txt')

        if os.path.isfile(intro):
            intro_file = open(intro)
            self.intro_label.set_markup(intro_file.read().rstrip('\n'))
            intro_file.close()
            return True
        else:
            return False


    def step_name(self, step_index):
        return self.steps.get_nth_page(step_index).get_name()


    def set_page(self, n):
        self.run_automation_error_cmd()
        # We only stop the backup process when we're on a page where questions
        # need to be asked, otherwise you wont be able to back up past
        # migration-assistant.
        self.backup = False
        self.live_installer.show()
        if n == 'Language':
            cur = self.stepLanguage
        elif n == 'ConsoleSetup':
            cur = self.stepKeyboardConf
        elif n == 'Timezone':
            cur = self.stepLocation
        elif n == 'Partman':
            # Rather than try to guess which partman page we should be on,
            # we leave that decision to set_autopartitioning_choices and
            # update_partman.
            return
        elif n == 'UserSetup':
            cur = self.stepUserInfo
        elif n == 'Summary':
            cur = self.stepReady
            self.next.set_label(self.get_string('install_button'))
        elif n == 'MigrationAssistant':
            cur = self.stepMigrationAssistant
        else:
            print >>sys.stderr, 'No page found for %s' % n
            return

        self.set_current_page(self.steps.page_num(cur))
        if not self.first_seen_page:
            self.first_seen_page = n
        if self.first_seen_page == self.pages[self.pagesindex].__name__:
            self.allow_go_backward(False)
        elif 'UBIQUITY_AUTOMATIC' not in os.environ:
            self.allow_go_backward(True)

    def set_current_page(self, current):
        if self.steps.get_current_page() == current:
            # self.steps.set_current_page() will do nothing. Update state
            # ourselves.
            self.on_steps_switch_page(
                self.steps, self.steps.get_nth_page(current), current)
        else:
            self.steps.set_current_page(current)

    # Methods

    def progress_loop(self):
        """prepare, copy and config the system in the core install process."""

        syslog.syslog('progress_loop()')

        self.current_page = None

        self.debconf_progress_start(
            0, 100, self.get_string('ubiquity/install/title'))
        self.debconf_progress_region(0, 15)

        dbfilter = partman_commit.PartmanCommit(self)
        if dbfilter.run_command(auto_process=True) != 0:
            while self.progress_position.depth() != 0:
                self.debconf_progress_stop()
            self.debconf_progress_window.hide()
            self.return_to_partitioning()
            return

        # No return to partitioning from now on
        self.installing_no_return = True

        self.debconf_progress_region(15, 100)

        dbfilter = install.Install(self)
        ret = dbfilter.run_command(auto_process=True)
        if ret != 0:
            self.installing = False
            if ret == 3:
                # error already handled by Install
                sys.exit(ret)
            elif (os.WIFSIGNALED(ret) and
                  os.WTERMSIG(ret) in (signal.SIGINT, signal.SIGKILL,
                                       signal.SIGTERM)):
                sys.exit(ret)
            elif os.path.exists('/var/lib/ubiquity/install.trace'):
                tbfile = open('/var/lib/ubiquity/install.trace')
                realtb = tbfile.read()
                tbfile.close()
                raise RuntimeError, ("Install failed with exit code %s\n%s" %
                                     (ret, realtb))
            else:
                raise RuntimeError, ("Install failed with exit code %s; see "
                                     "/var/log/syslog" % ret)

        while self.progress_position.depth() != 0:
            self.debconf_progress_stop()

        # just to make sure
        self.debconf_progress_window.hide()

        self.installing = False

        self.run_success_cmd()
        if not self.get_reboot_seen():
            if 'UBIQUITY_ONLY' in os.environ:
                txt = self.get_string('ubiquity/finished_restart_only')
                self.finished_label.set_label(txt)
                self.quit_button.hide()
            self.finished_dialog.run()
        elif self.get_reboot():
            self.reboot()


    def reboot(self, *args):
        """reboot the system after installing process."""

        self.returncode = 10
        self.quit_installer()


    def do_reboot(self):
        """Callback for main program to actually reboot the machine."""

        if (os.path.exists("/usr/lib/ubiquity/gdm-signal") and
            os.path.exists("/usr/bin/gnome-session-save") and
            'DESKTOP_SESSION' in os.environ):
            execute("/usr/lib/ubiquity/gdm-signal", "--reboot")
            if 'SUDO_UID' in os.environ:
                user = '#%d' % int(os.environ['SUDO_UID'])
            else:
                user = 'mint'
            execute("sudo", "-u", user, "-H",
                    "gnome-session-save", "--kill", "--silent")
        else:
            execute("reboot")


    def quit_installer(self):
        """quit installer cleanly."""

        # exiting from application
        self.current_page = None
        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
        if gtk.main_level() > 0:
            gtk.main_quit()


    # Callbacks
    def on_quit_clicked(self, widget):
        self.warning_dialog.show()
        response = self.warning_dialog.run()
        self.warning_dialog.hide()
        if response == gtk.RESPONSE_CLOSE:
            self.current_page = None
            self.quit_installer()
            return False
        else:
            return True # stop processing


    def on_live_installer_delete_event(self, widget, event):
        return self.on_quit_clicked(widget)


    def info_loop(self, widget):
        """check if all entries from Identification screen are filled. Callback
        defined in glade file."""

        if (self.username_changed_id is None or
            self.hostname_changed_id is None):
            return

        if (widget is not None and widget.get_name() == 'fullname' and
            not self.username_edited):
            self.username.handler_block(self.username_changed_id)
            new_username = widget.get_text().split(' ')[0]
            new_username = new_username.encode('ascii', 'ascii_transliterate')
            new_username = new_username.lower()
            self.username.set_text(new_username)
            self.username.handler_unblock(self.username_changed_id)
        elif (widget is not None and widget.get_name() == 'username' and
              not self.hostname_edited):
            if self.laptop:
                hostname_suffix = '-laptop'
            else:
                hostname_suffix = '-desktop'
            self.hostname.handler_block(self.hostname_changed_id)
            self.hostname.set_text(widget.get_text() + hostname_suffix)
            self.hostname.handler_unblock(self.hostname_changed_id)

        complete = True
        for name in ('username', 'hostname'):
            if getattr(self, name).get_text() == '':
                complete = False
        if not self.allow_password_empty:
            for name in ('password', 'verified_password'):
                if getattr(self, name).get_text() == '':
                    complete = False
        self.allow_go_forward(complete)

    def on_username_changed(self, widget):
        self.username_edited = (widget.get_text() != '')

    def on_hostname_changed(self, widget):
        self.hostname_edited = (widget.get_text() != '')

    def on_next_clicked(self, widget):
        """Callback to control the installation process between steps."""

        if not self.allowed_change_step or not self.allowed_go_forward:
            return

        self.allow_change_step(False)

        step = self.step_name(self.steps.get_current_page())

        # Beware that 'step' is the step we're leaving, not the one we're
        # entering. At present it's a little awkward to define actions that
        # occur upon entering a page without unwanted side-effects when the
        # user tries to go forward but fails due to validation.
        if step == "stepPartAuto":
            self.part_advanced_warning_message.set_text('')
            self.part_advanced_warning_hbox.hide()
        if step in ("stepPartAuto", "stepPartAdvanced"):
            self.username_error_box.hide()
            self.password_error_box.hide()
            self.hostname_error_box.hide()

        if self.dbfilter is not None:
            self.dbfilter.ok_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits
        elif gtk.main_level() > 0:
            gtk.main_quit()

        if not self.live_installer.get_focus():
            self.live_installer.child_focus(gtk.DIR_TAB_FORWARD)

    def on_keyboardlayoutview_row_activated(self, treeview, path, view_column):
        self.next.activate()

    def on_keyboard_layout_selected(self, start_editing, *args):
        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            layout = self.get_keyboard()
            if layout is not None:
                self.current_layout = layout
                self.dbfilter.change_layout(layout)

    def on_keyboardvariantview_row_activated(self, treeview, path,
                                             view_column):
        self.next.activate()

    def on_keyboard_variant_selected(self, start_editing, *args):
        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            layout = self.get_keyboard()
            variant = self.get_keyboard_variant()
            if layout is not None and variant is not None:
                self.dbfilter.apply_keyboard(layout, variant)

    def prepare_page(self):
        """Set up the frontend in preparation for running a step."""

        # Note that self.current_page et al have not been updated for the
        # new page yet, so we have to check self.dbfilter.

        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            self.default_keyboard_layout = None
            self.default_keyboard_variant = None

    def process_step(self):
        """Process and validate the results of this step."""

        # setting actual step
        step_num = self.steps.get_current_page()
        step = self.step_name(step_num)
        syslog.syslog('Step_before = %s' % step)

        if step.startswith("stepPart"):
            self.previous_partitioning_page = step_num

        elif step == "stepLanguage":
            self.translate_widgets()
            # FIXME: needed anymore now that we're doing dbfilter first?
            #self.allow_go_forward(self.get_timezone() is not None)
        # Automatic partitioning
        elif step == "stepPartAuto":
            self.process_autopartitioning()
        # Advanced partitioning
        elif step == "stepPartAdvanced":
            self.info_loop(None)
        # Identification
        elif step == "stepUserInfo":
            self.process_identification()

    def process_identification (self):
        """Processing identification step tasks."""

        error_msg = []
        error = 0

        # Validation stuff

        # checking hostname entry
        hostname = self.hostname.get_property('text')
        for result in validation.check_hostname(hostname):
            if result == validation.HOSTNAME_LENGTH:
                error_msg.append("The hostname must be between 1 and 63 characters long.")
            elif result == validation.HOSTNAME_BADCHAR:
                error_msg.append("The hostname may only contain letters, digits, hyphens, and dots.")
            elif result == validation.HOSTNAME_BADHYPHEN:
                error_msg.append("The hostname may not start or end with a hyphen.")
            elif result == validation.HOSTNAME_BADDOTS:
                error_msg.append('The hostname may not start or end with a dot, or contain the sequence "..".')

        # showing warning message is error is set
        if len(error_msg) != 0:
            self.hostname_error_reason.set_text("\n".join(error_msg))
            self.hostname_error_box.show()
            self.stay_on_page = True
        else:
            self.stay_on_page = False


    def process_autopartitioning(self):
        """Processing automatic partitioning step tasks."""


        while gtk.events_pending ():
            gtk.main_iteration ()

        # For safety, if we somehow ended up improperly initialised
        # then go to manual partitioning.
        choice = self.get_autopartition_choice()[0]
        if self.manual_choice is None or choice == self.manual_choice:
            self.steps.next_page()
        #else:
        #    if not 'UBIQUITY_MIGRATION_ASSISTANT' in os.environ:
        #        self.info_loop(None)
        #        self.set_current_page(self.steps.page_num(self.stepUserInfo))
        #    else:
        #        self.set_current_page(self.steps.page_num(self.stepMigrationAssistant))


    def on_back_clicked(self, widget):
        """Callback to set previous screen."""

        if not self.allowed_change_step:
            return

        self.allow_change_step(False)

        self.backup = True
        self.stay_on_page = False

        # Enabling next button
        self.allow_go_forward(True)
        # Setting actual step
        step = self.step_name(self.steps.get_current_page())

        if step == "stepReady":
            self.next.set_label("gtk-go-forward")
            self.translate_widget(self.next, self.locale)

        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits
        elif gtk.main_level() > 0:
            gtk.main_quit()

        if not self.live_installer.get_focus():
            self.live_installer.child_focus(gtk.DIR_TAB_FORWARD)


    def selected_language (self, selection):
        (model, iterator) = selection.get_selected()
        if iterator is not None:
            value = unicode(model.get_value(iterator, 0))
            return self.language_choice_map[value][1]
        else:
            return ''


    def link_button_browser (self, button, uri):
        selection = self.language_treeview.get_selection()
        lang = self.selected_language(selection)
        lang = lang.split('.')[0] # strip encoding
        uri = uri.replace('${LANG}', lang)
        subprocess.Popen(['sensible-browser', uri],
                         close_fds=True, preexec_fn=drop_all_privileges)


    def on_language_treeview_row_activated (self, treeview, path, view_column):
        self.next.activate()

    def on_language_treeview_selection_changed (self, selection):
        lang = self.selected_language(selection)
        if lang:
            # strip encoding; we use UTF-8 internally no matter what
            lang = lang.split('.')[0].lower()
            for widget in self.language_questions:
                self.translate_widget(getattr(self, widget), lang)

    def on_steps_switch_page (self, foo, bar, current):
        self.current_page = current
        # If we're on the language page, then we may not know the correct
        # language yet.  But we still want to update the page number if the
        # user hit back, so call on_language_treeview_selection_changed and if
        # we have a language selection, the interface will be translated
        # properly.
        if self.step_name(current) != 'stepLanguage':
            self.translate_widget(self.step_label, self.locale)
        else:
            selection = self.language_treeview.get_selection()
            self.on_language_treeview_selection_changed(selection)
        syslog.syslog('switched to page %s' % self.step_name(current))

    def on_extra_combo_changed (self, widget):
        txt = widget.get_active_text()
        for k in self.disk_layout:
            disk = k
            if disk.startswith('=dev='):
                disk = disk[5:]
            if '(%s)' % disk in txt:
                self.before_bar.remove_all()
                self.create_bar(k)
                break
        if txt in self.format_warnings:
            self.format_warning.set_text(self.format_warnings[txt])
            self.format_warning_align.show_all()
        else:
            self.format_warning_align.hide()

    def on_autopartition_toggled (self, widget, extra_combo):
        """Update autopartitioning screen when a button is selected."""

        choice = unicode(widget.get_label(), 'utf-8', 'replace')
        if choice is not None and choice in self.autopartition_extras:
            element = self.autopartition_extras[choice]
            if widget.get_active():
                element.set_sensitive(True)
            else:
                element.set_sensitive(False)

        if widget.get_active():
            self.action_bar.remove_all()
            self.action_bar.resize = -1
            if choice == self.manual_choice:
                self.action_bar.add_segment_rgb(self.manual_choice, -1, \
                    self.release_color)
            elif choice == self.resize_choice:
                for k in self.disk_layout:
                    for p in self.disk_layout[k]:
                        if self.resize_path == p[0]:
                            self.before_bar.remove_all()
                            self.create_bar(k)
                            self.create_bar(k, type=choice)
                            return
            elif choice == self.biggest_free_choice:
                for k in self.disk_layout:
                    for p in self.disk_layout[k]:
                        if self.biggest_free_id == p[2]:
                            self.before_bar.remove_all()
                            self.create_bar(k)
                            self.create_bar(k, type=choice)
                            return
            else:
                # Use entire disk.
                self.action_bar.add_segment_rgb(get_release_name(), -1, \
                    self.release_color)
                self.on_extra_combo_changed(extra_combo)

    # Callbacks provided to components.

    def watch_debconf_fd (self, from_debconf, process_input):
        gobject.io_add_watch(from_debconf,
                             gobject.IO_IN | gobject.IO_ERR | gobject.IO_HUP,
                             self.watch_debconf_fd_helper, process_input)


    def watch_debconf_fd_helper (self, source, cb_condition, callback):
        debconf_condition = 0
        if (cb_condition & gobject.IO_IN) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_IN
        if (cb_condition & gobject.IO_ERR) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_ERR
        if (cb_condition & gobject.IO_HUP) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_HUP

        return callback(source, debconf_condition)


    def debconf_progress_start (self, progress_min, progress_max, progress_title):
        if self.current_page is not None:
            self.debconf_progress_window.set_transient_for(self.live_installer)
            # Metacity doesn't seem to respect the modal flag for normal
            # windows when the parent window is fullscreened.
            self.debconf_progress_window.set_type_hint(
                gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        else:
            self.debconf_progress_window.set_transient_for(None)
        if progress_title is None:
            progress_title = ""
        if self.progress_position.depth() == 0:
            self.debconf_progress_window.set_title(progress_title)

        self.progress_position.start(progress_min, progress_max,
                                     progress_title)
        self.progress_title.set_markup(
            '<big><b>' +
            xml.sax.saxutils.escape(self.progress_position.title()) +
            '</b></big>')
        self.debconf_progress_set(0)
        self.progress_info.set_text('')
        self.debconf_progress_window.show()

    def debconf_progress_set (self, progress_val):
        if self.progress_cancelled:
            return False
        self.progress_position.set(progress_val)
        fraction = self.progress_position.fraction()
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text('%s%%' % int(fraction * 100))
        return True

    def debconf_progress_step (self, progress_inc):
        if self.progress_cancelled:
            return False
        self.progress_position.step(progress_inc)
        fraction = self.progress_position.fraction()
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text('%s%%' % int(fraction * 100))
        return True

    def debconf_progress_info (self, progress_info):
        if self.progress_cancelled:
            return False
        self.progress_info.set_markup(
            '<i>' + xml.sax.saxutils.escape(progress_info) + '</i>')
        return True

    def debconf_progress_stop (self):
        self.progress_cancelled = False
        self.progress_position.stop()
        if self.progress_position.depth() == 0:
            self.debconf_progress_window.hide()
        else:
            self.progress_title.set_markup(
                '<big><b>' +
                xml.sax.saxutils.escape(self.progress_position.title()) +
                '</b></big>')

    def debconf_progress_region (self, region_start, region_end):
        self.progress_position.set_region(region_start, region_end)

    def debconf_progress_cancellable (self, cancellable):
        if cancellable:
            self.progress_cancel_button.show()
        else:
            self.progress_cancel_button.hide()
            self.progress_cancelled = False

    def on_progress_cancel_button_clicked (self, button):
        self.progress_cancelled = True


    def debconffilter_done (self, dbfilter):
        if BaseFrontend.debconffilter_done(self, dbfilter):
            if gtk.main_level() > 0:
                gtk.main_quit()
            return True
        else:
            return False


    def set_language_choices (self, choices, choice_map):
        BaseFrontend.set_language_choices(self, choices, choice_map)
        if len(self.language_treeview.get_columns()) < 1:
            column = gtk.TreeViewColumn(None, gtk.CellRendererText(), text=0)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            self.language_treeview.append_column(column)
            selection = self.language_treeview.get_selection()
            selection.connect('changed',
                              self.on_language_treeview_selection_changed)
        list_store = gtk.ListStore(gobject.TYPE_STRING)
        self.language_treeview.set_model(list_store)
        for choice in choices:
            list_store.append([choice])


    def set_language (self, language):
        model = self.language_treeview.get_model()
        iterator = model.iter_children(None)
        while iterator is not None:
            if unicode(model.get_value(iterator, 0)) == language:
                path = model.get_path(iterator)
                self.language_treeview.get_selection().select_path(path)
                self.language_treeview.scroll_to_cell(
                    path, use_align=True, row_align=0.5)
                break
            iterator = model.iter_next(iterator)


    def get_language (self):
        selection = self.language_treeview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return 'C'
        else:
            value = unicode(model.get_value(iterator, 0))
            return self.language_choice_map[value][1]


    def get_oem_id (self):
        return self.oem_id_entry.get_text()


    def set_timezone (self, timezone):
        self.select_city(None, timezone)

    def get_timezone (self):
        i = self.timezone_zone_combo.get_active()
        m = self.timezone_zone_combo.get_model()
        region = m[i][0]
        
        i = self.timezone_city_combo.get_active()
        m = self.timezone_city_combo.get_model()
        city = m[i][0].replace(' ', '_')
        city = region + '/' + city
        return city
    
    def set_keyboard_choices(self, choices):
        layouts = gtk.ListStore(gobject.TYPE_STRING)
        self.keyboardlayoutview.set_model(layouts)
        for v in sorted(choices):
            layouts.append([v])

        if len(self.keyboardlayoutview.get_columns()) < 1:
            column = gtk.TreeViewColumn("Layout", gtk.CellRendererText(), text=0)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            self.keyboardlayoutview.append_column(column)
            selection = self.keyboardlayoutview.get_selection()
            selection.connect('changed',
                              self.on_keyboard_layout_selected)

        if self.current_layout is not None:
            self.set_keyboard(self.current_layout)

    def set_keyboard (self, layout):
        if self.default_keyboard_layout is None:
            self.default_keyboard_layout = layout
        BaseFrontend.set_keyboard(self, layout)
        model = self.keyboardlayoutview.get_model()
        if model is None:
            return
        iterator = model.iter_children(None)
        while iterator is not None:
            if unicode(model.get_value(iterator, 0)) == layout:
                path = model.get_path(iterator)
                self.keyboardlayoutview.get_selection().select_path(path)
                self.keyboardlayoutview.scroll_to_cell(
                    path, use_align=True, row_align=0.5)
                break
            iterator = model.iter_next(iterator)

    def get_keyboard (self):
        if self.suggested_keymap.get_active():
            return unicode(self.default_keyboard_layout)
        selection = self.keyboardlayoutview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            return unicode(model.get_value(iterator, 0))

    def set_keyboard_variant_choices(self, choices):
        variants = gtk.ListStore(gobject.TYPE_STRING)
        self.keyboardvariantview.set_model(variants)
        for v in sorted(choices):
            variants.append([v])

        if len(self.keyboardvariantview.get_columns()) < 1:
            column = gtk.TreeViewColumn("Variant", gtk.CellRendererText(), text=0)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            self.keyboardvariantview.append_column(column)
            selection = self.keyboardvariantview.get_selection()
            selection.connect('changed',
                              self.on_keyboard_variant_selected)

    def set_keyboard_variant (self, variant):
        if self.default_keyboard_variant is None:
            self.default_keyboard_variant = variant
        # Make sure the "suggested option" is selected, otherwise this will
        # change every time the user selects a new keyboard in the manual
        # choice selection boxes.
        if self.suggested_keymap.get_active():
            self.suggested_keymap_label.set_property('label', variant)
            self.suggested_keymap.toggled()
        model = self.keyboardvariantview.get_model()
        if model is None:
            return
        iterator = model.iter_children(None)
        while iterator is not None:
            if unicode(model.get_value(iterator, 0)) == variant:
                path = model.get_path(iterator)
                self.keyboardvariantview.get_selection().select_path(path)
                self.keyboardvariantview.scroll_to_cell(
                    path, use_align=True, row_align=0.5)
                break
            iterator = model.iter_next(iterator)

    def get_keyboard_variant (self):
        if self.suggested_keymap.get_active():
            return unicode(self.default_keyboard_variant)
        selection = self.keyboardvariantview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            return unicode(model.get_value(iterator, 0))

    def on_suggested_keymap_toggled (self, widget):
        if self.suggested_keymap.get_active():
            self.keyboard_layout_hbox.set_sensitive(False)
            if isinstance(self.dbfilter, console_setup.ConsoleSetup):
                if (self.default_keyboard_layout is not None and
                    self.default_keyboard_variant is not None):
                    self.current_layout = self.default_keyboard_layout
                    self.dbfilter.change_layout(self.default_keyboard_layout)
                    self.dbfilter.apply_keyboard(self.default_keyboard_layout,
                                                 self.default_keyboard_variant)

        else:
            self.keyboard_layout_hbox.set_sensitive(True)
        
    def set_disk_layout(self, layout):
        self.disk_layout = layout

    def create_bar(self, disk, type=None):
        if type:
            b = self.action_bar
        else:
            b = self.before_bar
            ret = []
            for part in self.disk_layout[disk]:
                if part[0].startswith('/'):
                    t = find_in_os_prober(part[0])
                    if t and t != 'swap':
                        ret.append(t)
            if len(ret) == 0:
                s = self.get_string('ubiquity/text/part_auto_comment_none')
            elif len(ret) == 1:
                s = self.get_string('ubiquity/text/part_auto_comment_one')
                s = s.replace('${OS}', ret[0])
            else:
                s = self.get_string('ubiquity/text/part_auto_comment_many')
            self.part_auto_comment_label.set_text(s)
        i = 0
        for part in self.disk_layout[disk]:
            dev = part[0]
            size = part[1]
            if type == self.biggest_free_choice and part[2] == self.biggest_free_id:
                b.add_segment_rgb(get_release_name(), size, self.release_color)
            elif dev == 'free':
                b.add_segment_rgb("Free Space", size, b.remainder_color)
            else:
                if dev in self.dev_colors:
                    c = self.dev_colors[dev]
                else:
                    c = self.auto_colors[i]
                    self.dev_colors[dev] = c
                b.add_segment_rgb(dev, size, c)
                if dev == self.resize_path and type == self.resize_choice:
                    self.action_bar.add_segment_rgb(get_release_name(), -1,
                        self.release_color)
                i = (i + 1) % len(self.auto_colors)

    def setup_format_warnings(self, extra_options):
        for extra in extra_options:
            for k in self.disk_layout:
                disk = k
                if disk.startswith('=dev='):
                    disk = disk[5:]
                if '(%s)' % disk not in extra:
                    continue
                l = []
                for part in self.disk_layout[k]:
                    if part[0] == 'free':
                        continue
                    ret = find_in_os_prober(part[0])
                    if ret and ret != 'swap':
                        l.append(ret)
                if l:
                    if len(l) == 1:
                        l = l[0]
                    elif len(l) > 1:
                        l = ', '.join(l)
                    txt = self.get_string('ubiquity/text/part_format_warning')
                    txt = txt.replace('${RELEASE}', get_release_name())
                    txt = txt.replace('${SYSTEMS}', l)
                    self.format_warnings[extra] = txt

    def set_autopartition_choices (self, choices, extra_options,
                                   resize_choice, manual_choice,
                                   biggest_free_choice):
        BaseFrontend.set_autopartition_choices(self, choices, extra_options,
                                               resize_choice, manual_choice,
                                               biggest_free_choice)

        if resize_choice in choices:
            self.resize_min_size, self.resize_max_size, \
                self.resize_orig_size, self.resize_path = \
                    extra_options[resize_choice]
            self.action_bar.set_part_size(self.resize_orig_size)
            self.action_bar.set_min(self.resize_min_size)
            self.action_bar.set_max(self.resize_max_size)
            self.action_bar.set_device(self.resize_path)
        if biggest_free_choice in choices:
            self.biggest_free_id = extra_options[biggest_free_choice]

        for child in self.autopartition_choices_vbox.get_children():
            self.autopartition_choices_vbox.remove(child)
        
        text = self.get_string('ubiquity/text/part_auto_choices_label')
        text = text.replace('${RELEASE}', get_release_name())
        self.part_auto_choices_label.set_text(text)

        firstbutton = None
        extra_combo = None
        for choice in choices:
            button = gtk.RadioButton(firstbutton, choice, False)
            if firstbutton is None:
                firstbutton = button
            self.autopartition_choices_vbox.add(button)

            if choice in extra_options and choice != biggest_free_choice:
                alignment = gtk.Alignment(xscale=1, yscale=1)
                alignment.set_padding(0, 0, 12, 0)

                if choice not in [resize_choice, manual_choice]:
                    extra_combo = gtk.combo_box_new_text()
                    vbox = gtk.VBox(spacing=6)
                    alignment.add(vbox)
                    vbox.add(extra_combo)
                    for extra in extra_options[choice]:
                        extra_combo.append_text(extra)
                    a = gtk.Alignment(xscale=1, yscale=1)
                    a.set_padding(0, 0, 12, 0)
                    a.hide()
                    self.format_warning_align = a
                    label = gtk.Label()
                    self.format_warning = label
                    hbox = gtk.HBox(spacing=6)
                    img = gtk.Image()
                    img.set_from_icon_name('gtk-dialog-warning', gtk.ICON_SIZE_BUTTON)
                    hbox.pack_start(img, expand=False, fill=False)
                    hbox.pack_start(label, expand=False, fill=False)
                    a.add(hbox)
                    vbox.add(a)
                    
                    self.setup_format_warnings(extra_options[choice])
                    extra_combo.connect('changed', self.on_extra_combo_changed)
                    extra_combo.set_active(0)
                self.autopartition_choices_vbox.pack_start(alignment,
                                                   expand=False, fill=False)
                self.autopartition_extras[choice] = alignment
            button.connect('toggled', self.on_autopartition_toggled, extra_combo)

        if firstbutton is not None:
            firstbutton.set_active(True)
            self.on_autopartition_toggled(firstbutton, extra_combo)
        self.autopartition_choices_vbox.show_all()

        # make sure we're on the autopartitioning page
        self.set_current_page(self.steps.page_num(self.stepPartAuto))


    def get_autopartition_choice (self):
        for button in self.autopartition_choices_vbox.get_children():
            if isinstance(button, gtk.Button):
                if button.get_active():
                    choice = unicode(button.get_label(), 'utf-8', 'replace')
                    break
        else:
            raise AssertionError, "no active autopartitioning choice"

        if choice == self.resize_choice:
            # resize_choice should have been hidden otherwise
            assert self.action_bar.resize != -1
            return choice, '%d B' % self.action_bar.get_size()
        elif (choice != self.manual_choice and
              choice in self.autopartition_extras):
            vbox = self.autopartition_extras[choice].child
            for child in vbox.get_children():
                if isinstance(child, gtk.ComboBox):
                    return choice, unicode(child.get_active_text(),
                                           'utf-8', 'replace')
            else:
                return choice, None
        else:
            return choice, None


    def installation_medium_mounted (self, message):
        self.part_advanced_warning_message.set_text(message)
        self.part_advanced_warning_hbox.show_all()


    def partman_column_name (self, column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition:
            # whole disk
            cell.set_property('text', partition['device'])
        elif partition['parted']['fs'] != 'free':
            cell.set_property('text', '  %s' % partition['parted']['path'])
        elif partition['parted']['type'] == 'unusable':
            unusable = self.get_string('partman/text/unusable')
            cell.set_property('text', '  %s' % unusable)
        else:
            # partman uses "FREE SPACE" which feels a bit too SHOUTY for
            # this interface.
            free_space = self.get_string('partition_free_space')
            cell.set_property('text', '  %s' % free_space)

    def partman_column_type (self, column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition or 'method' not in partition:
            if ('parted' in partition and
                partition['parted']['fs'] != 'free' and
                'detected_filesystem' in partition):
                cell.set_property('text', partition['detected_filesystem'])
            else:
                cell.set_property('text', '')
        elif ('filesystem' in partition and
              partition['method'] in ('format', 'keep')):
            cell.set_property('text', partition['acting_filesystem'])
        else:
            cell.set_property('text', partition['method'])

    def partman_column_mountpoint (self, column, cell, model, iterator):
        partition = model[iterator][1]
        if isinstance(self.dbfilter, partman.Partman):
            mountpoint = self.dbfilter.get_current_mountpoint(partition)
            if mountpoint is None:
                mountpoint = ''
        else:
            mountpoint = ''
        cell.set_property('text', mountpoint)

    def partman_column_format (self, column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition:
            cell.set_property('visible', False)
            cell.set_property('active', False)
            cell.set_property('activatable', False)
        elif 'method' in partition:
            cell.set_property('visible', True)
            cell.set_property('active', partition['method'] == 'format')
            cell.set_property('activatable', 'can_activate_format' in partition)
        else:
            cell.set_property('visible', True)
            cell.set_property('active', False)
            cell.set_property('activatable', False)

    def partman_column_format_toggled (self, cell, path, user_data):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return
        model = user_data
        devpart = model[path][0]
        partition = model[path][1]
        if 'id' not in partition or 'method' not in partition:
            return
        self.allow_change_step(False)
        self.dbfilter.edit_partition(devpart, format='dummy')

    def partman_column_size (self, column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition:
            cell.set_property('text', '')
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['parted']['size']) / 1000000
            cell.set_property('text', '%d MB' % size_mb)

    def partman_column_used (self, column, cell, model, iterator):
        partition = model[iterator][1]
        if 'id' not in partition or partition['parted']['fs'] == 'free':
            cell.set_property('text', '')
        elif 'resize_min_size' not in partition:
            unknown = self.get_string('partition_used_unknown')
            cell.set_property('text', unknown)
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            size_mb = int(partition['resize_min_size']) / 1000000
            cell.set_property('text', '%d MB' % size_mb)

    def partman_popup (self, widget, event):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return

        model, iterator = widget.get_selection().get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]

        partition_list_menu = gtk.Menu()
        for action in self.dbfilter.get_actions(devpart, partition):
            if action == 'new_label':
                new_label_item = gtk.MenuItem(
                    self.get_string('partition_button_new_label'))
                new_label_item.connect(
                    'activate', self.on_partition_list_new_label_activate)
                partition_list_menu.append(new_label_item)
            elif action == 'new':
                new_item = gtk.MenuItem(
                    self.get_string('partition_button_new'))
                new_item.connect(
                    'activate', self.on_partition_list_new_activate)
                partition_list_menu.append(new_item)
            elif action == 'edit':
                edit_item = gtk.MenuItem(
                    self.get_string('partition_button_edit'))
                edit_item.connect(
                    'activate', self.on_partition_list_edit_activate)
                partition_list_menu.append(edit_item)
            elif action == 'delete':
                delete_item = gtk.MenuItem(
                    self.get_string('partition_button_delete'))
                delete_item.connect(
                    'activate', self.on_partition_list_delete_activate)
                partition_list_menu.append(delete_item)
        if partition_list_menu.get_children():
            partition_list_menu.append(gtk.SeparatorMenuItem())
        undo_item = gtk.MenuItem(
            self.get_string('partman/text/undo_everything'))
        undo_item.connect('activate', self.on_partition_list_undo_activate)
        partition_list_menu.append(undo_item)
        partition_list_menu.show_all()

        if event:
            button = event.button
            time = event.get_time()
        else:
            button = 0
            time = 0
        partition_list_menu.popup(None, None, None, button, time)

    def partman_create_dialog (self, devpart, partition):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return

        self.partition_create_dialog.show_all()

        # TODO cjwatson 2006-11-01: Because partman doesn't use a question
        # group for these, we have to figure out in advance whether each
        # question is going to be asked.

        if partition['parted']['type'] == 'pri/log':
            # Is there already a primary partition?
            model = self.partition_list_treeview.get_model()
            for otherpart in [row[1] for row in model]:
                if (otherpart['dev'] == partition['dev'] and
                    'id' in otherpart and
                    otherpart['parted']['type'] == 'primary'):
                    self.partition_create_type_logical.set_active(True)
                    break
            else:
                self.partition_create_type_primary.set_active(True)
        else:
            self.partition_create_type_label.hide()
            self.partition_create_type_primary.hide()
            self.partition_create_type_logical.hide()

        # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
        # partman expects.
        max_size_mb = int(partition['parted']['size']) / 1000000
        self.partition_create_size_spinbutton.set_adjustment(
            gtk.Adjustment(value=max_size_mb, upper=max_size_mb,
                           step_incr=1, page_incr=100))
        self.partition_create_size_spinbutton.set_value(max_size_mb)

        self.partition_create_place_beginning.set_active(True)

        self.partition_create_use_combo.clear()
        renderer = gtk.CellRendererText()
        self.partition_create_use_combo.pack_start(renderer)
        self.partition_create_use_combo.add_attribute(renderer, 'text', 2)
        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                                   gobject.TYPE_STRING)
        for method, name, description in self.dbfilter.create_use_as():
            list_store.append([method, name, description])
        self.partition_create_use_combo.set_model(list_store)
        if list_store.get_iter_first():
            self.partition_create_use_combo.set_active(0)

        list_store = gtk.ListStore(gobject.TYPE_STRING)
        for mp, choice_c, choice in self.dbfilter.default_mountpoint_choices():
            list_store.append([mp])
        self.partition_create_mount_combo.set_model(list_store)
        if self.partition_create_mount_combo.get_text_column() == -1:
            self.partition_create_mount_combo.set_text_column(0)
        self.partition_create_mount_combo.child.set_text('')

        response = self.partition_create_dialog.run()
        self.partition_create_dialog.hide()

        if (response == gtk.RESPONSE_OK and
            isinstance(self.dbfilter, partman.Partman)):
            if partition['parted']['type'] == 'primary':
                prilog = partman.PARTITION_TYPE_PRIMARY
            elif partition['parted']['type'] == 'logical':
                prilog = partman.PARTITION_TYPE_LOGICAL
            elif partition['parted']['type'] == 'pri/log':
                if self.partition_create_type_primary.get_active():
                    prilog = partman.PARTITION_TYPE_PRIMARY
                else:
                    prilog = partman.PARTITION_TYPE_LOGICAL

            if self.partition_create_place_beginning.get_active():
                place = partman.PARTITION_PLACE_BEGINNING
            else:
                place = partman.PARTITION_PLACE_END

            method_iter = self.partition_create_use_combo.get_active_iter()
            if method_iter is None:
                method = None
            else:
                model = self.partition_create_use_combo.get_model()
                method = model.get_value(method_iter, 1)

            mountpoint = self.partition_create_mount_combo.child.get_text()

            self.allow_change_step(False)
            self.dbfilter.create_partition(
                devpart,
                str(self.partition_create_size_spinbutton.get_value()),
                prilog, place, method, mountpoint)

    def on_partition_create_use_combo_changed (self, combobox):
        model = combobox.get_model()
        iterator = combobox.get_active_iter()
        # If the selected method isn't a filesystem, then selecting a mount
        # point makes no sense.
        if iterator is None or model[iterator][0] != 'filesystem':
            self.partition_create_mount_combo.child.set_text('')
            self.partition_create_mount_combo.set_sensitive(False)
        else:
            self.partition_create_mount_combo.set_sensitive(True)
            if isinstance(self.dbfilter, partman.Partman):
                mount_model = self.partition_create_mount_combo.get_model()
                if mount_model is not None:
                    fs = model[iterator][1]
                    mount_model.clear()
                    for mp, choice_c, choice in \
                        self.dbfilter.default_mountpoint_choices(fs):
                        mount_model.append([mp])

    def partman_edit_dialog (self, devpart, partition):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return

        self.partition_edit_dialog.show_all()

        current_size = None
        if ('can_resize' not in partition or not partition['can_resize'] or
            'resize_min_size' not in partition or
            'resize_max_size' not in partition):
            self.partition_edit_size_label.hide()
            self.partition_edit_size_spinbutton.hide()
        else:
            # Yes, I know, 1000000 bytes is annoying. Sorry. This is what
            # partman expects.
            min_size_mb = int(partition['resize_min_size']) / 1000000
            cur_size_mb = int(partition['parted']['size']) / 1000000
            max_size_mb = int(partition['resize_max_size']) / 1000000
            # Bad things happen if the current size is out of bounds.
            min_size_mb = min(min_size_mb, cur_size_mb)
            max_size_mb = max(cur_size_mb, max_size_mb)
            self.partition_edit_size_spinbutton.set_adjustment(
                gtk.Adjustment(value=cur_size_mb, lower=min_size_mb,
                               upper=max_size_mb,
                               step_incr=1, page_incr=100))
            self.partition_edit_size_spinbutton.set_value(cur_size_mb)
            current_size = str(self.partition_edit_size_spinbutton.get_value())

        self.partition_edit_use_combo.clear()
        renderer = gtk.CellRendererText()
        self.partition_edit_use_combo.pack_start(renderer)
        self.partition_edit_use_combo.add_attribute(renderer, 'text', 1)
        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        for script, arg, option in partition['method_choices']:
            list_store.append([arg, option])
        self.partition_edit_use_combo.set_model(list_store)
        current_method = self.dbfilter.get_current_method(partition)
        if current_method:
            iterator = list_store.get_iter_first()
            while iterator:
                if list_store[iterator][0] == current_method:
                    self.partition_edit_use_combo.set_active_iter(iterator)
                    break
                iterator = list_store.iter_next(iterator)

        if 'id' not in partition:
            self.partition_edit_format_label.hide()
            self.partition_edit_format_checkbutton.hide()
            current_format = False
        elif 'method' in partition:
            self.partition_edit_format_label.show()
            self.partition_edit_format_checkbutton.show()
            self.partition_edit_format_checkbutton.set_sensitive(
                'can_activate_format' in partition)
            current_format = (partition['method'] == 'format')
        else:
            self.partition_edit_format_label.show()
            self.partition_edit_format_checkbutton.show()
            self.partition_edit_format_checkbutton.set_sensitive(False)
            current_format = False
        self.partition_edit_format_checkbutton.set_active(current_format)

        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        if 'mountpoint_choices' in partition:
            for mp, choice_c, choice in partition['mountpoint_choices']:
                list_store.append([mp, choice])
        self.partition_edit_mount_combo.set_model(list_store)
        if self.partition_edit_mount_combo.get_text_column() == -1:
            self.partition_edit_mount_combo.set_text_column(0)
        current_mountpoint = self.dbfilter.get_current_mountpoint(partition)
        if current_mountpoint is not None:
            self.partition_edit_mount_combo.child.set_text(current_mountpoint)
            iterator = list_store.get_iter_first()
            while iterator:
                if list_store[iterator][0] == current_mountpoint:
                    self.partition_edit_mount_combo.set_active_iter(iterator)
                    break
                iterator = list_store.iter_next(iterator)

        response = self.partition_edit_dialog.run()
        self.partition_edit_dialog.hide()

        if (response == gtk.RESPONSE_OK and
            isinstance(self.dbfilter, partman.Partman)):
            size = None
            if current_size is not None:
                size = str(self.partition_edit_size_spinbutton.get_value())

            method_iter = self.partition_edit_use_combo.get_active_iter()
            if method_iter is None:
                method = None
            else:
                model = self.partition_edit_use_combo.get_model()
                method = model.get_value(method_iter, 0)

            format = self.partition_edit_format_checkbutton.get_active()

            mountpoint = self.partition_edit_mount_combo.child.get_text()

            if (current_size is not None and size is not None and
                current_size == size):
                size = None
            if method == current_method:
                method = None
            if format == current_format:
                format = None
            if mountpoint == current_mountpoint:
                mountpoint = None

            if (size is not None or method is not None or format is not None or
                mountpoint is not None):
                self.allow_change_step(False)
                edits = {'size': size, 'method': method,
                         'mountpoint': mountpoint}
                if format is not None:
                    edits['format'] = 'dummy'
                self.dbfilter.edit_partition(devpart, **edits)

    def on_partition_edit_use_combo_changed (self, combobox):
        model = combobox.get_model()
        iterator = combobox.get_active_iter()
        # If the selected method isn't a filesystem, then selecting a mount
        # point makes no sense. TODO cjwatson 2007-01-31: Unfortunately we
        # have to hardcode the list of known filesystems here.
        known_filesystems = ('ext3', 'ext4', 'ext2', 'reiserfs', 'jfs', 'xfs',
                             'fat16', 'fat32', 'ntfs')
        if iterator is None or model[iterator][0] not in known_filesystems:
            self.partition_edit_mount_combo.child.set_text('')
            self.partition_edit_mount_combo.set_sensitive(False)
            self.partition_edit_format_checkbutton.set_sensitive(False)
        else:
            self.partition_edit_mount_combo.set_sensitive(True)
            self.partition_edit_format_checkbutton.set_sensitive(True)
            if isinstance(self.dbfilter, partman.Partman):
                mount_model = self.partition_edit_mount_combo.get_model()
                if mount_model is not None:
                    fs = model[iterator][0]
                    mount_model.clear()
                    for mp, choice_c, choice in \
                        self.dbfilter.default_mountpoint_choices(fs):
                        mount_model.append([mp, choice])

    def on_partition_list_treeview_button_press_event (self, widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            path_at_pos = widget.get_path_at_pos(int(event.x), int(event.y))
            if path_at_pos is not None:
                selection = widget.get_selection()
                selection.unselect_all()
                selection.select_path(path_at_pos[0])

            self.partman_popup(widget, event)
            return True

    def on_partition_list_treeview_key_press_event (self, widget, event):
        if event.type != gtk.gdk.KEY_PRESS:
            return False

        if event.keyval == gtk.keysyms.Delete:
            if not isinstance(self.dbfilter, partman.Partman):
                return False
            devpart, partition = self.partition_list_get_selection()
            for action in self.dbfilter.get_actions(devpart, partition):
                if action == 'delete':
                    self.on_partition_list_delete_activate(widget)
                    return True

        return False

    def on_partition_list_treeview_popup_menu (self, widget):
        self.partman_popup(widget, None)
        return True

    def on_partition_list_treeview_selection_changed (self, selection):
        self.partition_button_new_label.set_sensitive(False)
        self.partition_button_new.set_sensitive(False)
        self.partition_button_edit.set_sensitive(False)
        self.partition_button_delete.set_sensitive(False)
        if not isinstance(self.dbfilter, partman.Partman):
            return

        model, iterator = selection.get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]
            if 'id' not in partition:
                dev = partition['device']
            else:
                dev = partition['parent']
            for p in self.partition_bars.itervalues():
                p.hide()
            self.partition_bars[dev].show()
        for action in self.dbfilter.get_actions(devpart, partition):
            if action == 'new_label':
                self.partition_button_new_label.set_sensitive(True)
            elif action == 'new':
                self.partition_button_new.set_sensitive(True)
            elif action == 'edit':
                self.partition_button_edit.set_sensitive(True)
            elif action == 'delete':
                self.partition_button_delete.set_sensitive(True)
        self.partition_button_undo.set_sensitive(True)

    def on_partition_list_treeview_row_activated (self, treeview,
                                                  path, view_column):
        if not self.allowed_change_step:
            return
        model = treeview.get_model()
        try:
            devpart = model[path][0]
            partition = model[path][1]
        except (IndexError, KeyError):
            return

        if 'id' not in partition:
            # Are there already partitions on this disk? If so, don't allow
            # activating the row to offer to create a new partition table,
            # to avoid mishaps.
            for otherpart in [row[1] for row in model]:
                if otherpart['dev'] == partition['dev'] and 'id' in otherpart:
                    break
            else:
                if not isinstance(self.dbfilter, partman.Partman):
                    return
                self.allow_change_step(False)
                self.dbfilter.create_label(devpart)
        elif partition['parted']['fs'] == 'free':
            if 'can_new' in partition and partition['can_new']:
                self.partman_create_dialog(devpart, partition)
        else:
            self.partman_edit_dialog(devpart, partition)

    def partition_list_get_selection (self):
        model, iterator = self.partition_list_treeview.get_selection().get_selected()
        if iterator is None:
            devpart = None
            partition = None
        else:
            devpart = model[iterator][0]
            partition = model[iterator][1]
        return (devpart, partition)

    def on_partition_list_new_label_activate (self, widget):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return
        self.allow_change_step(False)
        devpart, partition = self.partition_list_get_selection()
        self.dbfilter.create_label(devpart)

    def on_partition_list_new_activate (self, widget):
        devpart, partition = self.partition_list_get_selection()
        self.partman_create_dialog(devpart, partition)

    def on_partition_list_edit_activate (self, widget):
        devpart, partition = self.partition_list_get_selection()
        self.partman_edit_dialog(devpart, partition)

    def on_partition_list_delete_activate (self, widget):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return
        self.allow_change_step(False)
        devpart, partition = self.partition_list_get_selection()
        self.dbfilter.delete_partition(devpart)

    def on_partition_list_undo_activate (self, widget):
        if not self.allowed_change_step:
            return
        if not isinstance(self.dbfilter, partman.Partman):
            return
        self.allow_change_step(False)
        self.dbfilter.undo()

    def update_partman (self, disk_cache, partition_cache, cache_order):
        if self.partition_bars:
            for p in self.partition_bars.itervalues():
                self.segmented_bar_vbox.remove(p)
                del p

        partition_tree_model = self.partition_list_treeview.get_model()
        if partition_tree_model is None:
            partition_tree_model = gtk.ListStore(gobject.TYPE_STRING,
                                                 gobject.TYPE_PYOBJECT)

            cell_name = gtk.CellRendererText()
            column_name = gtk.TreeViewColumn(
                self.get_string('partition_column_device'), cell_name)
            column_name.set_cell_data_func(cell_name, self.partman_column_name)
            column_name.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_name)

            cell_type = gtk.CellRendererText()
            column_type = gtk.TreeViewColumn(
                self.get_string('partition_column_type'), cell_type)
            column_type.set_cell_data_func(cell_type, self.partman_column_type)
            column_type.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_type)

            cell_mountpoint = gtk.CellRendererText()
            column_mountpoint = gtk.TreeViewColumn(
                self.get_string('partition_column_mountpoint'),
                cell_mountpoint)
            column_mountpoint.set_cell_data_func(
                cell_mountpoint, self.partman_column_mountpoint)
            column_mountpoint.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_mountpoint)

            cell_format = gtk.CellRendererToggle()
            column_format = gtk.TreeViewColumn(
                self.get_string('partition_column_format'), cell_format)
            column_format.set_cell_data_func(
                cell_format, self.partman_column_format)
            column_format.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            cell_format.connect("toggled", self.partman_column_format_toggled,
                                partition_tree_model)
            self.partition_list_treeview.append_column(column_format)

            cell_size = gtk.CellRendererText()
            column_size = gtk.TreeViewColumn(
                self.get_string('partition_column_size'), cell_size)
            column_size.set_cell_data_func(cell_size, self.partman_column_size)
            column_size.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_size)

            cell_used = gtk.CellRendererText()
            column_used = gtk.TreeViewColumn(
                self.get_string('partition_column_used'), cell_used)
            column_used.set_cell_data_func(cell_used, self.partman_column_used)
            column_used.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.partition_list_treeview.append_column(column_used)

            self.partition_list_treeview.set_model(partition_tree_model)

            selection = self.partition_list_treeview.get_selection()
            selection.connect(
                'changed', self.on_partition_list_treeview_selection_changed)
        else:
            # TODO cjwatson 2006-08-31: inefficient, but will do for now
            partition_tree_model.clear()

        partition_bar = None
        dev = ''
        total_size = {}
        i = 0
        if not self.segmented_bar_vbox:
            sw = gtk.ScrolledWindow()
            self.segmented_bar_vbox = gtk.VBox()
            sw.add_with_viewport(self.segmented_bar_vbox)
            sw.child.set_shadow_type(gtk.SHADOW_NONE)
            sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
            sw.show_all()
            self.part_advanced_vbox.pack_start(sw, expand=False)
            self.part_advanced_vbox.reorder_child(sw, 0)

        for item in cache_order:
            if item in disk_cache:
                partition_tree_model.append([item, disk_cache[item]])
                dev = disk_cache[item]['device']
                self.partition_bars[dev] = segmented_bar.SegmentedBar()
                partition_bar = self.partition_bars[dev]
                self.segmented_bar_vbox.add(partition_bar)
                total_size[dev] = 0.0
            else:
                partition_tree_model.append([item, partition_cache[item]])
                size = int(partition_cache[item]['parted']['size'])
                total_size[dev] = total_size[dev] + size
                fs = partition_cache[item]['parted']['fs']
                path = partition_cache[item]['parted']['path'].replace('/dev/','')
                if fs == 'free':
                    c = partition_bar.remainder_color
                    # TODO evand 2008-07-27: i18n
                    txt = 'Free space'
                else:
                    i = (i + 1) % len(self.auto_colors)
                    c = self.auto_colors[i]
                    txt = '%s (%s)' % (path, fs)
                partition_bar.add_segment_rgb(txt, size, c)
        sel = self.partition_list_treeview.get_selection()
        if sel.count_selected_rows() == 0:
            sel.select_path(0)
        # make sure we're on the advanced partitioning page
        self.set_current_page(self.steps.page_num(self.stepPartAdvanced))

    def ma_get_choices(self):
        return self.ma_choices

    def ma_cb_toggle(self, cell, path, model=None):
        iterator = model.get_iter(path)
        checked = not cell.get_active()
        model.set_value(iterator, 0, checked)

        # We're on a user checkbox.
        if model.iter_children(iterator):
            if not cell.get_active():
                model.get_value(iterator, 1)['selected'] = True
            else:
                model.get_value(iterator, 1)['selected'] = False
            parent = iterator
            iterator = model.iter_children(iterator)
            items = []
            while iterator:
                model.set_value(iterator, 0, checked)
                if checked:
                    items.append(model.get_value(iterator, 1))
                iterator = model.iter_next(iterator)
            model.get_value(parent, 1)['items'] = items

        # We're on an item checkbox.
        else:
            parent = model.iter_parent(iterator)
            if not model.get_value(parent, 0):
                model.set_value(parent, 0, True)
                model.get_value(parent, 1)['selected'] = True

            item = model.get_value(iterator, 1)
            items = model.get_value(parent, 1)['items']
            if checked:
                items.append(item)
            else:
                items.remove(item)

    def ma_set_choices(self, choices):

        def cell_data_func(column, cell, model, iterator):
            val = model.get_value(iterator, 1)
            if model.iter_children(iterator):
                # Windows XP...
                text = '%s  <small><i>%s (%s)</i></small>' % \
                       (val['user'], val['os'], val['part'])
            else:
                # Gaim, Yahoo, etc
                text = model.get_value(iterator, 1)

            try:
                cell.set_property("markup", unicode(text))
            except:
                cell.set_property("text", '%s  %s (%s)' % \
                    (val['user'], val['os'], val['part']))
        # Showing the interface for the second time.
        if self.matreeview.get_model():
            for col in self.matreeview.get_columns():
                self.matreeview.remove_column(col)

        # For the previous selected item.
        self.ma_previous_selection = None

        # TODO evand 2007-01-11 I'm on the fence as to whether or not skipping
        # the page would be better than showing the user this error.
        if not choices:
            # TODO cjwatson 2009-04-01: i18n
            msg = 'There were no users or operating systems suitable for ' \
                  'importing from.'
            liststore = gtk.ListStore(str)
            liststore.append([msg])
            self.matreeview.set_model(liststore)
            column = gtk.TreeViewColumn('item', gtk.CellRendererText(), text=0)
            self.matreeview.append_column(column)
        else:
            treestore = gtk.TreeStore(bool, object)

            # We save the choices list so we can preserve state, should the user
            # decide to move back through the interface.  We cannot just put the
            # old list back as the options could conceivably change.  For
            # example, the user moves back to the partitioning page, removes a
            # partition, and moves forward to the migration-assistant page.

            # TODO evand 2007-12-04: simplify.
            for choice in choices:
                kept = False
                for old_choice in self.ma_choices:
                    if (old_choice['user'] == choice['user']) and \
                    (old_choice['part'] == choice['part']):
                        piter = treestore.append(None, \
                            [old_choice['selected'], choice])
                        choice['selected'] = old_choice['selected']
                        new_items = []
                        for item in choice['items']:
                            if item in old_choice['items']:
                                treestore.append(piter, [True, item])
                                new_items.append(item)
                            else:
                                treestore.append(piter, [False, item])
                        choice['items'] = new_items
                        kept = True
                        break
                if kept == False:
                    piter = treestore.append(None, [False, choice])
                    for item in choice['items']:
                        treestore.append(piter, [False, item])
                    choice['items'] = []

            self.matreeview.set_model(treestore)

            renderer = gtk.CellRendererToggle()
            renderer.connect('toggled', self.ma_cb_toggle, treestore)
            column = gtk.TreeViewColumn('boolean', renderer, active=0)
            column.set_clickable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
            self.matreeview.append_column(column)

            renderer = gtk.CellRendererText()
            column = gtk.TreeViewColumn('item', renderer)
            column.set_cell_data_func(renderer, cell_data_func)
            self.matreeview.append_column(column)

            self.matreeview.set_search_column(1)

        self.matreeview.show_all()

        # Save the list so we can preserve state.
        self.ma_choices = choices

    def set_fullname(self, value):
        self.fullname.set_text(value)

    def get_fullname(self):
        return self.fullname.get_text()

    def set_username(self, value):
        self.username.set_text(value)

    def get_username(self):
        return self.username.get_text()

    def get_password(self):
        return self.password.get_text()

    def get_verified_password(self):
        return self.verified_password.get_text()

    def select_password(self):
        # LP: 344402, the password should be selected if we just said "go back"
        # to the weak password entry.
        if self.password.get_text_length():
            self.password.select_region(0, -1)
            self.password.grab_focus()

    def set_auto_login(self, value):
        self.login_auto.set_active(value)

    def get_auto_login(self):
        return self.login_auto.get_active()

    def set_encrypt_home(self, value):
        if value:
            self.login_encrypt.show()
        self.login_encrypt.set_active(value)

    def get_encrypt_home(self):
        return self.login_encrypt.get_active()

    def username_error(self, msg):
        self.username_error_reason.set_text(msg)
        self.username_error_box.show()

    def password_error(self, msg):
        self.password_error_reason.set_text(msg)
        self.password_error_box.show()

    def get_hostname (self):
        return self.hostname.get_text()

    def set_hostname(self, value):
        self.hostname.set_text(value)

    def set_summary_text (self, text):
        for child in self.ready_text.get_children():
            self.ready_text.remove(child)

        ready_buffer = gtk.TextBuffer()
        ready_buffer.set_text(text)
        self.ready_text.set_buffer(ready_buffer)

    def set_grub_combo (self, options):
        self.grub_device_entry.clear()
        l = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        renderer = gtk.CellRendererText()
        self.grub_device_entry.pack_start(renderer, True)
        self.grub_device_entry.add_attribute(renderer, 'text', 0)
        renderer = gtk.CellRendererText()
        self.grub_device_entry.pack_start(renderer, True)
        self.grub_device_entry.add_attribute(renderer, 'text', 1)
        for opt in options:
            l.append(opt)
        self.grub_device_entry.set_model(l)
        self.grub_device_entry.set_text_column(0)

    def grub_verify_loop(self, widget):
        if widget is not None:
            if validation.check_grub_device(widget.child.get_text()):
                self.advanced_okbutton.set_sensitive(True)
            else:
                self.advanced_okbutton.set_sensitive(False)

    def on_advanced_button_clicked (self, button):
        display = False
        grub_en = self.get_grub()
        summary_device = self.get_summary_device()

        if grub_en is not None:
            display = True
            self.bootloader_vbox.show()
            self.grub_enable.set_active(grub_en)
        else:
            self.bootloader_vbox.hide()
            summary_device = None

        if summary_device is not None:
            display = True
            self.grub_device_label.show()
            self.grub_device_entry.show()
            self.grub_device_entry.child.set_text(summary_device)
            self.grub_device_entry.set_sensitive(grub_en)
            self.grub_device_label.set_sensitive(grub_en)
        else:
            self.grub_device_label.hide()
            self.grub_device_entry.hide()

        if self.popcon is not None:
            display = True
            self.popcon_vbox.show()
            self.popcon_checkbutton.set_active(self.popcon)
        else:
            self.popcon_vbox.hide()

        display = True
        if self.http_proxy_host:
            self.proxy_host_entry.set_text(self.http_proxy_host)
            self.proxy_port_spinbutton.set_sensitive(True)
        else:
            self.proxy_port_spinbutton.set_sensitive(False)
        self.proxy_port_spinbutton.set_value(self.http_proxy_port)

        # never happens at the moment because the HTTP proxy question is
        # always valid
        if not display:
            return

        response = self.advanced_dialog.run()
        self.advanced_dialog.hide()
        if response == gtk.RESPONSE_OK:
            if summary_device is not None:
                self.set_summary_device(self.grub_device_entry.child.get_text())
            self.set_popcon(self.popcon_checkbutton.get_active())
            self.set_grub(self.grub_enable.get_active())
            self.set_proxy_host(self.proxy_host_entry.get_text())
            self.set_proxy_port(self.proxy_port_spinbutton.get_value_as_int())
        return True

    def toggle_grub(self, widget):
        if (widget is not None and widget.get_name() == 'grub_enable'):
            self.grub_device_entry.set_sensitive(widget.get_active())
            self.grub_device_label.set_sensitive(widget.get_active())

    def on_proxy_host_changed(self, widget):
        if widget is not None and widget.get_name() == 'proxy_host_entry':
            text = self.proxy_host_entry.get_text()
            self.proxy_port_spinbutton.set_sensitive(text != '')

    def return_to_partitioning (self):
        """If the install progress bar is up but still at the partitioning
        stage, then errors can safely return us to partitioning.
        """

        if self.installing and not self.installing_no_return:
            # Go back to the partitioner and try again.
            self.live_installer.show()
            # FIXME: ugh, can't hardcode this.
            self.pagesindex = 3
            self.dbfilter = partman.Partman(self)
            self.set_current_page(self.previous_partitioning_page)
            self.next.set_label("gtk-go-forward")
            self.translate_widget(self.next, self.locale)
            self.backup = True
            self.installing = False

    def error_dialog (self, title, msg, fatal=True):
        # TODO: cancel button as well if capb backup
        self.run_automation_error_cmd()
        # TODO cjwatson 2009-04-16: We need to call allow_change_step here
        # to get a normal cursor, but that also enables the Back/Forward
        # buttons. Cursor handling should be controllable independently.
        saved_allowed_change_step = self.allowed_change_step
        self.allow_change_step(True)
        if self.current_page is not None:
            transient = self.live_installer
        else:
            transient = self.debconf_progress_window
        if not msg:
            msg = title
        dialog = gtk.MessageDialog(transient, gtk.DIALOG_MODAL,
                                   gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, msg)
        dialog.set_title(title)
        dialog.run()
        self.allow_change_step(saved_allowed_change_step)
        dialog.hide()
        if fatal:
            self.return_to_partitioning()

    def question_dialog (self, title, msg, options, use_templates=True):
        self.run_automation_error_cmd()
        # TODO cjwatson 2009-04-16: We need to call allow_change_step here
        # to get a normal cursor, but that also enables the Back/Forward
        # buttons. Cursor handling should be controllable independently.
        saved_allowed_change_step = self.allowed_change_step
        self.allow_change_step(True)
        if self.current_page is not None:
            transient = self.live_installer
        else:
            transient = self.debconf_progress_window
        if not msg:
            msg = title
        buttons = []
        for option in options:
            if use_templates:
                text = self.get_string(option)
            else:
                text = option
            if text is None:
                text = option
            # Work around PyGTK bug; each button text must actually be a
            # subtype of str, which unicode isn't.
            text = str(text)
            buttons.extend((text, len(buttons) / 2 + 1))
        dialog = gtk.Dialog(title, transient, gtk.DIALOG_MODAL, tuple(buttons))
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        label = gtk.Label(msg)
        label.set_line_wrap(True)
        label.set_selectable(True)
        vbox.pack_start(label)
        vbox.show_all()
        dialog.vbox.pack_start(vbox)
        response = dialog.run()
        self.allow_change_step(saved_allowed_change_step)
        dialog.hide()
        if response < 0:
            # something other than a button press, probably destroyed
            return None
        else:
            return options[response - 1]


    def refresh (self):
        while gtk.events_pending():
            gtk.main_iteration()


    # Run the UI's main loop until it returns control to us.
    def run_main_loop (self):
        self.allow_change_step(True)
        gtk.main()


    # Return control to the next level up.
    def quit_main_loop (self):
        if gtk.main_level() > 0:
            gtk.main_quit()


# Much of this timezone map widget is a rough translation of
# gnome-system-tools/src/time/tz-map.c. Thanks to Hans Petter Jansson
# <hpj@ximian.com> for that.

NORMAL_RGBA = 0xc070a0ffL
HOVER_RGBA = 0xffff60ffL
SELECTED_1_RGBA = 0xff60e0ffL
SELECTED_2_RGBA = 0x000000ffL

class TimezoneMap(object):
    def __init__(self, frontend):
        self.frontend = frontend
        self.tzdb = ubiquity.tz.Database()
        self.tzmap = ubiquity.emap.EMap()
        self.update_timeout = None
        self.point_selected = None
        self.point_hover = None
        self.location_selected = None

        self.tzmap.set_smooth_zoom(False)
        zoom_in_file = os.path.join(PATH, 'pixmaps', 'zoom-in.png')
        if os.path.exists(zoom_in_file):
            display = self.frontend.live_installer.get_display()
            pixbuf = gtk.gdk.pixbuf_new_from_file(zoom_in_file)
            self.cursor_zoom_in = gtk.gdk.Cursor(display, pixbuf, 10, 10)
        else:
            self.cursor_zoom_in = None

        self.tzmap.add_events(gtk.gdk.LEAVE_NOTIFY_MASK |
                              gtk.gdk.VISIBILITY_NOTIFY_MASK)

        self.frontend.timezone_map_window.add(self.tzmap)

        timezone_city_combo = self.frontend.timezone_city_combo

        renderer = gtk.CellRendererText()
        timezone_city_combo.pack_start(renderer, True)
        timezone_city_combo.add_attribute(renderer, 'text', 0)
        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        timezone_city_combo.set_model(list_store)

        prev_continent = ''
        for location in self.tzdb.locations:
            self.tzmap.add_point("", location.longitude, location.latitude,
                                 NORMAL_RGBA)
            zone_bits = location.zone.split('/')
            if len(zone_bits) == 1:
                continue
            continent = zone_bits[0]
            if continent != prev_continent:
                list_store.append(['', None])
                list_store.append(["--- %s ---" % continent, None])
                prev_continent = continent
            human_zone = '/'.join(zone_bits[1:]).replace('_', ' ')
            list_store.append([human_zone, location.zone])

        self.tzmap.connect("map-event", self.mapped)
        self.tzmap.connect("unmap-event", self.unmapped)
        self.tzmap.connect("motion-notify-event", self.motion)
        self.tzmap.connect("button-press-event", self.button_pressed)
        self.tzmap.connect("leave-notify-event", self.out_map)

        timezone_city_combo.connect("changed", self.city_changed)

    def set_city_text(self, name):
        model = self.frontend.timezone_city_combo.get_model()
        iterator = model.get_iter_first()
        while iterator is not None:
            location = model.get_value(iterator, 1)
            if location == name:
                self.frontend.timezone_city_combo.set_active_iter(iterator)
                break
            iterator = model.iter_next(iterator)

    def set_zone_text(self, location):
        offset = location.utc_offset
        if offset >= datetime.timedelta(0):
            minuteoffset = int(offset.seconds / 60)
        else:
            minuteoffset = int(offset.seconds / 60 - 1440)
        if location.zone_letters == 'GMT':
            text = location.zone_letters
        else:
            text = "%s (GMT%+d:%02d)" % (location.zone_letters,
                                         minuteoffset / 60, minuteoffset % 60)
        self.frontend.timezone_zone_text.set_text(text)
        translations = gettext.translation('iso_3166',
                                           languages=[self.frontend.locale],
                                           fallback=True)
        self.frontend.timezone_country_text.set_text(
            translations.ugettext(location.human_country))
        self.update_current_time()

    def update_current_time(self):
        if self.location_selected is not None:
            try:
                now = datetime.datetime.now(self.location_selected.info)
                self.frontend.timezone_time_text.set_text(now.strftime('%X'))
            except ValueError:
                # Some versions of Python have problems with clocks set
                # before the epoch (http://python.org/sf/1646728).
                self.frontend.timezone_time_text.set_text('<clock error>')

    def set_tz_from_name(self, name):
        (longitude, latitude) = (0.0, 0.0)

        for location in self.tzdb.locations:
            if location.zone == name:
                (longitude, latitude) = (location.longitude, location.latitude)
                break
        else:
            return

        if self.point_selected is not None:
            self.tzmap.point_set_color_rgba(self.point_selected, NORMAL_RGBA)

        self.point_selected = self.tzmap.get_closest_point(longitude, latitude,
                                                           False)

        self.location_selected = location
        self.set_city_text(self.location_selected.zone)
        self.set_zone_text(self.location_selected)
        self.frontend.allow_go_forward(True)

    def city_changed(self, widget):
        iterator = widget.get_active_iter()
        if iterator is not None:
            model = widget.get_model()
            location = model.get_value(iterator, 1)
            if location is not None:
                self.set_tz_from_name(location)

    def get_selected_tz_name(self):
        if self.location_selected is not None:
            return self.location_selected.zone
        else:
            return None

    def location_from_point(self, point):
        if point is None:
            return None

        (longitude, latitude) = point.get_location()

        best_location = None
        best_distance = None
        for location in self.tzdb.locations:
            if (abs(location.longitude - longitude) <= 1.0 and
                abs(location.latitude - latitude) <= 1.0):
                distance = ((location.longitude - longitude) ** 2 +
                            (location.latitude - latitude) ** 2) ** 0.5
                if best_distance is None or distance < best_distance:
                    best_location = location
                    best_distance = distance

        return best_location

    def timeout(self):
        self.update_current_time()

        if self.point_selected is None:
            return True

        if self.point_selected.get_color_rgba() == SELECTED_1_RGBA:
            self.tzmap.point_set_color_rgba(self.point_selected,
                                            SELECTED_2_RGBA)
        else:
            self.tzmap.point_set_color_rgba(self.point_selected,
                                            SELECTED_1_RGBA)

        return True

    def mapped(self, widget, event):
        if self.update_timeout is None:
            self.update_timeout = gobject.timeout_add(100, self.timeout)

    def unmapped(self, widget, event):
        if self.update_timeout is not None:
            gobject.source_remove(self.update_timeout)
            self.update_timeout = None

    def motion(self, widget, event):
        if self.tzmap.get_magnification() <= 1.0:
            if self.cursor_zoom_in is not None:
                self.frontend.live_installer.window.set_cursor(
                    self.cursor_zoom_in)
        else:
            self.frontend.live_installer.window.set_cursor(None)

            (longitude, latitude) = self.tzmap.window_to_world(event.x,
                                                               event.y)

            if (self.point_hover is not None and
                self.point_hover != self.point_selected):
                self.tzmap.point_set_color_rgba(self.point_hover, NORMAL_RGBA)

            self.point_hover = self.tzmap.get_closest_point(longitude,
                                                            latitude, True)

            if self.point_hover != self.point_selected:
                self.tzmap.point_set_color_rgba(self.point_hover, HOVER_RGBA)

        return True

    def out_map(self, widget, event):
        if event.mode != gtk.gdk.CROSSING_NORMAL:
            return False

        if (self.point_hover is not None and
            self.point_hover != self.point_selected):
            self.tzmap.point_set_color_rgba(self.point_hover, NORMAL_RGBA)

        self.point_hover = None

        self.frontend.live_installer.window.set_cursor(None)

        return True

    def button_pressed(self, widget, event):
        (longitude, latitude) = self.tzmap.window_to_world(event.x, event.y)

        if event.button != 1:
            self.tzmap.zoom_out()
            if self.cursor_zoom_in is not None:
                self.frontend.live_installer.window.set_cursor(
                    self.cursor_zoom_in)
        elif self.tzmap.get_magnification() <= 1.0:
            self.tzmap.zoom_to_location(longitude, latitude)
            if self.cursor_zoom_in is not None:
                self.frontend.live_installer.window.set_cursor(None)
        else:
            if self.point_selected is not None:
                self.tzmap.point_set_color_rgba(self.point_selected,
                                                NORMAL_RGBA)
            self.point_selected = self.point_hover

            new_location_selected = \
                self.location_from_point(self.point_selected)
            if new_location_selected is not None:
                old_city = self.get_selected_tz_name()
                if old_city is None or old_city != new_location_selected.zone:
                    self.set_city_text(new_location_selected.zone)
                    self.set_zone_text(new_location_selected)
            self.location_selected = new_location_selected
            self.frontend.allow_go_forward(self.location_selected is not None)

        return True

# vim:ai:et:sts=4:tw=80:sw=4:
