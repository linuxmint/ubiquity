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

import re
import subprocess
import codecs
import os
from ubiquity import misc

_supported_locales = None

def get_supported_locales():
    """Returns a list of all locales supported by the installation system."""
    global _supported_locales
    if _supported_locales is None:
        _supported_locales = {}
        supported = open('/usr/share/i18n/SUPPORTED')
        for line in supported:
            (locale, charset) = line.split(None, 1)
            _supported_locales[locale] = charset
        supported.close()
    return _supported_locales


_strip_context_re = None

def strip_context(question, string):
    # po-debconf context
    global _strip_context_re
    if _strip_context_re is None:
        _strip_context_re = re.compile(r'\[\s[^\[\]]*\]$')
    string = _strip_context_re.sub('', string)

    return string


_translations = None

def get_translations(languages=None, core_names=[]):
    """Returns a dictionary {name: {language: description}} of translatable
    strings.

    If languages is set to a list, then only languages in that list will be
    translated. If core_names is also set to a list, then any names in that
    list will still be translated into all languages. If either is set, then
    the dictionary returned will be built from scratch; otherwise, the last
    cached version will be returned."""

    global _translations
    if _translations is None or languages is not None or len(core_names) > 0:
        if languages is None:
            use_langs = None
        else:
            use_langs = set('c')
            for lang in languages:
                ll_cc = lang.lower().split('.')[0]
                ll = ll_cc.split('_')[0]
                use_langs.add(ll_cc)
                use_langs.add(ll)

        _translations = {}
        devnull = open('/dev/null', 'w')
        # necessary?
        def subprocess_setup():
            misc.regain_privileges()
        db = subprocess.Popen(
            ['debconf-copydb', 'templatedb', 'pipe',
             '--config=Name:pipe', '--config=Driver:Pipe',
             '--config=InFd:none',
             '--pattern=^(ubiquity|partman/text/undo_everything|partman/text/unusable|partman-basicfilesystems/bad_mountpoint|partman-basicfilesystems/text/specify_mountpoint|partman-basicmethods/text/format|partman-newworld/no_newworld|partman-partitioning|partman-target/no_root|partman-target/text/method|grub-installer/bootdev|popularity-contest/participate)'],
            stdout=subprocess.PIPE, stderr=devnull, preexec_fn=subprocess_setup)
        question = None
        descriptions = {}
        fieldsplitter = re.compile(r':\s*')

        for line in db.stdout:
            line = line.rstrip('\n')
            if ':' not in line:
                if question is not None:
                    _translations[question] = descriptions
                    descriptions = {}
                    question = None
                continue

            (name, value) = fieldsplitter.split(line, 1)
            if value == '':
                continue
            name = name.lower()
            if name == 'name':
                question = value
            elif name.startswith('description'):
                namebits = name.split('-', 1)
                if len(namebits) == 1:
                    lang = 'c'
                else:
                    lang = namebits[1].lower()
                    # TODO: recode from specified encoding
                    lang = lang.split('.')[0]
                if (use_langs is None or lang in use_langs or
                    question in core_names):
                    value = strip_context(question, value)
                    descriptions[lang] = value.replace('\\n', '\n')
            elif name.startswith('extended_description'):
                namebits = name.split('-', 1)
                if len(namebits) == 1:
                    lang = 'c'
                else:
                    lang = namebits[1].lower()
                    # TODO: recode from specified encoding
                    lang = lang.split('.')[0]
                if (use_langs is None or lang in use_langs or
                    question in core_names):
                    value = strip_context(question, value)
                    if lang not in descriptions:
                        descriptions[lang] = value.replace('\\n', '\n')
                    # TODO cjwatson 2006-09-04: a bit of a hack to get the
                    # description and extended description separately ...
                    if question in ('grub-installer/bootdev',
                                    'partman-newworld/no_newworld'):
                        descriptions["extended:%s" % lang] = \
                            value.replace('\\n', '\n')

        db.wait()
        devnull.close()

    return _translations

string_questions = {
    'new_size_label': 'partman-partitioning/new_size',
    'partition_create_heading_label': 'partman-partitioning/text/new',
    'partition_create_type_label': 'partman-partitioning/new_partition_type',
    'partition_create_mount_label': 'partman-basicfilesystems/text/specify_mountpoint',
    'partition_create_use_label': 'partman-target/text/method',
    'partition_create_place_label': 'partman-partitioning/new_partition_place',
    'partition_edit_use_label': 'partman-target/text/method',
    'partition_edit_format_label': 'partman-basicmethods/text/format',
    'partition_edit_mount_label': 'partman-basicfilesystems/text/specify_mountpoint',
    'grub_device_dialog': 'grub-installer/bootdev',
    'grub_device_label': 'grub-installer/bootdev',
    # TODO: it would be nice to have a neater way to handle stock buttons
    'quit': 'ubiquity/imported/quit',
    'back': 'ubiquity/imported/go-back',
    'next': 'ubiquity/imported/go-forward',
    'cancelbutton': 'ubiquity/imported/cancel',
    'exitbutton': 'ubiquity/imported/quit',
    'closebutton1': 'ubiquity/imported/close',
    'cancelbutton1': 'ubiquity/imported/cancel',
    'okbutton1': 'ubiquity/imported/ok',
    'advanced_cancelbutton': 'ubiquity/imported/cancel',
    'advanced_okbutton': 'ubiquity/imported/ok',
}

string_extended = set('grub_device_label')

def map_widget_name(name):
    """Map a widget name to its translatable template."""
    if '/' in name:
        question = name
    elif name in string_questions:
        question = string_questions[name]
    else:
        question = 'ubiquity/text/%s' % name
    return question

def get_string(name, lang):
    """Get the translation of a single string."""
    question = map_widget_name(name)
    translations = get_translations()
    if question not in translations:
        return None

    if lang is None:
        lang = 'c'
    else:
        lang = lang.lower()
    if name in string_extended:
        lang = 'extended:%s' % lang

    if lang in translations[question]:
        text = translations[question][lang]
    else:
        ll_cc = lang.split('.')[0]
        ll = ll_cc.split('_')[0]
        if ll_cc in translations[question]:
            text = translations[question][ll_cc]
        elif ll in translations[question]:
            text = translations[question][ll]
        elif lang.startswith('extended:'):
            text = translations[question]['extended:c']
        else:
            text = translations[question]['c']

    return unicode(text, 'utf-8', 'replace')


# Based on code by Walter Dörwald:
# http://mail.python.org/pipermail/python-list/2007-January/424460.html
def ascii_transliterate(exc):
    if not isinstance(exc, UnicodeEncodeError):
        raise TypeError("don't know how to handle %r" % exc)
    import unicodedata
    s = unicodedata.normalize('NFD', exc.object[exc.start])[:1]
    if ord(s) in range(128):
        return s, exc.start + 1
    else:
        return u'', exc.start + 1

codecs.register_error('ascii_transliterate', ascii_transliterate)

# vim:ai:et:sts=4:tw=80:sw=4:
