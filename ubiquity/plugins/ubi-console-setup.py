# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005, 2006, 2007, 2008 Canonical Ltd.
# Written by Tollef Fog Heen <tfheen@ubuntu.com> and
# Colin Watson <cjwatson@ubuntu.com>
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

import re
import os

from ubiquity import plugin
from ubiquity import keyboard_names
from ubiquity import misc
from ubiquity import osextras

NAME = 'console_setup'
AFTER = 'timezone'
WEIGHT = 10

class PageGtk(plugin.PluginUI):
    plugin_title = 'ubiquity/text/keyboard_heading_label'
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        self.current_layout = None
        try:
            import gtk
            builder = gtk.Builder()
            self.controller.add_builder(builder)
            builder.add_from_file(os.path.join(os.environ['UBIQUITY_GLADE'], 'stepKeyboardConf.ui'))
            builder.connect_signals(self)
            self.page = builder.get_object('stepKeyboardConf')
            self.keyboardlayoutview = builder.get_object('keyboardlayoutview')
            self.keyboardvariantview = builder.get_object('keyboardvariantview')
            self.calculate_keymap_button = builder.get_object('deduce_layout')
            self.keyboard_test = builder.get_object('keyboard_test')
            self.calculate_keymap_button.connect('clicked', self.calculate_clicked)
        except Exception, e:
            self.debug('Could not create keyboard page: %s', e)
            self.page = None
        self.plugin_widgets = self.page

    def plugin_translate(self, lang):
        # TODO Move back into the frontend as we can check
        # isinstance(LabelledEntry and just call set_label.  We'll need to
        # properly name the debconf keys though (s/inactive_label//)
        test_label = self.controller.get_string('keyboard_test_label', lang)
        self.keyboard_test.set_label(test_label)

    @plugin.only_this_page
    def calculate_result(self, w, keymap):
        l = self.controller.dbfilter.get_locale()
        keymap = keymap.split(':')
        if len(keymap) == 1:
            keymap.append('')
        layout = keyboard_names.lang[l]['layouts_rev'][keymap[0]]
        # Temporary workaround until I fix variants_rev
        v = keyboard_names.lang[l]['variants'][keymap[0]]
        idx = v.values().index(keymap[1])
        variant = v.keys()[idx]
        self.set_keyboard(layout)
        self.set_keyboard_variant(variant)
        # FIXME choppy UI effect

        # Necessary to clean up references so self.query is garbage collected.
        self.calculate_closed()

    def calculate_closed(self, *args):
        self.query.destroy()
        # FIXME greyablebin has some interesting side effects.
        #self.controller._wizard.overlay.set_property('greyed', False)
        self.query = None

    def calculate_clicked(self, *args):
        from ubiquity.frontend.gtk_components.keyboard_query import KeyboardQuery
        self.query = KeyboardQuery(self.controller._wizard)
        self.query.connect('layout_result', self.calculate_result)
        self.query.connect('delete-event', self.calculate_closed)
        #self.controller._wizard.overlay.set_property('greyed', True)
        self.query.run()

    def on_keyboardlayoutview_row_activated(self, *args):
        self.controller.go_forward()

    @plugin.only_this_page
    def on_keyboard_layout_selected(self, *args):
        layout = self.get_keyboard()
        if layout is not None:
            self.current_layout = layout
            self.controller.dbfilter.change_layout(layout)

    def on_keyboardvariantview_row_activated(self, *args):
        self.controller.go_forward()

    @plugin.only_this_page
    def on_keyboard_variant_selected(self, *args):
        layout = self.get_keyboard()
        variant = self.get_keyboard_variant()
        if layout is not None and variant is not None:
            self.controller.dbfilter.apply_keyboard(layout, variant)

    def set_keyboard_choices(self, choices):
        import gtk, gobject
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

    def set_keyboard(self, layout):
        self.current_layout = layout
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

    def get_keyboard(self):
        selection = self.keyboardlayoutview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            return unicode(model.get_value(iterator, 0))

    def set_keyboard_variant_choices(self, choices):
        import gtk, gobject
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

    def set_keyboard_variant(self, variant):
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

    def get_keyboard_variant(self):
        selection = self.keyboardvariantview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            return unicode(model.get_value(iterator, 0))

