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

import os
import debconf

from ubiquity import plugin
from ubiquity import i18n
from ubiquity import misc
from ubiquity import auto_update
from ubiquity import osextras

NAME = 'language'
AFTER = None
WEIGHT = 10

try:
    import lsb_release
    _ver = lsb_release.get_distro_information()['RELEASE']
except:
    _ver = '10.10'
_wget_url = 'http://changelogs.ubuntu.com/ubiquity/%s-update-available' % _ver

_release_notes_url_path = '/cdrom/.disk/release_notes_url'

class PageBase(plugin.PluginUI):
    def set_language_choices(self, unused_choices, choice_map):
        """Called with language choices and a map to localised names."""
        self.language_choice_map = dict(choice_map)

    def set_language(self, language):
        """Set the current selected language."""
        pass

    def get_language(self):
        """Get the current selected language."""
        return 'C'

    def set_oem_id(self, text):
        pass

    def get_oem_id(self):
        return ''

    def set_alpha_warning(self, show):
        self.show_alpha_warning = show

class PageGtk(PageBase):
    plugin_is_language = True
    plugin_title = 'ubiquity/text/language_heading_label'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        if self.controller.oem_user_config:
            ui_file = 'stepLanguageOnly.ui'
            self.only = True
        else:
            ui_file = 'stepLanguage.ui'
            self.only = False
        try:
            import gtk
            builder = gtk.Builder()
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], ui_file))
            builder.connect_signals(self)
            self.controller.add_builder(builder)
            self.page = builder.get_object('stepLanguage')
            self.iconview = builder.get_object('language_iconview')
            self.treeview = builder.get_object('language_treeview')
            self.oem_id_entry = builder.get_object('oem_id_entry')
            if self.controller.oem_config:
                builder.get_object('oem_id_vbox').show()

            self.release_notes_url = ''
            self.update_installer = True
            self.release_notes_label = builder.get_object('release_notes_label')
            self.release_notes_found = False
            if self.release_notes_label:
                if self.controller.oem_config or auto_update.already_updated():
                    self.update_installer = False
                try:
                    release_notes = open(_release_notes_url_path)
                    self.release_notes_url = release_notes.read().rstrip('\n')
                    release_notes.close()
                    self.release_notes_found = True
                except (KeyboardInterrupt, SystemExit):
                    raise
                except:
                    pass
            self.install_ubuntu = builder.get_object('install_ubuntu')
            self.try_ubuntu = builder.get_object('try_ubuntu')
            if not self.only:
                if not 'UBIQUITY_GREETER' in os.environ:
                    choice_section_vbox = builder.get_object('choice_section_vbox')
                    choice_section_vbox and choice_section_vbox.hide()
                else:
                    def inst(*args):
                        self.try_ubuntu.set_sensitive(False)
                        self.controller.go_forward()
                    self.install_ubuntu.connect('clicked', inst)
                    self.try_ubuntu.connect('clicked',
                        self.on_try_ubuntu_clicked)
                self.try_install_text_label = builder.get_object('try_install_text_label')
                # We do not want to show the yet to be substituted strings
                # (${MEDIUM}, etc), so don't show the core of the page until
                # it's ready.
                for w in self.page.get_children():
                    w.hide()
                if self.update_installer:
                    self.setup_network_watch()

        except Exception, e:
            self.debug('Could not create language page: %s', e)
            self.page = None
        self.plugin_widgets = self.page

    def setup_network_watch(self):
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        try:
            DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            bus.add_signal_receiver(self.network_change,
                                    'DeviceNoLongerActive',
                                    'org.freedesktop.NetworkManager',
                                    'org.freedesktop.NetworkManager',
                                    '/org/freedesktop/NetworkManager')
            bus.add_signal_receiver(self.network_change, 'StateChange',
                                    'org.freedesktop.NetworkManager',
                                    'org.freedesktop.NetworkManager',
                                    '/org/freedesktop/NetworkManager')
        except dbus.DBusException:
            return
        self.timeout_id = None
        self.wget_retcode = None
        self.wget_proc = None
        self.wget_retcode_release_notes = None
        self.wget_proc_release_notes = None
        self.network_change()

    def network_change(self, state=None):
        import gobject
        if state and (state != 4 and state != 3):
            return
        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
        self.timeout_id = gobject.timeout_add(300, self.check_returncode)
        self.timeout_id = gobject.timeout_add(300, self.check_returncode_release_notes)

    def check_returncode(self, *args):
        import subprocess
        if self.wget_retcode is not None or self.wget_proc is None:
            self.wget_proc = subprocess.Popen(
                ['wget', '-q', _wget_url, '--timeout=15', '-O', '/dev/null'])
        self.wget_retcode = self.wget_proc.poll()
        if self.wget_retcode is None:
            return True
        else:
            if self.wget_retcode == 0:
                self.update_installer = True
            else:
                self.update_installer = False
            self.update_release_notes_label()
            return False

    def check_returncode_release_notes(self, *args):
        import subprocess
        if not self.release_notes_url:
            return False
        if self.wget_retcode_release_notes is not None or self.wget_proc_release_notes is None:
            self.wget_proc_release_notes = subprocess.Popen(
                ['wget', '-q', self.release_notes_url, '--timeout=15', '-O', '/dev/null'])
        self.wget_retcode_release_notes = self.wget_proc_release_notes.poll()
        if self.wget_retcode_release_notes is None:
            return True
        else:
            if self.wget_retcode_release_notes == 0:
                self.release_notes_found = True
            else:
                self.release_notes_found = False
            self.update_release_notes_label()
            return False

    @plugin.only_this_page
    def on_try_ubuntu_clicked(self, *args):
        # Spinning cursor.
        self.controller.allow_change_step(False)
        # Queue quit.
        self.install_ubuntu.set_sensitive(False)
        self.controller._wizard.current_page = None
        self.controller.dbfilter.ok_handler()

    def set_language_choices(self, choices, choice_map):
        import gtk, gobject
        PageBase.set_language_choices(self, choices, choice_map)
        list_store = gtk.ListStore(gobject.TYPE_STRING)
        for choice in choices:
            list_store.append([choice])
        # Support both iconview and treeview
        if self.only:
            self.iconview.set_model(list_store)
            self.iconview.set_text_column(0)
            lang_per_column = self.iconview.get_allocation().height / 50
            columns = int(round(len(choices) / float(lang_per_column)))
            self.iconview.set_columns(columns)
        else:
            if len(self.treeview.get_columns()) < 1:
                column = gtk.TreeViewColumn(None, gtk.CellRendererText(), text=0)
                column.set_sizing(gtk.TREE_VIEW_COLUMN_GROW_ONLY)
                self.treeview.append_column(column)
                selection = self.treeview.get_selection()
                selection.connect('changed',
                                    self.on_language_selection_changed)
            self.treeview.set_model(list_store)

    def set_language(self, language):
        # Support both iconview and treeview
        if self.only:
            model = self.iconview.get_model()
            iterator = model.iter_children(None)
            while iterator is not None:
                if unicode(model.get_value(iterator, 0)) == language:
                    path = model.get_path(iterator)
                    self.iconview.select_path(path)
                    self.iconview.scroll_to_path(path, True, 0.5, 0.5)
                    break
                iterator = model.iter_next(iterator)
        else:
            model = self.treeview.get_model()
            iterator = model.iter_children(None)
            while iterator is not None:
                if unicode(model.get_value(iterator, 0)) == language:
                    path = model.get_path(iterator)
                    self.treeview.get_selection().select_path(path)
                    self.treeview.scroll_to_cell(
                        path, use_align=True, row_align=0.5)
                    break
                iterator = model.iter_next(iterator)
        
        if not self.only and 'UBIQUITY_GREETER' in os.environ:
            self.try_ubuntu.set_sensitive(True)
            self.install_ubuntu.set_sensitive(True)

    def get_language(self):
        # Support both iconview and treeview
        if self.only:
            model = self.iconview.get_model()
            items = self.iconview.get_selected_items()
            if not items:
                return None
            iterator = model.get_iter(items[0])
        else:
            selection = self.treeview.get_selection()
            (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            value = unicode(model.get_value(iterator, 0))
            return self.language_choice_map[value][1]

    def on_language_activated(self, *args, **kwargs):
        self.controller.go_forward()

    def on_language_selection_changed(self, *args, **kwargs):
        lang = self.get_language()
        self.controller.allow_go_forward(bool(lang))
        if not lang:
            return
        # strip encoding; we use UTF-8 internally no matter what
        lang = lang.split('.')[0]
        self.controller.translate(lang)
        import gtk
        ltr = i18n.get_string('default-ltr', lang, 'ubiquity/imported')
        if ltr == 'default:RTL':
            gtk.widget_set_default_direction(gtk.TEXT_DIR_RTL)
        else:
            gtk.widget_set_default_direction(gtk.TEXT_DIR_LTR)

        if self.only:
            # The language page for oem-config doesn't have the fancy greeter.
            return

        # TODO: Cache these.
        release = misc.get_release()
        install_medium = misc.get_install_medium()
        install_medium = i18n.get_string(install_medium, lang)
        # Set the release name (Ubuntu 10.04) and medium (USB or CD) where
        # necessary.
        w = self.try_install_text_label
        text = i18n.get_string(gtk.Buildable.get_name(w), lang)
        text = text.replace('${RELEASE}', release.name)
        text = text.replace('${MEDIUM}', install_medium)
        w.set_label(text)

        # Big buttons.
        for w in (self.try_ubuntu, self.install_ubuntu):
            text = i18n.get_string(gtk.Buildable.get_name(w), lang)
            text = text.replace('${RELEASE}', release.name)
            text = text.replace('${MEDIUM}', install_medium)
            w.get_child().set_markup('<span size="x-large">%s</span>' % text)

        # There doesn't appear to be a way to have a homogeneous layout for a
        # single row in a GtkTable.
        self.try_ubuntu.set_size_request(-1, -1)
        self.install_ubuntu.set_size_request(-1, -1)
        try_w = self.try_ubuntu.size_request()[0]
        install_w = self.install_ubuntu.size_request()[0]
        if try_w > install_w:
            self.try_ubuntu.set_size_request(try_w, -1)
            self.install_ubuntu.set_size_request(try_w, -1)
        elif install_w > try_w:
            self.try_ubuntu.set_size_request(install_w, -1)
            self.install_ubuntu.set_size_request(install_w, -1)

        # Make the forward button a consistent size, regardless of its text.
        install_label = i18n.get_string('install_button', lang)
        reboot_label = i18n.get_string('restart_to_continue', lang)
        next_button = self.controller._wizard.next
        next_label = next_button.get_label()

        next_button.set_size_request(-1, -1)
        next_w = next_button.size_request()[0]
        next_button.set_label(install_label)
        install_w = next_button.size_request()[0]
        next_button.set_label(reboot_label)
        restart_w = next_button.size_request()[0]
        next_button.set_label(next_label)
        if next_w > install_w and next_w > restart_w:
            next_button.set_size_request(next_w, -1)
        elif install_w > restart_w:
            next_button.set_size_request(install_w, -1)
        else:
            next_button.set_size_request(restart_w, -1)

        self.update_release_notes_label()
        for w in self.page.get_children():
            w.show()

    def update_release_notes_label(self):
        print "update_release_notes_label()"
        lang = self.get_language()
        if not lang:
            return
        # strip encoding; we use UTF-8 internally no matter what
        lang = lang.split('.')[0]
        # Either leave the release notes label alone (both release notes and a
        # critical update are available), set it to just the release notes,
        # just the critical update, or neither, as appropriate.
        if self.release_notes_label:
            if self.release_notes_found and self.update_installer:
                text = i18n.get_string('release_notes_label', lang)
                self.release_notes_label.set_markup(text)
                self.release_notes_label.show()
            elif self.release_notes_found:
                text = i18n.get_string('release_notes_only', lang)
                self.release_notes_label.set_markup(text)
                self.release_notes_label.show()
            elif self.update_installer:
                text = i18n.get_string('update_installer_only', lang)
                self.release_notes_label.set_markup(text)
                self.release_notes_label.show()
            else:
                self.release_notes_label.hide()

    def set_oem_id(self, text):
        return self.oem_id_entry.set_text(text)

    def get_oem_id(self):
        return self.oem_id_entry.get_text()

    def on_link_clicked(self, widget, uri):
        # Connected in glade.
        lang = self.get_language()
        lang = lang.split('.')[0] # strip encoding
        if uri == 'update':
            if not auto_update.update(self.controller._wizard):
                # no updates, so don't check again
                if self.release_notes_url:
                    text = i18n.get_string('release_notes_only', lang)
                    self.release_notes_label.set_markup(text)
                else:
                    self.release_notes_label.hide()
        elif uri == 'release-notes':
            import subprocess
            uri = self.release_notes_url.replace('${LANG}', lang)
            subprocess.Popen(['sensible-browser', uri], close_fds=True,
                             preexec_fn=misc.drop_all_privileges)
        return True

class PageKde(PageBase):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_language'
    plugin_is_language = True

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        if self.controller.oem_user_config:
            self.only = True
        else:
            self.only = False

        try:
            from PyQt4 import uic
            from PyQt4.QtGui import QWidget, QPixmap
            self.page = uic.loadUi('/usr/share/ubiquity/qt/stepLanguage.ui')
            self.combobox = self.page.language_combobox
            self.combobox.currentIndexChanged[str].connect(self.on_language_selection_changed)
            if not self.controller.oem_config:
                self.page.oem_id_label.hide()
                self.page.oem_id_entry.hide()
            
            def inst(*args):
                self.page.try_ubuntu.setEnabled(False)
                self.controller.go_forward()
            self.page.install_ubuntu.clicked.connect(inst)
            self.page.try_ubuntu.clicked.connect(self.on_try_ubuntu_clicked)
            picture1 = QPixmap("/usr/share/ubiquity/pixmaps/kubuntu-live-session.png")
            self.page.image1.setPixmap(picture1)
            self.page.image1.resize(picture1.size())
            picture2 = QPixmap("/usr/share/ubiquity/pixmaps/kubuntu-install.png")
            self.page.image2.setPixmap(picture2)
            self.page.image2.resize(picture2.size())

            self.release_notes_url = ''
            self.update_installer = True
            if self.controller.oem_config or auto_update.already_updated():
                self.update_installer = False
            self.release_notes_found = False
            try:
                release_notes = open(_release_notes_url_path)
                self.release_notes_url = release_notes.read().rstrip('\n')
                release_notes.close()
                self.release_notes_found = True
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                pass

            if self.release_notes_url:
                self.page.release_notes_label.linkActivated.connect(
                    self.on_release_notes_link)
            else:
                self.page.release_notes_label.hide()

            if not 'UBIQUITY_GREETER' in os.environ:
                self.page.try_ubuntu.hide()
                self.page.try_install_text_label.hide()
                self.page.install_ubuntu.hide()
                self.page.image1.hide()
                self.page.image2.hide()

            if self.only:
                self.page.alpha_warning_label.hide()
            self.setup_network_watch()
            # We do not want to show the yet to be substituted strings
            # (${MEDIUM}, etc), so don't show the core of the page until
            # it's ready.
            self.widgetHidden = []
            for w in self.page.children():
                if isinstance(w, QWidget) and not w.isHidden():
                    self.widgetHidden.append(w)
                    w.hide()

        except Exception, e:
            self.debug('Could not create language page: %s', e)
            self.page = None

        self.plugin_widgets = self.page

    #FIXME these three functions duplicate lots from GTK page above and from ubi-prepare.py
    def setup_network_watch(self):
        import dbus
        try:
            bus = dbus.SystemBus()
            bus.add_signal_receiver(self.network_change,
                                    'DeviceNoLongerActive',
                                    'org.freedesktop.NetworkManager',
                                    'org.freedesktop.NetworkManager',
                                    '/org/freedesktop/NetworkManager')
            bus.add_signal_receiver(self.network_change, 'StateChange',
                                    'org.freedesktop.NetworkManager',
                                    'org.freedesktop.NetworkManager',
                                    '/org/freedesktop/NetworkManager')
        except dbus.DBusException:
            return
        self.timeout_id = None
        self.wget_retcode = None
        self.wget_proc = None
        self.wget_retcode_release_notes = None
        self.wget_proc_release_notes = None
        self.network_change()

    def network_change(self, state=None):
        from PyQt4.QtCore import QTimer, SIGNAL
        if state and (state != 4 and state != 3):
            return
        QTimer.singleShot(300, self.check_returncode)
        self.timer = QTimer(self.page)
        self.timer.connect(self.timer, SIGNAL("timeout()"), self.check_returncode)
        self.timer.connect(self.timer, SIGNAL("timeout()"), self.check_returncode_release_notes)
        self.timer.start(300)

    def check_returncode(self, *args):
        import subprocess
        from PyQt4.QtCore import SIGNAL
        if self.wget_retcode is not None or self.wget_proc is None:
            self.wget_proc = subprocess.Popen(
                ['wget', '-q', _wget_url, '--timeout=15', '-O', '/dev/null'])
        self.wget_retcode = self.wget_proc.poll()
        if self.wget_retcode is None:
            return True
        else:
            if self.wget_retcode == 0:
                self.update_installer = True
            else:
                self.update_installer = False
            self.update_release_notes_label()
            self.timer.disconnect(self.timer, SIGNAL("timeout()"),
                self.check_returncode)

    def check_returncode_release_notes(self, *args):
        import subprocess
        from PyQt4.QtCore import SIGNAL
        if self.wget_retcode_release_notes is not None or self.wget_proc_release_notes is None:
            self.wget_proc_release_notes = subprocess.Popen(
                ['wget', '-q', self.release_notes_url, '--timeout=15', '-O', '/dev/null'])
        self.wget_retcode_release_notes = self.wget_proc_release_notes.poll()
        if self.wget_retcode_release_notes is None:
            return True
        else:
            if self.wget_retcode_release_notes == 0:
                self.release_notes_found = True
            else:
                self.release_notes_found = False
            self.update_release_notes_label()
            self.timer.disconnect(self.timer, SIGNAL("timeout()"),
                self.check_returncode_release_notes)

    @plugin.only_this_page
    def on_try_ubuntu_clicked(self, *args):
        # Spinning cursor.
        self.controller.allow_change_step(False)
        # Queue quit.
        self.page.install_ubuntu.setEnabled(False)
        self.controller._wizard.current_page = None
        self.controller.dbfilter.ok_handler()

    def set_alpha_warning(self, show):
        if not show and not self.only:
            self.page.alpha_warning_label.hide()
            if self.page.alpha_warning_label in self.widgetHidden:
                self.widgetHidden.remove(self.page.alpha_warning_label)

    def on_release_notes_link(self, link):
        lang = self.selected_language()
        if link == "release-notes":
            if lang:
                lang = lang.split('.')[0].lower()
                url = self.release_notes_url.replace('${LANG}', lang)
                self.openURL(url)
        elif link == "update":
            if not auto_update.update(self.controller._wizard):
                # no updates, so don't check again
                text = i18n.get_string('release_notes_only', lang)
                self.page.release_notes_label.setText(text)

    def openURL(self, url):
        from PyQt4.QtGui import QDesktopServices
        from PyQt4.QtCore import QUrl
        from ubiquity.misc import drop_privileges_save, regain_privileges_save

        # this nonsense is needed because kde doesn't want to be root
        drop_privileges_save()
        QDesktopServices.openUrl(QUrl(url))
        regain_privileges_save()

    def set_language_choices(self, choices, choice_map):
        from PyQt4.QtCore import QString
        PageBase.set_language_choices(self, choices, choice_map)
        self.combobox.clear()
        for choice in choices:
            self.combobox.addItem(QString(unicode(choice)))

    def set_language(self, language):
        from PyQt4.QtCore import QString
        index = self.combobox.findText(QString(unicode(language)))
        if index < 0:
            self.combobox.addItem("C")
        else:
            self.combobox.setCurrentIndex(index)
        
        if not self.only and 'UBIQUITY_GREETER' in os.environ:
            self.page.try_ubuntu.setEnabled(True)
            self.page.install_ubuntu.setEnabled(True)

    def get_language(self):
        lang = self.selected_language()
        return lang if lang else 'C'

    def selected_language(self):
        lang = self.combobox.currentText()
        if lang.isNull() or not hasattr(self, 'language_choice_map'):
            return None
        else:
            return self.language_choice_map[unicode(lang)][1]

    def on_language_selection_changed(self):
        lang = self.selected_language()
        if not lang:
            return
        # strip encoding; we use UTF-8 internally no matter what
        lang = lang.split('.')[0]
        self.controller.translate(lang)
        if not self.only:
            release = misc.get_release()
            install_medium = misc.get_install_medium()
            install_medium = i18n.get_string(install_medium, lang)
            for widget in (self.page.try_install_text_label,
                           self.page.try_ubuntu,
                           self.page.install_ubuntu,
                           self.page.alpha_warning_label):
                text = widget.text()
                text = text.replace('${RELEASE}', release.name)
                text = text.replace('${MEDIUM}', install_medium)
                text = text.replace('Ubuntu', 'Kubuntu')
                widget.setText(text)
                
        self.update_release_notes_label()
        for w in self.widgetHidden:
            w.show()
        self.widgetHidden = []

    def update_release_notes_label(self):
        lang = self.selected_language()
        if not lang:
            return
        # strip encoding; we use UTF-8 internally no matter what
        lang = lang.split('.')[0]
        # Either leave the release notes label alone (both release notes and a
        # critical update are available), set it to just the release notes,
        # just the critical update, or neither, as appropriate.
        if self.page.release_notes_label:
            if self.release_notes_found and self.update_installer:
                text = i18n.get_string('release_notes_label', lang)
                self.page.release_notes_label.setText(text)
                self.page.release_notes_label.show()
            elif self.release_notes_found:
                text = i18n.get_string('release_notes_only', lang)
                self.page.release_notes_label.setText(text)
                self.page.release_notes_label.show()
            elif self.update_installer:
                text = i18n.get_string('update_installer_only', lang)
                self.page.release_notes_label.setText(text)
                self.page.release_notes_label.show()
            else:
                self.page.release_notes_label.hide()

    def set_oem_id(self, text):
        return self.page.oem_id_entry.setText(text)

    def get_oem_id(self):
        return unicode(self.page.oem_id_entry.text())

class PageDebconf(PageBase):
    plugin_title = 'ubiquity/text/language_heading_label'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller

class PageNoninteractive(PageBase):
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller

    def set_language(self, language):
        """Set the current selected language."""
        # Use the language code, not the translated name
        self.language = self.language_choice_map[language][1]

    def get_language(self):
        """Get the current selected language."""
        return self.language

class Page(plugin.Plugin):
    def prepare(self, unfiltered=False):
        self.language_question = None
        self.initial_language = None
        self.db.fset('localechooser/languagelist', 'seen', 'false')
        with misc.raised_privileges():
            osextras.unlink_force('/var/lib/localechooser/preseeded')
            osextras.unlink_force('/var/lib/localechooser/langlevel')
        if self.ui.controller.oem_config:
            try:
                self.ui.set_oem_id(self.db.get('oem-config/id'))
            except debconf.DebconfError:
                pass

        show = self.db.get('ubiquity/show_alpha_warning') == 'true'
        self.ui.set_alpha_warning(show)

        localechooser_script = '/usr/lib/ubiquity/localechooser/localechooser'
        if ('UBIQUITY_FRONTEND' in os.environ and
            os.environ['UBIQUITY_FRONTEND'] == 'debconf_ui'):
            localechooser_script += '-debconf'

        questions = ['localechooser/languagelist']
        environ = {'PATH': '/usr/lib/ubiquity/localechooser:' + os.environ['PATH']}
        if 'UBIQUITY_FRONTEND' in os.environ and os.environ['UBIQUITY_FRONTEND'] == "debconf_ui":
            environ['TERM_FRAMEBUFFER'] = '1'
        else:
            environ['OVERRIDE_SHOW_ALL_LANGUAGES'] = '1'
        return (localechooser_script, questions, environ)

    def run(self, priority, question):
        if question == 'localechooser/languagelist':
            self.language_question = question
            if self.initial_language is None:
                self.initial_language = self.db.get(question)
            current_language_index = self.value_index(question)
            only_installable = misc.create_bool(self.db.get('ubiquity/only-show-installable-languages'))

            current_language, sorted_choices, language_display_map = \
                i18n.get_languages(current_language_index, only_installable)

            self.ui.set_language_choices(sorted_choices,
                                         language_display_map)
            self.ui.set_language(current_language)
            if len(sorted_choices) == 1:
                self.done = True
                return True
        return plugin.Plugin.run(self, priority, question)

    def cancel_handler(self):
        self.ui.controller.translate(just_me=False, not_me=True) # undo effects of UI translation
        plugin.Plugin.cancel_handler(self)

    def ok_handler(self):
        if self.language_question is not None:
            new_language = self.ui.get_language()
            self.preseed(self.language_question, new_language)
            if (self.initial_language is None or
                self.initial_language != new_language):
                self.db.reset('debian-installer/country')
        if self.ui.controller.oem_config:
            self.preseed('oem-config/id', self.ui.get_oem_id())
        plugin.Plugin.ok_handler(self)

    def cleanup(self):
        plugin.Plugin.cleanup(self)
        i18n.reset_locale(self.frontend)
        self.frontend.stop_debconf()
        self.ui.controller.translate(just_me=False, not_me=True, reget=True)

class Install(plugin.InstallPlugin):
    def prepare(self, unfiltered=False):
        if 'UBIQUITY_OEM_USER_CONFIG' in os.environ:
            return (['/usr/lib/ubiquity/localechooser-apply'], [])
        else:
            return (['sh', '-c',
                     '/usr/lib/ubiquity/localechooser/post-base-installer ' +
                     '&& /usr/lib/ubiquity/localechooser/finish-install'], [])

    def install(self, target, progress, *args, **kwargs):
        progress.info('ubiquity/install/locales')
        rv = plugin.InstallPlugin.install(self, target, progress, *args, **kwargs)
        if not rv:
            # fontconfig configuration needs to be adjusted based on the
            # selected locale (from language-selector-common.postinst). Ignore
            # errors.
            misc.execute('chroot', target, 'fontconfig-voodoo', '--auto', '--force', '--quiet')
        return rv
