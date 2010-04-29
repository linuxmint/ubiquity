# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
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
import subprocess
import traceback
import syslog
import atexit
import signal
import xml.sax.saxutils
import gettext

import dbus
import pygtk
import gtk
pygtk.require('2.0')
import pango
import warnings
warnings.filterwarnings('ignore', 'error opening config file', pango.Warning)
import gobject
gobject.threads_init()
import glib

import debconf

from ubiquity import filteredcommand, gconftool, i18n, osextras, validation, \
                     wrap_label
from ubiquity.misc import *
from ubiquity.plugin import Plugin
from ubiquity.components import install, partman_commit
import ubiquity.progressposition
import ubiquity.frontend.base
from ubiquity.frontend.base import BaseFrontend

# We create class attributes dynamically from UI files, and it's far too
# tedious to list them all.
__pychecker__ = 'no-classattr'

# Define global path
PATH = '/usr/share/ubiquity'

# Define ui path
UIDIR = os.path.join(PATH, 'gtk')

# Define locale path
LOCALEDIR = "/usr/share/locale"

def wrap_fix(w, allocation):
    # Until the extended layout branch of GTK+ gets merged (bgo #101968).
    # We cannot short circuit this function if the layout width or height is
    # unchanged as we might have switched text direction (by selecting an RTL
    # language) since the last time the label was processed.  Fortunately,
    # size-allocate is not called often once past the language page.
    layout = w.get_layout()
    old_width, old_height = layout.get_size()
    layout.set_width(allocation.width * pango.SCALE)
    unused, height = layout.get_size()
    w.set_size_request(-1, height / pango.SCALE)

def process_labels(w):
    if isinstance(w, gtk.Container):
        children = w.get_children()
        for c in children:
            process_labels(c)
    elif isinstance(w, gtk.Label):
        if w.get_line_wrap():
            w.connect_after('size-allocate', wrap_fix)
        w.set_property('can-focus', False)

class Controller(ubiquity.frontend.base.Controller):
    def __init__(self, wizard):
        ubiquity.frontend.base.Controller.__init__(self, wizard)
        self.grub_options = wizard.grub_options

    def add_builder(self, builder):
        self._wizard.builders.append(builder)

    def translate(self, lang=None, just_me=True, not_me=False, reget=False):
        if lang:
            self._wizard.locale = lang
        self._wizard.translate_pages(lang, just_me, not_me, reget)

    def allow_go_forward(self, allowed):
        try:
             self._wizard.allow_go_forward(allowed)
        except AttributeError:
            pass

    def allow_go_backward(self, allowed):
        try:
            self._wizard.allow_go_backward(allowed)
        except AttributeError:
            pass

    def allow_change_step(self, allowed):
        try:
            self._wizard.allow_change_step(allowed)
        except AttributeError:
            pass

    def allowed_change_step(self):
        return self._wizard.allowed_change_step

    def go_forward(self):
        self._wizard.next.activate()

    def go_backward(self):
        self._wizard.back.activate()

    def go_to_page(self, widget):
        self._wizard.set_current_page(self._wizard.steps.page_num(widget))

    def toggle_top_level(self):
        if self._wizard.live_installer.get_property('visible'):
            self._wizard.live_installer.hide()
        else:
            self._wizard.live_installer.show()
        self._wizard.refresh()

    def get_string(self, name, lang=None, prefix=None):
        return self._wizard.get_string(name, lang, prefix)