def utf8(str):
    if isinstance(str, unicode):
        return str
    return unicode(str, 'utf-8')

class PageKde(plugin.PluginUI):
    plugin_breadcrumb = 'ubiquity/text/breadcrumb_keyboard'

    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        self.current_layout = None
        self.default_keyboard_layout = None
        self.default_keyboard_variant = None
        try:
            from PyQt4 import uic
            from PyQt4.QtGui import QVBoxLayout
            from ubiquity.frontend.kde_components.Keyboard import Keyboard
            self.page = uic.loadUi('/usr/share/ubiquity/qt/stepKeyboardConf.ui')
            self.keyboardDisplay = Keyboard(self.page.keyboard_frame)
            self.page.keyboard_frame.setLayout(QVBoxLayout())
            self.page.keyboard_frame.layout().addWidget(self.keyboardDisplay)
            #use activated instead of changed because we only want to act when the user changes the selection
            #not when we are populating the combo box
            self.page.keyboard_layout_combobox.activated.connect(self.on_keyboard_layout_selected)
            self.page.keyboard_variant_combobox.activated.connect(self.on_keyboard_variant_selected)
        except Exception, e:
            self.debug('Could not create keyboard page: %s', e)
            self.page = None
        self.plugin_widgets = self.page

    @plugin.only_this_page
    def on_keyboard_layout_selected(self, *args):
        layout = self.get_keyboard()
        l = self.controller.dbfilter.get_locale()
        if layout is not None:
            #skip updating keyboard if not using display
            if self.keyboardDisplay:
                ly = keyboard_names.lang[l]['layouts'][utf8(layout)]
                self.keyboardDisplay.setLayout(ly)

                #no variants, force update by setting none
                #if ly not in keyboard_names.lang[l]['variants']:
                #    self.keyboardDisplay.setVariant(None)

            self.current_layout = layout
            self.controller.dbfilter.change_layout(layout)

    @plugin.only_this_page
    def on_keyboard_variant_selected(self, *args):
        layout = self.get_keyboard()
        variant = self.get_keyboard_variant()

        if self.keyboardDisplay:
            var = None
            l = self.controller.dbfilter.get_locale()
            ly = keyboard_names.lang[l]['layouts'][layout]
            if variant and ly in keyboard_names.lang[l]['variants']:
                variantMap = keyboard_names.lang[l]['variants'][ly]
                var = variantMap[utf8(variant)]

            self.keyboardDisplay.setVariant(var)

        if layout is not None and variant is not None:
            self.controller.dbfilter.apply_keyboard(layout, variant)

    def set_keyboard_choices(self, choices):
        from PyQt4.QtCore import QString
        self.page.keyboard_layout_combobox.clear()
        for choice in sorted(choices):
            self.page.keyboard_layout_combobox.addItem(QString(utf8(choice)))

        if self.current_layout is not None:
            self.set_keyboard(self.current_layout)

    @plugin.only_this_page
    def set_keyboard (self, layout):
        from PyQt4.QtCore import QString
        index = self.page.keyboard_layout_combobox.findText(QString(utf8(layout)))

        if index > -1:
            self.page.keyboard_layout_combobox.setCurrentIndex(index)

        if self.keyboardDisplay:
            l = self.controller.dbfilter.get_locale()
            ly = keyboard_names.lang[l]['layouts'][utf8(layout)]
            self.keyboardDisplay.setLayout(ly)

    def get_keyboard(self):
        if self.page.keyboard_layout_combobox.currentIndex() < 0:
            return None

        return unicode(self.page.keyboard_layout_combobox.currentText())

    def set_keyboard_variant_choices(self, choices):
        from PyQt4.QtCore import QString
        self.page.keyboard_variant_combobox.clear()
        for choice in sorted(choices):
            self.page.keyboard_variant_combobox.addItem(QString(utf8(choice)))

    @plugin.only_this_page
    def set_keyboard_variant(self, variant):
        from PyQt4.QtCore import QString
        index = self.page.keyboard_variant_combobox.findText(QString(utf8(variant)))

        if index > -1:
            self.page.keyboard_variant_combobox.setCurrentIndex(index)

        if self.keyboardDisplay:
            var = None
            l = self.controller.dbfilter.get_locale()
            layout = keyboard_names.lang[l]['layouts'][self.get_keyboard()]
            if variant and layout in keyboard_names.lang[l]['variants']:
                variantMap = keyboard_names.lang[l]['variants'][layout]
                var = variantMap[utf8(variant)]

            self.keyboardDisplay.setVariant(var)

    def get_keyboard_variant(self):
        if self.page.keyboard_variant_combobox.currentIndex() < 0:
            return None

        return unicode(self.page.keyboard_variant_combobox.currentText())

