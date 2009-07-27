# -*- coding: UTF-8 -*-

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

from ubiquity.filteredcommand import FilteredCommand
from ubiquity import keyboard_names
from ubiquity import misc

class ConsoleSetup(FilteredCommand):
    def prepare(self):
        self.preseed('console-setup/ask_detect', 'false')

        # We need to get rid of /etc/default/console-setup, or console-setup
        # will think it's already configured and behave differently. Try to
        # save the old file for interest's sake, but it's not a big deal if
        # we can't.
        misc.regain_privileges()
        try:
            os.unlink('/etc/default/console-setup.pre-ubiquity')
        except OSError:
            pass
        try:
            os.rename('/etc/default/console-setup',
                      '/etc/default/console-setup.pre-ubiquity')
        except OSError:
            try:
                os.unlink('/etc/default/console-setup')
            except OSError:
                pass
        misc.drop_privileges()
        # Make sure debconf doesn't do anything with crazy "preseeded"
        # answers to these questions. If you want to preseed these, use the
        # *code variants.
        self.db.fset('console-setup/layout', 'seen', 'false')
        self.db.fset('console-setup/variant', 'seen', 'false')
        self.db.fset('console-setup/model', 'seen', 'false')
        self.db.fset('console-setup/codeset', 'seen', 'false')

        # Technically we should provide a version as the second argument,
        # but that isn't currently needed and it would require querying
        # apt/dpkg for the current version, which would be slow, so we don't
        # bother for now.
        return (['/usr/lib/ubiquity/console-setup/console-setup.postinst',
                 'configure'],
                ['^console-setup/layout', '^console-setup/variant'],
                {'OVERRIDE_ALLOW_PRESEEDING': '1'})

    def run(self, priority, question):
        if self.done:
            return self.succeeded

        if question == 'console-setup/layout':
            # Reset this in case we just backed up from the variant
            # question.
            self.succeeded = True
            # TODO cjwatson 2006-09-07: no console-setup support for layout
            # choice translation yet
            self.frontend.set_keyboard_choices(
                self.choices_untranslated(question))
            self.frontend.set_keyboard(self.db.get(question))
            return True
        elif question == 'console-setup/variant':
            # TODO cjwatson 2006-10-02: no console-setup support for variant
            # choice translation yet
            self.frontend.set_keyboard_variant_choices(
                self.choices_untranslated(question))
            self.frontend.set_keyboard_variant(self.db.get(question))
            # console-setup preseeding is special, and needs to be checked
            # by hand. The seen flag on console-setup/layout is used
            # internally by console-setup, so we can't just force it to
            # true.
            if ('UBIQUITY_AUTOMATIC' in os.environ and
                self.db.fget('console-setup/layoutcode', 'seen') == 'true'):
                return True
            else:
                return FilteredCommand.run(self, priority, question)
        else:
            return True

    def change_layout(self, layout):
        self.preseed('console-setup/layout', layout)
        # Back up in order to get console-setup to recalculate the list of
        # possible variants.
        self.succeeded = False
        self.exit_ui_loops()

    def ok_handler(self):
        variant = self.frontend.get_keyboard_variant()
        if variant is not None:
            self.preseed('console-setup/variant', variant)
        return FilteredCommand.ok_handler(self)

    # TODO cjwatson 2006-09-07: This is duplication from console-setup, but
    # currently difficult to avoid; we need to apply the keymap immediately
    # when the user selects it in the UI (and before they move to the next
    # page), so this needs to be fast and moving through console-setup to
    # get the corrections it applies will be too slow.
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
            if variant in ('106', 'common', 'OADG109A', 'nicola_f_bs'):
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

    def apply_keyboard(self, layout, variant):
        model = self.db.get('console-setup/modelcode')

        if layout not in keyboard_names.layouts:
            self.debug("Unknown keyboard layout '%s'" % layout)
            return
        layout = keyboard_names.layouts[layout]

        if layout not in keyboard_names.variants:
            self.debug("No known variants for layout '%s'" % layout)
            variant = ''
        elif variant in keyboard_names.variants[layout]:
            variant = keyboard_names.variants[layout][variant]
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

    def cleanup(self):
        # TODO cjwatson 2006-09-07: I'd use dexconf, but it seems reasonable
        # for somebody to edit /etc/X11/xorg.conf on the live CD and expect
        # that to be carried over to the installed system (indeed, we've
        # always supported that up to now). So we get this horrible mess
        # instead ...

        model = self.db.get('console-setup/modelcode')
        layout = self.db.get('console-setup/layoutcode')
        variant = self.db.get('console-setup/variantcode')
        options = self.db.get('console-setup/optionscode')
        self.apply_real_keyboard(model, layout, variant, options.split(','))

        if layout == '':
            return

        misc.regain_privileges()
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
        misc.drop_privileges()
