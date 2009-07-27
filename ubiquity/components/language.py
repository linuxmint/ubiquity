# -*- coding: UTF-8 -*-

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
import re
import locale

from ubiquity.filteredcommand import FilteredCommand
from ubiquity import i18n
from ubiquity import misc

class Language(FilteredCommand):
    def prepare(self):
        self.language_question = None
        self.db.fset('localechooser/languagelist', 'seen', 'false')
        try:
            os.unlink('/var/lib/localechooser/preseeded')
            os.unlink('/var/lib/localechooser/langlevel')
        except OSError:
            pass
        questions = ['localechooser/languagelist']
        return (['/usr/lib/ubiquity/localechooser/localechooser'], questions,
                {'PATH': '/usr/lib/ubiquity/localechooser:' + os.environ['PATH'],
                 'OVERRIDE_SHOW_ALL_LANGUAGES': '1'})

    def run(self, priority, question):
        if question == 'localechooser/languagelist':
            self.language_question = question
            current_language_index = self.value_index(question)
            current_language = "English"

            import gzip
            languagelist = gzip.open('/usr/lib/ubiquity/localechooser/languagelist.data.gz')
            language_display_map = {}
            i = 0
            for line in languagelist:
                line = unicode(line, 'utf-8')
                if line == '' or line == '\n':
                    continue
                code, name, trans = line.strip(u'\n').split(u':')[1:]
                if code in ('dz', 'km'):
                    i += 1
                    continue
                language_display_map[trans] = (name, code)
                if i == current_language_index:
                    current_language = trans
                i += 1
            languagelist.close()

            def compare_choice(x, y):
                result = cmp(language_display_map[x][1],
                             language_display_map[y][1])
                if result != 0:
                    return result
                return cmp(x, y)

            sorted_choices = sorted(language_display_map, compare_choice)
            self.frontend.set_language_choices(sorted_choices,
                                               language_display_map)
            self.frontend.set_language(current_language)

        return FilteredCommand.run(self, priority, question)

    def ok_handler(self):
        if self.language_question is not None:
            self.preseed(self.language_question, self.frontend.get_language())
        FilteredCommand.ok_handler(self)

    def cleanup(self):
        di_locale = self.db.get('debian-installer/locale')
        if di_locale not in i18n.get_supported_locales():
            di_locale = self.db.get('debian-installer/fallbacklocale')
        if di_locale != self.frontend.locale:
            self.frontend.locale = di_locale
            os.environ['LANG'] = di_locale
            os.environ['LANGUAGE'] = di_locale
            try:
                locale.setlocale(locale.LC_ALL, '')
            except locale.Error, e:
                self.debug('locale.setlocale failed: %s (LANG=%s)',
                           e, di_locale)
            misc.execute_root('fontconfig-voodoo',
                              '--auto', '--force', '--quiet')