class PageDebconf(plugin.PluginUI):
    plugin_title = 'ubiquity/text/keyboard_heading_label'

class PageNoninteractive(plugin.PluginUI):
    def set_keyboard_choices(self, choices):
        """Set the available keyboard layout choices."""
        pass

    def set_keyboard(self, layout):
        """Set the current keyboard layout."""
        self.current_layout = layout

    def get_keyboard(self):
        """Get the current keyboard layout."""
        return self.current_layout

    def set_keyboard_variant_choices(self, choices):
        """Set the available keyboard variant choices."""
        pass

    def set_keyboard_variant(self, variant):
        """Set the current keyboard variant."""
        self.keyboard_variant = variant

    def get_keyboard_variant(self):
        return self.keyboard_variant

class Page(plugin.Plugin):
    def prepare(self, unfiltered=False):
        self.preseed('console-setup/ask_detect', 'false')

        # We need to get rid of /etc/default/keyboard, or console-setup will
        # think it's already configured and behave differently. Try to save
        # the old file for interest's sake, but it's not a big deal if we
        # can't.
        with misc.raised_privileges():
            osextras.unlink_force('/etc/default/keyboard.pre-ubiquity')
            try:
                os.rename('/etc/default/keyboard',
                          '/etc/default/keyboard.pre-ubiquity')
            except OSError:
                osextras.unlink_force('/etc/default/keyboard')
        # Make sure debconf doesn't do anything with crazy "preseeded"
        # answers to these questions. If you want to preseed these, use the
        # *code variants.
        self.db.fset('keyboard-configuration/layout', 'seen', 'false')
        self.db.fset('keyboard-configuration/variant', 'seen', 'false')
        self.db.fset('keyboard-configuration/model', 'seen', 'false')
        self.db.fset('console-setup/codeset47', 'seen', 'false')

        # Roughly taken from console-setup's config.proto:
        di_locale = self.db.get('debian-installer/locale')
        l = di_locale.rsplit('.', 1)[0]
        if l not in keyboard_names.lang:
            self.debug("Untranslated layout '%s'" % l)
            l = l.rsplit('_', 1)[0]
        if l not in keyboard_names.lang:
            self.debug("Untranslated layout '%s'" % l)
            l = 'C'
        self._locale = l

        self.has_variants = False

        # Technically we should provide a version as the second argument,
        # but that isn't currently needed and it would require querying
        # apt/dpkg for the current version, which would be slow, so we don't
        # bother for now.
        return (['/usr/lib/ubiquity/console-setup/keyboard-configuration.postinst',
                 'configure'],
                ['^keyboard-configuration/layout', '^keyboard-configuration/variant',
                 '^keyboard-configuration/model', '^keyboard-configuration/altgr$',
                 '^keyboard-configuration/unsupported_'],
                {'OVERRIDE_ALLOW_PRESEEDING': '1',
                 'LC_ALL': di_locale,
                 'PATH': '/usr/lib/ubiquity/console-setup:' +
                         os.environ['PATH']})

    # keyboard-configuration has a complex model of whether to store defaults
    # in debconf, induced by its need to run well both in an installer context
    # and as a package.  We need to adjust this while we're running in order
    # that we can go back and forward without keyboard-configuration
    # overwriting our answers with default values.
    def store_defaults(self, store):
        self.preseed_bool(
            'keyboard-configuration/store_defaults_in_debconf_db', store,
            seen=False)

    def run(self, priority, question):
        if self.done:
            return self.succeeded

        if question == 'keyboard-configuration/layout':
            # TODO cjwatson 2006-09-07: no keyboard-configuration support
            # for layout choice translation yet
            self.ui.set_keyboard_choices(
                self.choices_untranslated(question))
            self.ui.set_keyboard(self.db.get(question))
            # Reset these in case we just backed up from the variant
            # question.
            self.store_defaults(True)
            self.has_variants = False
            self.succeeded = True
            return True
        elif question in ('keyboard-configuration/variant',
                          'keyboard-configuration/altgr'):
            if question == 'keyboard-configuration/altgr':
                if self.has_variants:
                    return True
                else:
                    # If there's only one variant, it is always the same as
                    # the layout name.
                    single_variant = self.db.get(
                        'keyboard-configuration/layout')
                    self.ui.set_keyboard_variant_choices([single_variant])
                    self.ui.set_keyboard_variant(single_variant)
            else:
                # TODO cjwatson 2006-10-02: no keyboard-configuration
                # support for variant choice translation yet
                self.has_variants = True
                self.ui.set_keyboard_variant_choices(
                    self.choices_untranslated(question))
                self.ui.set_keyboard_variant(self.db.get(question))
            # keyboard-configuration preseeding is special, and needs to be
            # checked by hand. The seen flag on
            # keyboard-configuration/layout is used internally by
            # keyboard-configuration, so we can't just force it to true.
            if ('UBIQUITY_AUTOMATIC' in os.environ and
                self.db.fget('keyboard-configuration/layoutcode', 'seen') == 'true'):
                return True
            else:
                return plugin.Plugin.run(self, priority, question)
        elif question == 'keyboard-configuration/model':
            # Backing up from the variant question inconveniently goes back
            # to the model question.  Catch this and go forward again so
            # that we can reach the layout question.
            return True
        elif question.startswith('keyboard-configuration/unsupported_'):
            response = self.frontend.question_dialog(
                self.description(question),
                self.extended_description(question),
                ('ubiquity/imported/yes', 'ubiquity/imported/no'))
            if response is None or response == 'ubiquity/imported/yes':
                self.preseed(question, 'true')
            else:
                self.preseed(question, 'false')
            return True
        else:
            return True

    def change_layout(self, layout):
        self.preseed('keyboard-configuration/layout', layout)
        self.store_defaults(False)
        # Back up in order to get keyboard-configuration to recalculate the
        # list of possible variants.
        self.succeeded = False
        self.exit_ui_loops()

    def ok_handler(self):
        variant = self.ui.get_keyboard_variant()
        if variant is not None:
            self.preseed('keyboard-configuration/variant', variant)
        return plugin.Plugin.ok_handler(self)

    # TODO cjwatson 2006-09-07: This is duplication from
    # keyboard-configuration, but currently difficult to avoid; we need to
    # apply the keymap immediately when the user selects it in the UI (and
    # before they move to the next page), so this needs to be fast and
    # moving through keyboard-configuration to get the corrections it
    # applies will be too slow.
    def adjust_keyboard(self, model, layout, variant, options):
        """Apply any necessary tweaks to the supplied model, layout, variant,
        and options."""

        if layout in ('am', 'ara', 'ben', 'bd', 'bg', 'bt', 'by', 'deva', 'ge',
                      'gh', 'gr', 'guj', 'guru', 'il', 'in', 'ir', 'iku',
                      'kan', 'kh', 'kz', 'la', 'lao', 'lk', 'mk', 'mm', 'mn',
                      'mv', 'mal', 'ori', 'pk', 'ru', 'scc', 'sy', 'syr',
                      'tel', 'th', 'tj', 'tam', 'ua', 'uz'):
            latin = False
            real_layout = 'us,%s' % layout
        elif layout == 'jp':
            if variant in ('106', 'common', 'OADG109A', 'nicola_f_bs', ''):
                latin = True
                real_layout = layout
            else:
                latin = False
                real_layout = 'jp,jp'
        elif layout == 'lt':
            latin = False
            real_layout = 'lt,lt'
        elif layout == 'me':
            if variant == 'basic' or variant.startswith('latin'):
                latin = True
                real_layout = layout
            else:
                latin = False
                real_layout = 'me,me'
        elif layout == 'rs':
            if variant == 'basic' or variant.startswith('latin'):
                latin = True
                real_layout = layout
            else:
                latin = False
                real_layout = 'rs,rs'
        else:
            latin = True
            real_layout = layout

        if latin:
            real_variant = variant
        elif real_layout == 'jp,jp':
            real_variant = '106,%s' % variant
        elif real_layout == 'lt,lt':
            if variant == 'us':
                real_variant = 'us,'
            else:
                real_variant = '%s,us' % variant
        elif real_layout == 'me,me':
            if variant == 'cyrillicyz':
                real_variant = 'latinyz,%s' % variant
            elif variant == 'cyrillicalternatequotes':
                real_variant = 'latinalternatequotes,%s' % variant
            else:
                real_variant = 'basic,%s' % variant
        elif real_layout == 'rs,rs':
            if variant == 'yz':
                real_variant = 'latinyz,%s' % variant
            elif variant == 'alternatequotes':
                real_variant = 'latinalternatequotes,%s' % variant
            else:
                real_variant = 'latin,%s' % variant
        else:
            real_variant = ',%s' % variant

        real_options = [opt for opt in options if not opt.startswith('lv3:')]
        if not latin:
            toggle = re.compile(r'^grp:.*toggle$')
            real_options = [opt for opt in real_options
                                if not toggle.match(opt)]
            # TODO cjwatson 2006-09-07: honour crazy preseeding; probably
            # not quite right, especially for Apples which may need a level
            # 3 shift
            real_options.append('grp:alt_shift_toggle')
        if layout != 'us':
            real_options.append('lv3:ralt_switch')

        real_model = model
        if model == 'pc105':
            if real_layout == 'br':
                real_model = 'abnt2'
            elif real_layout == 'jp':
                real_model = 'jp106'

        return (real_model, real_layout, real_variant, real_options)

    def get_locale(self):
        return self._locale

    def apply_keyboard(self, layout, variant):
        model = self.db.get('keyboard-configuration/modelcode')

        l = self.get_locale()
        if layout not in keyboard_names.lang[l]['layouts']:
            self.debug("Unknown keyboard layout '%s'" % layout)
            return
        layout = keyboard_names.lang[l]['layouts'][layout]

        if layout not in keyboard_names.lang[l]['variants']:
            self.debug("No known variants for layout '%s'" % layout)
            variant = ''
        elif variant in keyboard_names.lang[l]['variants'][layout]:
            variant = keyboard_names.lang[l]['variants'][layout][variant]
        else:
            self.debug("Unknown keyboard variant '%s' for layout '%s'" %
                       (variant, layout))
            return

        (model, layout, variant, options) = \
            self.adjust_keyboard(model, layout, variant, [])
        self.debug("Setting keyboard layout: %s %s %s %s" %
                   (model, layout, variant, options))
        self.apply_real_keyboard(model, layout, variant, options)

    def apply_real_keyboard(self, model, layout, variant, options):
        args = []
        if model is not None and model != '':
            args.extend(("-model", model))
        args.extend(("-layout", layout))
        if variant != '':
            args.extend(("-variant", variant))
        args.extend(("-option", ""))
        for option in options:
            args.extend(("-option", option))
        misc.execute("setxkbmap", *args)

    @misc.raise_privileges
    def rewrite_xorg_conf(self, model, layout, variant, options):
        oldconfigfile = '/etc/X11/xorg.conf'
        newconfigfile = '/etc/X11/xorg.conf.new'
        try:
            oldconfig = open(oldconfigfile)
        except IOError:
            # Did they remove /etc/X11/xorg.conf or something? Oh well,
            # better to carry on than to crash.
            return
        newconfig = open(newconfigfile, 'w')

        re_section_inputdevice = re.compile(r'\s*Section\s+"InputDevice"\s*$')
        re_driver_kbd = re.compile(r'\s*Driver\s+"kbd"\s*$')
        re_endsection = re.compile(r'\s*EndSection\s*$')
        re_option_xkbmodel = re.compile(r'(\s*Option\s*"XkbModel"\s*).*')
        re_option_xkblayout = re.compile(r'(\s*Option\s*"XkbLayout"\s*).*')
        re_option_xkbvariant = re.compile(r'(\s*Option\s*"XkbVariant"\s*).*')
        re_option_xkboptions = re.compile(r'(\s*Option\s*"XkbOptions"\s*).*')
        in_inputdevice = False
        in_inputdevice_kbd = False
        done = {'model': model == '', 'layout': False,
                'variant': variant == '', 'options': options == ''}

        for line in oldconfig:
            line = line.rstrip('\n')
            if re_section_inputdevice.match(line) is not None:
                in_inputdevice = True
            elif in_inputdevice and re_driver_kbd.match(line) is not None:
                in_inputdevice_kbd = True
            elif re_endsection.match(line) is not None:
                if in_inputdevice_kbd:
                    if not done['model']:
                        print >>newconfig, ('\tOption\t\t"XkbModel"\t"%s"' %
                                            model)
                    if not done['layout']:
                        print >>newconfig, ('\tOption\t\t"XkbLayout"\t"%s"' %
                                            layout)
                    if not done['variant']:
                        print >>newconfig, ('\tOption\t\t"XkbVariant"\t"%s"' %
                                            variant)
                    if not done['options']:
                        print >>newconfig, ('\tOption\t\t"XkbOptions"\t"%s"' %
                                            options)
                in_inputdevice = False
                in_inputdevice_kbd = False
                done = {'model': model == '', 'layout': False,
                        'variant': variant == '', 'options': options == ''}
            elif in_inputdevice_kbd:
                match = re_option_xkbmodel.match(line)
                if match is not None:
                    if model == '':
                        # hmm, not quite sure what to do here; guessing that
                        # forcing to pc105 will be reasonable
                        line = match.group(1) + '"pc105"'
                    else:
                        line = match.group(1) + '"%s"' % model
                    done['model'] = True
                else:
                    match = re_option_xkblayout.match(line)
                    if match is not None:
                        line = match.group(1) + '"%s"' % layout
                        done['layout'] = True
                    else:
                        match = re_option_xkbvariant.match(line)
                        if match is not None:
                            if variant == '':
                                continue # delete this line
                            else:
                                line = match.group(1) + '"%s"' % variant
                            done['variant'] = True
                        else:
                            match = re_option_xkboptions.match(line)
                            if match is not None:
                                if options == '':
                                    continue # delete this line
                                else:
                                    line = match.group(1) + '"%s"' % options
                                done['options'] = True
            print >>newconfig, line

        newconfig.close()
        oldconfig.close()
        os.rename(newconfigfile, oldconfigfile)

    def cleanup(self):
        # TODO cjwatson 2006-09-07: I'd use dexconf, but it seems reasonable
        # for somebody to edit /etc/X11/xorg.conf on the live CD and expect
        # that to be carried over to the installed system (indeed, we've
        # always supported that up to now). So we get this horrible mess
        # instead ...

        model = self.db.get('keyboard-configuration/modelcode')
        layout = self.db.get('keyboard-configuration/layoutcode')
        variant = self.db.get('keyboard-configuration/variantcode')
        options = self.db.get('keyboard-configuration/optionscode')
        if options:
            options_list = options.split(',')
        else:
            options_list = []
        self.apply_real_keyboard(model, layout, variant, options_list)

        plugin.Plugin.cleanup(self)

        if layout == '':
            return

        self.rewrite_xorg_conf(model, layout, variant, options)

class Install(plugin.InstallPlugin):
    def prepare(self, unfiltered=False):
        return (['/usr/share/ubiquity/console-setup-apply'], [])

    def install(self, target, progress, *args, **kwargs):
        progress.info('ubiquity/install/keyboard')
        return plugin.InstallPlugin.install(self, target, progress, *args, **kwargs)