class Wizard(BaseFrontend):

    def __init__(self, distro):
        def add_subpage(self, steps, name):
            """Inserts a subpage into the notebook.  This assumes the file
            shares the same base name as the page you are looking for."""
            widget = None
            uifile = UIDIR + '/' + name + '.ui'
            if os.path.exists(uifile):
                self.builder.add_from_file(uifile)
                widget = self.builder.get_object(name)
                steps.append_page(widget)
            else:
                print >>sys.stderr, 'Could not find ui file %s' % name
            return widget

        def add_widget(self, widget):
            """Make a widget callable by the toplevel."""
            if not isinstance(widget, gtk.Widget):
                return
            widget.set_name(gtk.Buildable.get_name(widget))
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
        self.language_questions = ('live_installer', 'step_label',
                                   'quit', 'back', 'next',
                                   'warning_dialog', 'warning_dialog_label',
                                   'cancelbutton', 'exitbutton')
        self.current_page = None
        self.backup = None
        self.allowed_change_step = True
        self.allowed_go_backward = True
        self.allowed_go_forward = True
        self.stay_on_page = False
        self.progress_position = ubiquity.progressposition.ProgressPosition()
        self.progress_cancelled = False
        self.default_keyboard_layout = None
        self.default_keyboard_variant = None
        self.installing = False
        self.installing_no_return = False
        self.returncode = 0
        self.history = []
        self.builder = gtk.Builder()
        self.grub_options = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)

        self.laptop = execute("laptop-detect")

        # set default language
        self.locale = i18n.reset_locale(self)

        gobject.timeout_add(30000, self.poke_screensaver)

        # To get a "busy mouse":
        self.watch = gtk.gdk.Cursor(gtk.gdk.WATCH)

        # set custom language
        self.set_locales()

        gtk.window_set_default_icon_from_file('/usr/share/pixmaps/'
                                              'ubiquity.png')

        # load the main interface
        self.builder.add_from_file('%s/ubiquity.ui' % UIDIR)
        
        # load the main install window
        self.builder.add_from_file('%s/install_window.ui' % UIDIR)

        self.builders = [self.builder]
        self.pages = []
        self.pagesindex = 0
        self.pageslen = 0
        self.user_pageslen = 0
        steps = self.builder.get_object("steps")
        found_install = False
        for mod in self.modules:
            if hasattr(mod.module, 'PageGtk'):
                mod.ui_class = mod.module.PageGtk
                mod.controller = Controller(self)
                mod.ui = mod.ui_class(mod.controller)
                widgets = mod.ui.get('plugin_widgets')
                optional_widgets = mod.ui.get('plugin_optional_widgets')
                if not found_install:
                    found_install = mod.ui.get('plugin_is_install')
                if widgets or optional_widgets:
                    def fill_out(widget_list):
                        rv = []
                        if not isinstance(widget_list, list):
                            widget_list = [widget_list]
                        for w in widget_list:
                            if not w: continue
                            if isinstance(w, str):
                                w = add_subpage(self, steps, w)
                            else:
                                steps.append_page(w)
                            rv.append(w)
                        return rv
                    mod.widgets = fill_out(widgets)
                    mod.optional_widgets = fill_out(optional_widgets)
                    mod.all_widgets = mod.widgets + mod.optional_widgets
                    for w in mod.all_widgets:
                        process_labels(w)
                    self.user_pageslen += len(mod.widgets)
                    self.pageslen += 1
                    self.pages.append(mod)

        #If no plugins declare they are install, then we'll say the last one is
        if not found_install:
            self.pages[self.pageslen - 1].ui.plugin_is_install = True

        self.toplevels = set()
        for builder in self.builders:
            for widget in builder.get_objects():
                add_widget(self, widget)
                if isinstance(widget, gtk.Window):
                    self.toplevels.add(widget)
        self.builder.connect_signals(self)

        self.stop_debconf()
        self.translate_widgets(reget=True)

        self.customize_installer()

    def all_children(self, parent):
        if isinstance(parent, gtk.Container):
            def recurse(x, y):
                return x + self.all_children(y)
            rv = reduce(recurse, parent.get_children(), [parent])
            return rv
        else:
            return [parent]

    def translate_pages(self, lang=None, just_current=True, not_current=False, reget=False):
        current_page = self.pages[self.pagesindex]
        if just_current:
            pages = [current_page]
        else:
            pages = self.pages

        if reget:
            self.translate_reget(lang)

        widgets = []
        for p in pages:
            # There's no sense retranslating the page we're leaving.
            if not_current and p == current_page:
                continue
            # Allow plugins to provide a hook for translation.
            if hasattr(p.ui, 'plugin_translate'):
                try:
                    p.ui.plugin_translate(lang or self.locale)
                except Exception, e:
                    print >>sys.stderr, 'Could not translate page (%s): %s' \
                                        % (p.module.NAME, str(e))
            prefix = p.ui.get('plugin_prefix')
            for w in p.all_widgets:
                for c in self.all_children(w):
                    widgets.append((c, prefix))
        if not just_current:
            for toplevel in self.toplevels:
                if toplevel.name != 'live_installer':
                    for c in self.all_children(toplevel):
                        widgets.append((c, None))
        self.translate_widgets(lang=lang, widgets=widgets, reget=False)

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
            dialog.set_has_separator(False)
            dialog.run()
            sys.exit(1)

        self.disable_volume_manager()

        # show interface
        self.allow_change_step(True)

        # Auto-connecting signals with additional parameters does not work.
        self.grub_new_device_entry.connect('changed', self.grub_verify_loop,
            self.grub_fail_okbutton)

        if 'UBIQUITY_AUTOMATIC' in os.environ:
            self.debconf_progress_start(0, self.pageslen,
                self.get_string('ubiquity/install/checking'))
            self.debconf_progress_window.set_title(
                self.get_string('ubiquity/install/title'))
            self.install_progress_window.set_title(
                self.get_string('ubiquity/install/title'))
            self.refresh()

        self.set_current_page(0)

        while(self.pagesindex < len(self.pages)):
            if self.current_page is None:
                return self.returncode

            if not self.pages[self.pagesindex].filter_class:
                # This page is just a UI page
                self.dbfilter = None
                self.dbfilter_status = None
                if self.set_page(self.pages[self.pagesindex].module.NAME):
                    self.run_main_loop()
            else:
                old_dbfilter = self.dbfilter
                if issubclass(self.pages[self.pagesindex].filter_class, Plugin):
                    ui = self.pages[self.pagesindex].ui
                else:
                    ui = None
                self.start_debconf()
                self.dbfilter = self.pages[self.pagesindex].filter_class(self, ui=ui)

                if self.dbfilter is not None and self.dbfilter != old_dbfilter:
                    self.allow_change_step(False)
                    glib.idle_add(lambda: self.dbfilter.start(auto_process=True))

                self.pages[self.pagesindex].controller.dbfilter = self.dbfilter
                gtk.main()
                self.pages[self.pagesindex].controller.dbfilter = None

            if self.backup or self.dbfilter_handle_status():
                #TODO: superm1, Jan 2010 is there some kind of way that we are entering this normally?
                #if self.installing:
                #    self.progress_loop()
                #elif
                if self.current_page is not None and not self.backup:
                    self.process_step()
                    if not self.stay_on_page:
                        self.pagesindex = self.pagesindex + 1
                    if 'UBIQUITY_AUTOMATIC' in os.environ:
                        # if no debconf_progress, create another one, set start to pageindex
                        self.debconf_progress_step(1)
                        self.refresh()
                if self.backup:
                    self.pagesindex = self.pop_history()


            while gtk.events_pending():
                gtk.main_iteration()

        if self.oem_user_config:
            self.quit_installer()
        elif not self.get_reboot_seen():
            self.live_installer.hide()
            if ('UBIQUITY_ONLY' in os.environ or
                'UBIQUITY_GREETER' in os.environ):
                txt = self.get_string('ubiquity/finished_restart_only')
                self.finished_label.set_label(txt)
                self.quit_button.hide()
            with raised_privileges():
                open('/var/run/reboot-required', "w").close()
            self.finished_dialog.set_keep_above(True)
            self.finished_dialog.run()
        elif self.get_reboot():
            self.reboot()

        return self.returncode

    def win_size_req(self, widget, req):
        s = widget.get_screen()
        m = s.get_monitor_geometry(0)
        w = -1
        h = -1

        # What's the size of the WM border?
        total_frame = widget.window.get_frame_extents()
        (cur_x, cur_y, cur_w, cur_h, depth) = widget.window.get_geometry()
        wm_w = total_frame.width - cur_w
        wm_h = total_frame.height - cur_h

        if req.width > m.width - wm_w:
            w = m.width - wm_w
        if req.height > m.height - wm_h:
            h = m.height - wm_h

        widget.set_size_request(w, h)
        widget.resize(w, h)

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

        self.live_installer.connect('size-request', self.win_size_req)

        if self.oem_config:
            self.live_installer.set_title(self.get_string('oem_config_title'))
        elif self.oem_user_config:
            self.live_installer.set_title(self.get_string('oem_user_config_title'))
            self.live_installer.set_icon_name("preferences-system")
            self.quit.hide()

        if not 'UBIQUITY_AUTOMATIC' in os.environ:
            self.live_installer.show()
        self.allow_change_step(False)

        if hasattr(self, 'stepPartAuto'):
            self.previous_partitioning_page = \
                self.steps.page_num(self.stepPartAuto)

        # The default instantiation of GtkComboBoxEntry creates a
        # GtkCellRenderer, so reuse it.
        self.grub_new_device_entry.set_model(self.grub_options)
        self.grub_new_device_entry.set_text_column(0)
        renderer = gtk.CellRendererText()
        self.grub_new_device_entry.pack_start(renderer, True)
        self.grub_new_device_entry.add_attribute(renderer, 'text', 1)

        # set initial bottom bar status
        self.allow_go_backward(False)
        
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
        if (self.oem_user_config or
            'UBIQUITY_ONLY' in os.environ or
            'UBIQUITY_GREETER' in os.environ):
            f = gtk.gdk.FUNC_RESIZE | gtk.gdk.FUNC_MAXIMIZE | gtk.gdk.FUNC_MOVE
            if not self.oem_user_config and not 'progress' in widget.get_name():
                f |= gtk.gdk.FUNC_CLOSE
            widget.window.set_functions(f)

    def set_locales(self):
        """internationalization config. Use only once."""

        domain = self.distro + '-installer'
        gettext.bindtextdomain(domain, LOCALEDIR)
        self.builder.set_translation_domain(domain)
        gettext.textdomain(domain)
        gettext.install(domain, LOCALEDIR, unicode=1)

    def translate_reget(self, lang):
        if lang is None:
            lang = self.locale
        if lang is None:
            languages = []
        else:
            languages = [lang]

        core_names = ['ubiquity/text/%s' % q for q in self.language_questions]
        core_names.append('ubiquity/text/oem_config_title')
        core_names.append('ubiquity/text/oem_user_config_title')
        core_names.append('ubiquity/imported/default-ltr')
        for stock_item in ('cancel', 'close', 'go-back', 'go-forward',
                            'ok', 'quit'):
            core_names.append('ubiquity/imported/%s' % stock_item)
        prefixes = []
        for p in self.pages:
            prefix = p.ui.get('plugin_prefix')
            if not prefix:
                prefix = 'ubiquity/text'
            if p.ui.get('plugin_is_language'):
                children = reduce(lambda x,y: x + self.all_children(y), p.all_widgets, [])
                core_names.extend([prefix+'/'+c.get_name() for c in children])
            prefixes.append(prefix)
        i18n.get_translations(languages=languages, core_names=core_names, extra_prefixes=prefixes)

    # widgets is a set of (widget, prefix) pairs
    def translate_widgets(self, lang=None, widgets=None, reget=True):
        if lang is None:
            lang = self.locale
        if widgets is None:
            widgets = [(x, None) for x in self.all_widgets]

        if reget:
            self.translate_reget(lang)

        # We always translate always-visible widgets
        for q in self.language_questions:
            if hasattr(self, q):
                widgets.append((getattr(self, q), None))

        for widget in widgets:
            self.translate_widget(widget[0], lang=lang, prefix=widget[1])

    def translate_widget(self, widget, lang=None, prefix=None):
        if isinstance(widget, gtk.Button) and widget.get_use_stock():
            widget.set_label(widget.get_label())

        text = self.get_string(widget.get_name(), lang, prefix)
        if text is None:
            return
        name = widget.get_name()

        if isinstance(widget, gtk.Label):
            if name == 'step_label':
                text = text.replace('${INDEX}', str(min(self.user_pageslen, max(1, len(self.history)))))
                text = text.replace('${TOTAL}', str(self.user_pageslen))
            elif name == 'ready_text_label' and self.oem_user_config:
                text = self.get_string('ready_text_oem_user_label', lang)
            widget.set_markup(text)

            # Ideally, these attributes would be in the ui file (and can be if
            # we bump required gtk+ to 2.16), but as long as we support glade
            # files, we can't make the change.
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
            unused = widget.get_image()

            question = i18n.map_widget_name(prefix, widget.get_name())
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
            if name == 'live_installer':
                if self.oem_config:
                    text = self.get_string('oem_config_title', lang)
                elif self.oem_user_config:
                    text = self.get_string('oem_user_config_title', lang)
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
        self.allowed_change_step = allowed

    def allow_go_backward(self, allowed):
        self.back.set_sensitive(allowed and self.allowed_change_step)
        self.allowed_go_backward = allowed

    def allow_go_forward(self, allowed):
        self.next.set_sensitive(allowed and self.allowed_change_step)
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
        dialog.set_has_separator(False)
        self.dbfilter_status = None
        label = gtk.Label(text)
        label.set_line_wrap(True)
        label.set_selectable(False)
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
            if step == "partman":
                print('dbfilter_handle_status stepPart')
                self.set_current_page(self.steps.page_num(self.stepPartAuto))
            return False

    def step_name(self, step_index):
        w = self.steps.get_nth_page(step_index)
        for p in self.pages:
            if w in p.all_widgets:
                return p.module.NAME
        return None

    def page_name(self, step_index):
        return self.steps.get_nth_page(step_index).get_name()

    def add_history(self, page, widget):
        history_entry = (page, widget)
        if self.history:
            # We may have skipped past child pages of the component.  Remove
            # the history between the page we're on and the end of the list in
            # that case.
            if history_entry in self.history:
                idx = self.history.index(history_entry)
                if idx + 1 < len(self.history):
                    self.history = self.history[:idx+1]
                    return # The page is now effectively a dup
            # We may have either jumped backward or forward over pages.
            # Correct history in that case
            new_index = self.pages.index(page)
            old_index = self.pages.index(self.history[-1][0])
            # First, pop if needed
            if new_index < old_index:
                while self.history[-1][0] != page and len(self.history) > 1:
                    self.pop_history()
            # Now push fake history if needed
            i = old_index + 1
            while i < new_index:
                for _ in self.pages[i].widgets: # add 1 for each always-on widgets
                    self.history.append((self.pages[i], None))
                i += 1

            if history_entry == self.history[-1]:
                return # Don't add the page if it's a dup
            if widget in page.optional_widgets:
                self.user_pageslen += 1
        self.history.append(history_entry)

    def pop_history(self):
        if len(self.history) < 2:
            return self.pagesindex
        old_entry = self.history.pop()
        if old_entry[1] in old_entry[0].optional_widgets:
            self.user_pageslen -= 1
        return self.pages.index(self.history[-1][0])

    def set_page(self, n):
        self.run_automation_error_cmd()
        # We only stop the backup process when we're on a page where questions
        # need to be asked, otherwise you wont be able to back up past
        # migration-assistant.
        self.backup = False
        self.live_installer.show()
        cur = None
        is_install = False
        for page in self.pages:
            if page.module.NAME == n:
                # Now ask ui class which page we want to be showing right now
                if hasattr(page.ui, 'plugin_get_current_page'):
                    cur = page.ui.call('plugin_get_current_page')
                    if isinstance(cur, str) and hasattr(self, cur):
                        cur = getattr(self, cur) # for not-yet-plugins
                elif page.widgets:
                    cur = page.widgets[0]
                elif page.optional_widgets:
                    cur = page.optional_widgets[0]
                if cur:
                    cur.show()
                    is_install = page.ui.get('plugin_is_install')
                    break
        if not cur:
            return False

        if is_install and not self.oem_user_config:
            self.next.set_label(self.get_string('install_button'))

        num = self.steps.page_num(cur)
        if num < 0:
            print >>sys.stderr, 'Invalid page found for %s: %s' % (n, str(cur))
            return False

        self.add_history(page, cur)
        self.set_current_page(num)
        if self.pagesindex == 0:
            self.allow_go_backward(False)
        elif 'UBIQUITY_AUTOMATIC' not in os.environ:
            self.allow_go_backward(True)
        return True

    def set_focus(self):
        # Make sure that something reasonable has the focus.  If the first
        # focusable item is a label or a button (often, the welcome text label
        # and the quit button), set the focus to the next button.
        if not self.live_installer.get_focus():
            self.live_installer.child_focus(gtk.DIR_TAB_FORWARD)
        focus = self.live_installer.get_focus()
        if focus:
            if focus.__class__ == gtk.Label:
                focus.select_region(-1, -1) # when it got focus, whole text was selected
                self.next.grab_focus()
            elif focus.__class__ == gtk.Button:
                self.next.grab_focus()
        return True

    def set_current_page(self, current):
        if self.steps.get_current_page() == current:
            # self.steps.set_current_page() will do nothing. Update state
            # ourselves.
            self.on_steps_switch_page(
                self.steps, self.steps.get_nth_page(current), current)
        else:
            self.steps.set_current_page(current)

    # Methods

    def switch_progress_windows(self, use_install_window=True):
        self.debconf_progress_window.hide()
        if use_install_window:
            self.old_progress_window = self.debconf_progress_window
            self.old_progress_info = self.progress_info
            self.old_progress_bar = self.progress_bar
            self.old_progress_cancel_button = self.progress_cancel_button
            
            self.debconf_progress_window = self.install_progress_window
            self.progress_info = self.install_progress_info
            self.progress_bar = self.install_progress_bar
            self.progress_cancel_button = self.install_progress_cancel_button
            self.progress_cancel_button.set_label(
                self.old_progress_cancel_button.get_label())
            
            # Set the install window to the (presumably dark) theme colors.
            a = gtk.Menu().rc_get_style()
            bg = a.bg[gtk.STATE_NORMAL]
            fg = a.fg[gtk.STATE_NORMAL]
            self.install_progress_window.modify_bg(gtk.STATE_NORMAL, bg)
            self.install_progress_info.modify_fg(gtk.STATE_NORMAL, fg)

        else:
            self.debconf_progress_window = self.old_progress_window
            self.progress_info = self.old_progress_info
            self.progress_bar = self.old_progress_bar
            self.progress_cancel_button = self.old_progress_cancel_button

    def progress_loop(self):
        """prepare, copy and config the system in the core install process."""
        self.installing = True

        syslog.syslog('progress_loop()')

        self.live_installer.hide()
        self.switch_progress_windows(use_install_window=True)

        slideshow_dir = '/usr/share/ubiquity-slideshow'
        slideshow_locale = self.slideshow_get_available_locale(slideshow_dir, self.locale)
        slideshow_main = slideshow_dir + '/slides/index.html'

        s = self.live_installer.get_screen()
        sh = s.get_height()
        sw = s.get_width()
        fail = None

        if os.path.exists(slideshow_main):
            if sh >= 600 and sw >= 800:
                slides = 'file://' + slideshow_main
                if slideshow_locale != 'c': #slideshow will use default automatically
                    slides += '#?locale=' + slideshow_locale
                    ltr = i18n.get_string('default-ltr', slideshow_locale, 'ubiquity/imported')
                    if ltr == 'default:RTL':
                        slides += '?rtl'
                try:
                    import webkit
                    webview = webkit.WebView()
                    # WebKit puts file URLs in their own domain by default.
                    # This means that anything which checks for the same origin,
                    # such as creating a XMLHttpRequest, will fail unless this
                    # is disabled.
                    # http://www.gitorious.org/webkit/webkit/commit/624b9463c33adbffa7f6705210384d0d7cf122d6
                    s = webview.get_settings()
                    s.set_property('enable-file-access-from-file-uris', True)
                    s.set_property('enable-default-context-menu', False)
                    webview.open(slides)
                    self.slideshow_frame.add(webview)
                    try:
                        import ConfigParser
                        cfg = ConfigParser.ConfigParser()
                        cfg.read(os.path.join(slideshow_dir, 'slideshow.conf'))
                        config_width = int(cfg.get('Slideshow','width'))
                        config_height = int(cfg.get('Slideshow','height'))
                    except:
                        config_width = 798
                        config_height = 451

                    webview.set_size_request(config_width, config_height)
                    webview.connect('new-window-policy-decision-requested',
                                    self.on_slideshow_link_clicked)
                    self.slideshow_frame.show_all()
                except ImportError:
                    fail = 'Webkit not present.'
            else:
                fail = 'Display < 800x600 (%sx%s).' % (sw, sh)
        else:
            fail = 'No slides present for %s.' % slideshow_dir
        if fail:
            syslog.syslog('Not displaying the slideshow: %s' % fail)

        self.debconf_progress_start(
            0, 100, self.get_string('ubiquity/install/title'))
        self.debconf_progress_region(0, 15)

        if not self.oem_user_config:
            self.start_debconf()
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

        self.start_debconf()
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

        self.run_success_cmd()

        #in case there are extra pages
        self.back.hide()
        self.quit.hide()
        self.next.set_label("gtk-go-forward")
        self.translate_widget(self.next)

        self.installing = False

    def reboot(self, *args):
        """reboot the system after installing process."""

        self.returncode = 10
        self.quit_installer()

    def do_reboot(self):
        """Callback for main program to actually reboot the machine."""

        try:
            session = dbus.Bus.get_session()
            gnome_session = session.name_has_owner('org.gnome.SessionManager')
        except dbus.exceptions.DBusException:
            gnome_session = False

        if gnome_session:
            manager = session.get_object('org.gnome.SessionManager',
                                         '/org/gnome/SessionManager')
            manager.RequestReboot()
        else:
            execute_root("reboot")

    def quit_installer(self, *args):
        """quit installer cleanly."""

        # Let the user know we're shutting down.
        self.finished_dialog.window.set_cursor(self.watch)
        self.quit_button.set_sensitive(False)
        self.reboot_button.set_sensitive(False)
        self.refresh()

        # exiting from application
        self.current_page = None
        self.warning_dialog.hide()
        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
        self.quit_main_loop()

    # Callbacks

    def on_quit_clicked(self, unused_widget):
        self.warning_dialog.show()
        # Stop processing.
        return True

    def on_quit_cancelled(self, unused_widget):
        self.warning_dialog.hide()

    def on_live_installer_delete_event(self, widget, unused_event):
        return self.on_quit_clicked(widget)

    def on_next_clicked(self, unused_widget):
        """Callback to control the installation process between steps."""

        if not self.allowed_change_step or not self.allowed_go_forward:
            return

        self.allow_change_step(False)

        step = self.page_name(self.steps.get_current_page())

        # Beware that 'step' is the step we're leaving, not the one we're
        # entering. At present it's a little awkward to define actions that
        # occur upon entering a page without unwanted side-effects when the
        # user tries to go forward but fails due to validation.
        if step == "stepPartAuto":
            self.part_advanced_warning_message.set_text('')
            self.part_advanced_warning_hbox.hide()
        if step in ("stepPartAuto", "stepPartAdvanced"):
            # TODO Ideally this should be done in the base frontend or the
            # partitioning component itself.
            options = grub_options()
            self.grub_options.clear()
            for opt in options:
                self.grub_options.append(opt)

        if self.dbfilter is not None:
            self.dbfilter.ok_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits
        else:
            self.quit_main_loop()

    def process_step(self):
        """Process and validate the results of this step."""

        # setting actual step
        step_num = self.steps.get_current_page()
        step = self.page_name(step_num)
        syslog.syslog('Step_before = %s' % step)

        if step.startswith("stepPart"):
            self.previous_partitioning_page = step_num

        # Ready to install
        if self.pages[self.pagesindex].ui.get('plugin_is_install'):
            self.progress_loop()

    def on_back_clicked(self, unused_widget):
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

        if step == "summary":
            self.next.set_label("gtk-go-forward")
            self.translate_widget(self.next)

        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits
        else:
            self.quit_main_loop()

    def on_slideshow_link_clicked(self, unused_view, unused_frame, req,
                                  unused_action, decision):
        uri = req.get_uri()
        decision.ignore()
        subprocess.Popen(['sensible-browser', uri],
                         close_fds=True, preexec_fn=drop_all_privileges)
        return True

    def on_steps_switch_page (self, unused_notebook, unused_page, current):
        self.current_page = current
        self.translate_widget(self.step_label)
        name = self.step_name(current)
        if 'UBIQUITY_GREETER' in os.environ:
            if name == 'language':
                self.navigation_control.hide()
            else:
                self.navigation_control.show()

        syslog.syslog('switched to page %s' % name)

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
        if self.progress_position.depth() == 0:
            if self.current_page is not None:
                self.debconf_progress_window.set_transient_for(
                    self.live_installer)
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

    def on_progress_cancel_button_clicked (self, unused_button):
        self.progress_cancelled = True


    def debconffilter_done (self, dbfilter):
        if BaseFrontend.debconffilter_done(self, dbfilter):
            self.quit_main_loop()
            return True
        else:
            return False

    def grub_verify_loop(self, widget, okbutton):
        if widget is not None:
            if validation.check_grub_device(widget.child.get_text()):
                okbutton.set_sensitive(True)
            else:
                okbutton.set_sensitive(False)

    def return_to_partitioning (self):
        """If the install progress bar is up but still at the partitioning
        stage, then errors can safely return us to partitioning.
        """

        if self.installing and not self.installing_no_return:
            # Go back to the partitioner and try again.
            self.slideshow_frame.hide()
            self.switch_progress_windows(use_install_window=False)
            self.live_installer.show()
            self.pagesindex = -1
            for page in self.pages:
                if page.module.NAME == 'partman':
                    self.pagesindex = self.pages.index(page)
                    break
            if self.pagesindex == -1: return
            self.start_debconf()
            ui = self.pages[self.pagesindex].ui
            self.dbfilter = self.pages[self.pagesindex].filter_class(self, ui=ui)
            self.set_current_page(self.previous_partitioning_page)
            self.next.set_label("gtk-go-forward")
            self.translate_widget(self.next)
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
        dialog.set_has_separator(False)
        dialog.set_title(title)
        dialog.run()
        self.allow_change_step(saved_allowed_change_step)
        dialog.hide()
        if fatal:
            self.return_to_partitioning()

    def toggle_grub_fail (self, unused_widget):
        if self.grub_no_new_device.get_active():
            self.no_grub_warn.show()
            self.grub_new_device_entry.set_sensitive(False)
            self.abort_warn.hide()
        elif self.grub_fail_option.get_active():
            self.abort_warn.show()
            self.no_grub_warn.hide()
            self.grub_new_device_entry.set_sensitive(False)
        else:
            self.abort_warn.hide()
            self.no_grub_warn.hide()
            self.grub_new_device_entry.set_sensitive(True)

    def bootloader_dialog (self, current_device):
        l = self.skip_label.get_label()
        l = l.replace('${RELEASE}', get_release_name())
        self.skip_label.set_label(l)
        self.grub_new_device_entry.child.set_text(current_device)
        self.grub_new_device_entry.child.grab_focus()
        response = self.bootloader_fail_dialog.run()
        self.bootloader_fail_dialog.hide()
        if response == gtk.RESPONSE_OK:
            if self.grub_new_device.get_active():
                return self.grub_new_device_entry.child.get_text()
            elif self.grub_no_new_device.get_active():
                return 'skip'
            else:
                return ''
        else:
            return ''

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
        dialog.set_has_separator(False)
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        label = gtk.Label(msg)
        label.set_line_wrap(True)
        label.set_selectable(False)
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
        self.set_focus()
        gtk.main()

    # Return control to the next level up.
    pending_quits = 0
    def quit_main_loop (self):
        # We quit in an idle function, because successive calls to
        # main_quit will do nothing if the main loop hasn't had time to
        # quit.  So we stagger calls to make sure that if this function
        # is called multiple times (nested loops), it works as expected.
        def quit_decrement():
            # Defensively guard against negative pending
            self.pending_quits = max(0, self.pending_quits - 1)
            return False
        def idle_quit():
            if self.pending_quits > 1:
                gtk.quit_add(0, quit_quit)
            if gtk.main_level() > 0:
                gtk.main_quit()
            return quit_decrement()
        def quit_quit():
            # Wait until we're actually out of this main loop
            glib.idle_add(idle_quit)
            return False

        if self.pending_quits == 0:
            quit_quit()
        self.pending_quits += 1

# vim:ai:et:sts=4:tw=80:sw=4:
