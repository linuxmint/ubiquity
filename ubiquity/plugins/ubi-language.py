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

import locale
import os
import re

import debconf

from ubiquity import auto_update, i18n, misc, osextras, plugin


NAME = 'language'
AFTER = None
WEIGHT = 10

try:
    import lsb_release
    _ver = lsb_release.get_distro_information()['RELEASE']
except:
    _ver = '12.04'
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


class PageGtk(PageBase):
    plugin_is_language = True
    plugin_title = 'ubiquity/text/language_heading_label'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        self.timeout_id = None
        self.wget_retcode = None
        self.wget_proc = None
        if self.controller.oem_user_config:
            ui_file = 'stepLanguageOnly.ui'
            self.only = True
        else:
            ui_file = 'stepLanguage.ui'
            self.only = False
        from gi.repository import Gtk
        builder = Gtk.Builder()
        builder.add_from_file(os.path.join(
            os.environ['UBIQUITY_GLADE'], ui_file))
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
        self.updating_installer = False
        self.release_notes_label = builder.get_object('release_notes_label')
        self.release_notes_found = False
        if self.release_notes_label:
            self.release_notes_label.connect(
                'activate-link', self.on_link_clicked)
            if self.controller.oem_config or auto_update.already_updated():
                self.update_installer = False
            try:
                with open(_release_notes_url_path) as release_notes:
                    self.release_notes_url = release_notes.read().rstrip('\n')
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
                self.try_ubuntu.connect('clicked', self.on_try_ubuntu_clicked)
            self.try_install_text_label = builder.get_object(
                'try_install_text_label')
            # We do not want to show the yet to be substituted strings
            # (${MEDIUM}, etc), so don't show the core of the page until
            # it's ready.
            for w in self.page.get_children():
                w.hide()
        self.plugin_widgets = self.page

    @plugin.only_this_page
    def on_try_ubuntu_clicked(self, *args):
        if not self.controller.allowed_change_step():
            # The button's already been clicked once, so stop reacting to it.
            # LP: #911907.
            return
        # Spinning cursor.
        self.controller.allow_change_step(False)
        # Queue quit.
        self.install_ubuntu.set_sensitive(False)
        self.controller._wizard.current_page = None
        self.controller.dbfilter.ok_handler()

    def set_language_choices(self, choices, choice_map):
        from gi.repository import Gtk, GObject
        PageBase.set_language_choices(self, choices, choice_map)
        list_store = Gtk.ListStore.new([GObject.TYPE_STRING])
        longest_length = 0
        longest = ''
        for choice in choices:
            list_store.append([choice])
            # Work around the fact that GtkIconView wraps at 50px or the width
            # of the icon, which is nonexistent here. See adjust_wrap_width ()
            # in gtkiconview.c for the details.
            if self.only:
                length = len(choice)
                if length > longest_length:
                    longest_length = length
                    longest = choice
        # Support both iconview and treeview
        if self.only:
            self.iconview.set_model(list_store)
            self.iconview.set_text_column(0)
            pad = self.iconview.get_property('item-padding')
            layout = self.iconview.create_pango_layout(longest)
            self.iconview.set_item_width(layout.get_pixel_size()[0] + pad * 2)
        else:
            if len(self.treeview.get_columns()) < 1:
                column = Gtk.TreeViewColumn(
                    None, Gtk.CellRendererText(), text=0)
                column.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
                self.treeview.append_column(column)
                selection = self.treeview.get_selection()
                selection.connect(
                    'changed', self.on_language_selection_changed)
            self.treeview.set_model(list_store)

    def set_language(self, language):
        # Support both iconview and treeview
        if self.only:
            model = self.iconview.get_model()
            iterator = model.iter_children(None)
            while iterator is not None:
                if misc.utf8(model.get_value(iterator, 0)) == language:
                    path = model.get_path(iterator)
                    self.iconview.select_path(path)
                    self.iconview.scroll_to_path(path, True, 0.5, 0.5)
                    break
                iterator = model.iter_next(iterator)
        else:
            model = self.treeview.get_model()
            iterator = model.iter_children(None)
            while iterator is not None:
                if misc.utf8(model.get_value(iterator, 0)) == language:
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
            value = misc.utf8(model.get_value(iterator, 0))
            return self.language_choice_map[value][1]

    def on_language_activated(self, *args, **kwargs):
        self.controller.go_forward()

    def on_language_selection_changed(self, *args, **kwargs):
        lang = self.get_language()
        self.controller.allow_go_forward(bool(lang))
        if not lang:
            return
        if 'UBIQUITY_GREETER' in os.environ:
            misc.set_indicator_keymaps(lang)
        # strip encoding; we use UTF-8 internally no matter what
        lang = lang.split('.')[0]
        self.controller.translate(lang)
        from gi.repository import Gtk
        ltr = i18n.get_string('default-ltr', lang, 'ubiquity/imported')
        if ltr == 'default:RTL':
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        else:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)

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
        text = i18n.get_string(Gtk.Buildable.get_name(w), lang)
        text = text.replace('${RELEASE}', release.name)
        text = text.replace('${MEDIUM}', install_medium)
        w.set_label(text)

        # Big buttons.
        for w in (self.try_ubuntu, self.install_ubuntu):
            text = i18n.get_string(Gtk.Buildable.get_name(w), lang)
            text = text.replace('${RELEASE}', release.name)
            text = text.replace('${MEDIUM}', install_medium)
            w.get_child().set_markup('<span size="x-large">%s</span>' % text)

        # We need to center each button under each image *and* have a homogeous
        # size between the two buttons.
        self.try_ubuntu.set_size_request(-1, -1)
        self.install_ubuntu.set_size_request(-1, -1)
        try_w = self.try_ubuntu.size_request().width
        install_w = self.install_ubuntu.size_request().width
        if try_w > install_w:
            self.try_ubuntu.set_size_request(try_w, -1)
            self.install_ubuntu.set_size_request(try_w, -1)
        elif install_w > try_w:
            self.try_ubuntu.set_size_request(install_w, -1)
            self.install_ubuntu.set_size_request(install_w, -1)

        # Make the forward button a consistent size, regardless of its text.
        install_label = i18n.get_string('install_button', lang)
        next_button = self.controller._wizard.next
        next_label = next_button.get_label()

        next_button.set_size_request(-1, -1)
        next_w = next_button.size_request().width
        next_button.set_label(install_label)
        install_w = next_button.size_request().width
        next_button.set_label(next_label)
        if next_w > install_w:
            next_button.set_size_request(next_w, -1)
        else:
            next_button.set_size_request(install_w, -1)

        self.update_release_notes_label()
        for w in self.page.get_children():
            w.show()

    def plugin_set_online_state(self, state):
        from gi.repository import GLib
        if self.release_notes_label:
            if self.timeout_id:
                GLib.source_remove(self.timeout_id)
            if state:
                self.release_notes_label.show()
                self.timeout_id = GLib.timeout_add(
                    300, self.check_returncode)
            else:
                self.release_notes_label.hide()

    def check_returncode(self, *args):
        import subprocess
        if self.wget_retcode is not None or self.wget_proc is None:
            self.wget_proc = subprocess.Popen(
                ['wget', '-q', _wget_url, '--timeout=15', '--tries=1',
                 '-O', '/dev/null'])
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

    def update_release_notes_label(self):
        print("update_release_notes_label()")
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
            elif self.release_notes_found:
                text = i18n.get_string('release_notes_only', lang)
                self.release_notes_label.set_markup(text)
            elif self.update_installer:
                text = i18n.get_string('update_installer_only', lang)
                self.release_notes_label.set_markup(text)
            else:
                self.release_notes_label.set_markup('')

    def set_oem_id(self, text):
        return self.oem_id_entry.set_text(text)

    def get_oem_id(self):
        return self.oem_id_entry.get_text()

    def on_link_clicked(self, widget, uri):
        # Connected in glade.
        lang = self.get_language()
        if not lang:
            lang = 'C'
        lang = lang.split('.')[0]  # strip encoding
        if uri == 'update':
            if self.updating_installer:
                return True
            self.updating_installer = True
            if not auto_update.update(self.controller._wizard):
                # no updates, so don't check again
                if self.release_notes_url:
                    text = i18n.get_string('release_notes_only', lang)
                    self.release_notes_label.set_markup(text)
                else:
                    self.release_notes_label.hide()
            self.updating_installer = False
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
        self.wget_retcode = None
        self.wget_proc = None
        if self.controller.oem_user_config:
            self.only = True
        else:
            self.only = False

        try:
            from PyQt4 import uic
            from PyQt4.QtGui import QWidget, QPixmap, QIcon
            self.page = uic.loadUi('/usr/share/ubiquity/qt/stepLanguage.ui')
            self.combobox = self.page.language_combobox
            # Tell layout that all items are of uniform sizes
            # Fixes LP:1187762
            self.combobox.view().setUniformItemSizes(True)
            self.combobox.currentIndexChanged[str].connect(
                self.on_language_selection_changed)
            if not self.controller.oem_config:
                self.page.oem_widget.hide()

            def init_big_button(button, image_name):
                pix = QPixmap('/usr/share/ubiquity/qt/images/' + image_name)
                icon = QIcon(pix)
                button.setIcon(icon)
                button.setIconSize(pix.size())
                # Set a fixed height to ensure the button text is not cropped
                # when the window is resized
                button.setFixedHeight(button.sizeHint().height())

            def inst(*args):
                self.page.try_ubuntu.setEnabled(False)
                self.controller.go_forward()
            self.page.install_ubuntu.clicked.connect(inst)
            self.page.try_ubuntu.clicked.connect(self.on_try_ubuntu_clicked)
            init_big_button(self.page.install_ubuntu, 'install.png')
            init_big_button(self.page.try_ubuntu, 'try.png')

            self.release_notes_url = ''
            self.update_installer = True
            self.updating_installer = False
            if self.controller.oem_config or auto_update.already_updated():
                self.update_installer = False
            self.release_notes_found = False
            try:
                with open(_release_notes_url_path) as release_notes:
                    self.release_notes_url = release_notes.read().rstrip('\n')
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

            # We do not want to show the yet to be substituted strings
            # (${MEDIUM}, etc), so don't show the core of the page until
            # it's ready.
            self.widgetHidden = []
            for w in self.page.children():
                if isinstance(w, QWidget) and not w.isHidden():
                    self.widgetHidden.append(w)
                    w.hide()

        except Exception as e:
            self.debug('Could not create language page: %s', e)
            self.page = None

        self.plugin_widgets = self.page

    @plugin.only_this_page
    def on_try_ubuntu_clicked(self, *args):
        if not self.controller.allowed_change_step():
            # The button's already been clicked once, so stop reacting to it.
            # LP: #911907.
            return
        # Spinning cursor.
        self.controller.allow_change_step(False)
        # Queue quit.
        self.page.install_ubuntu.setEnabled(False)
        self.controller._wizard.current_page = None
        self.controller.dbfilter.ok_handler()

    def on_release_notes_link(self, link):
        lang = self.selected_language()
        if link == "release-notes":
            if lang:
                lang = lang.split('.')[0].lower()
                url = self.release_notes_url.replace('${LANG}', lang)
                self.openURL(url)
        elif link == "update":
            if self.updating_installer:
                return
            self.updating_installer = True
            if not auto_update.update(self.controller._wizard):
                # no updates, so don't check again
                text = i18n.get_string('release_notes_only', lang)
                self.page.release_notes_label.setText(text)
            self.updating_installer = False

    def openURL(self, url):
        from PyQt4.QtGui import QDesktopServices
        from PyQt4.QtCore import QUrl
        from ubiquity.misc import drop_privileges_save, regain_privileges_save

        # this nonsense is needed because kde doesn't want to be root
        drop_privileges_save()
        QDesktopServices.openUrl(QUrl(url))
        regain_privileges_save()

    def set_language_choices(self, choices, choice_map):
        PageBase.set_language_choices(self, choices, choice_map)
        self.combobox.clear()
        self.combobox.addItems(choices)

    def set_language(self, language):
        index = self.combobox.findText(str(language))
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
        if not lang or not hasattr(self, 'language_choice_map'):
            return None
        else:
            return self.language_choice_map[str(lang)][1]

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
                           self.page.install_ubuntu):
                text = widget.text()
                text = text.replace('${RELEASE}', release.name)
                text = text.replace('${MEDIUM}', install_medium)
                text = text.replace('Ubuntu', 'Kubuntu')
                widget.setText(text)

        self.update_release_notes_label()
        for w in self.widgetHidden:
            w.show()
        self.widgetHidden = []

    def plugin_set_online_state(self, state):
        from PyQt4.QtCore import QTimer, SIGNAL
        if self.page.release_notes_label:
            if state:
                self.page.release_notes_label.show()
                QTimer.singleShot(300, self.check_returncode)
                self.timer = QTimer(self.page)
                self.timer.connect(
                    self.timer, SIGNAL("timeout()"), self.check_returncode)
                self.timer.start(300)
            else:
                self.page.release_notes_label.hide()

    def check_returncode(self, *args):
        import subprocess
        from PyQt4.QtCore import SIGNAL
        if self.wget_retcode is not None or self.wget_proc is None:
            self.wget_proc = subprocess.Popen(
                ['wget', '-q', _wget_url, '--timeout=15', '--tries=1',
                 '-O', '/dev/null'])
        self.wget_retcode = self.wget_proc.poll()
        if self.wget_retcode is None:
            return True
        else:
            if self.wget_retcode == 0:
                self.update_installer = True
            else:
                self.update_installer = False
            self.update_release_notes_label()
            self.timer.disconnect(
                self.timer, SIGNAL("timeout()"), self.check_returncode)

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
            elif self.release_notes_found:
                text = i18n.get_string('release_notes_only', lang)
                self.page.release_notes_label.setText(text)
            elif self.update_installer:
                text = i18n.get_string('update_installer_only', lang)
                self.page.release_notes_label.setText(text)

    def set_oem_id(self, text):
        return self.page.oem_id_entry.setText(text)

    def get_oem_id(self):
        return str(self.page.oem_id_entry.text())


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

        localechooser_script = '/usr/lib/ubiquity/localechooser/localechooser'
        if ('UBIQUITY_FRONTEND' in os.environ and
                os.environ['UBIQUITY_FRONTEND'] == 'debconf_ui'):
            localechooser_script += '-debconf'

        questions = ['localechooser/languagelist']
        environ = {
            'PATH': '/usr/lib/ubiquity/localechooser:' + os.environ['PATH'],
        }
        if ('UBIQUITY_FRONTEND' in os.environ and
                os.environ['UBIQUITY_FRONTEND'] == "debconf_ui"):
            environ['TERM_FRAMEBUFFER'] = '1'
        else:
            environ['OVERRIDE_SHOW_ALL_LANGUAGES'] = '1'
        return localechooser_script, questions, environ

    def run(self, priority, question):
        if question == 'localechooser/languagelist':
            self.language_question = question
            if self.initial_language is None:
                self.initial_language = self.db.get(question)
            current_language_index = self.value_index(question)
            only_installable = misc.create_bool(
                self.db.get('ubiquity/only-show-installable-languages'))

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
        # Undo effects of UI translation.
        self.ui.controller.translate(just_me=False, not_me=True)
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
            command = ['/usr/share/ubiquity/localechooser-apply']
        else:
            command = [
                'sh', '-c',
                '/usr/lib/ubiquity/localechooser/post-base-installer ' +
                '&& /usr/lib/ubiquity/localechooser/finish-install',
            ]
        return command, []

    def _pam_env_lines(self, fd):
        """Yield a sequence of logical lines from a PAM environment file."""
        buf = ""
        for line in fd:
            line = line.lstrip()
            if line and line[0] != "#":
                if "#" in line:
                    line = line[:line.index("#")]
                for i in range(len(line) - 1, -1, -1):
                    if line[i].isspace():
                        break
                if line[i] == "\\":
                    # Continuation line.
                    buf = line[:i]
                else:
                    buf += line
                    yield buf
                    buf = ""
        if buf:
            yield buf

    def _pam_env_parse_file(self, path):
        """Parse a PAM environment file just as pam_env does.

        We use this for reading /etc/default/locale after configuring it.
        """
        try:
            with open(path) as fd:
                for line in self._pam_env_lines(fd):
                    line = line.lstrip()
                    if not line or line[0] == "#":
                        continue
                    if line.startswith("export "):
                        line = line[7:]
                    line = re.sub(r"[#\n].*", "", line)
                    if not re.match(r"^[A-Z_]+=", line):
                        continue
                    # pam_env's handling of quoting is crazy, but in this
                    # case it's better to imitate it than to fix it.
                    key, value = line.split("=", 1)
                    if value.startswith('"') or value.startswith("'"):
                        value = re.sub(r"[\"'](.|$)", r"\1", value[1:])
                    yield key, value
        except IOError:
            pass

    def install(self, target, progress, *args, **kwargs):
        progress.info('ubiquity/install/locales')
        rv = plugin.InstallPlugin.install(
            self, target, progress, *args, **kwargs)
        if not rv:
            locale_file = "/etc/default/locale"
            if 'UBIQUITY_OEM_USER_CONFIG' not in os.environ:
                locale_file = "/target%s" % locale_file
            for key, value in self._pam_env_parse_file(locale_file):
                if key in ("LANG", "LANGUAGE") or key.startswith("LC_"):
                    os.environ[key] = value
            # Start using the newly-generated locale, if possible.
            try:
                locale.setlocale(locale.LC_ALL, '')
            except locale.Error:
                pass
        return rv
