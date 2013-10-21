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

import codecs
from functools import reduce
import locale
import os
import re
import subprocess
import sys

from ubiquity import im_switch, misc


def reset_locale(frontend):
    frontend.start_debconf()
    di_locale = frontend.db.get('debian-installer/locale')
    if not di_locale:
        # TODO cjwatson 2006-07-17: maybe fetch
        # languagechooser/language-name and set a language based on
        # that?
        di_locale = 'en_US.UTF-8'
    if 'LANG' not in os.environ or di_locale != os.environ['LANG']:
        os.environ['LANG'] = di_locale
        os.environ['LANGUAGE'] = di_locale
        try:
            locale.setlocale(locale.LC_ALL, '')
        except locale.Error as e:
            print('locale.setlocale failed: %s (LANG=%s)' % (e, di_locale),
                  file=sys.stderr)
        im_switch.start_im()
    return di_locale


_strip_context_re = None


def strip_context(unused_question, string):
    # po-debconf context
    global _strip_context_re
    if _strip_context_re is None:
        _strip_context_re = re.compile(r'\[\s[^\[\]]*\]$')
    string = _strip_context_re.sub('', string)

    return string


_translations = None


def get_translations(languages=None, core_names=[], extra_prefixes=[]):
    """Returns a dictionary {name: {language: description}} of translatable
    strings.

    If languages is set to a list, then only languages in that list will be
    translated. If core_names is also set to a list, then any names in that
    list will still be translated into all languages. If either is set, then
    the dictionary returned will be built from scratch; otherwise, the last
    cached version will be returned."""

    global _translations
    if (_translations is None or languages is not None or core_names or
            extra_prefixes):
        if languages is None:
            use_langs = None
        else:
            use_langs = set('c')
            for lang in languages:
                ll_cc = lang.lower().split('.')[0]
                ll = ll_cc.split('_')[0]
                use_langs.add(ll_cc)
                use_langs.add(ll)

        prefixes = '|'.join((
            'ubiquity',
            'partman/text/undo_everything',
            'partman/text/unusable',
            'partman-basicfilesystems/bad_mountpoint',
            'partman-basicfilesystems/text/specify_mountpoint',
            'partman-basicmethods/text/format',
            'partman-newworld/no_newworld',
            'partman-partitioning',
            'partman-crypto',
            'partman-target/no_root',
            'partman-target/text/method',
            'grub-installer/bootdev',
            'popularity-contest/participate',
        ))
        prefixes = reduce(lambda x, y: x + '|' + y, extra_prefixes, prefixes)

        _translations = {}
        devnull = open('/dev/null', 'w')
        db = subprocess.Popen(
            ['debconf-copydb', 'templatedb', 'pipe',
             '--config=Name:pipe', '--config=Driver:Pipe',
             '--config=InFd:none',
             '--pattern=^(%s)' % prefixes],
            bufsize=8192, stdout=subprocess.PIPE, stderr=devnull,
            # necessary?
            preexec_fn=misc.regain_privileges)
        question = None
        descriptions = {}
        fieldsplitter = re.compile(br':\s*')

        for line in db.stdout:
            line = line.rstrip(b'\n')
            if b':' not in line:
                if question is not None:
                    _translations[question] = descriptions
                    descriptions = {}
                    question = None
                continue

            (name, value) = fieldsplitter.split(line, 1)
            if value == b'':
                continue
            name = name.lower()
            if name == b'name':
                question = value.decode()
            elif name.startswith(b'description'):
                namebits = name.split(b'-', 1)
                if len(namebits) == 1:
                    lang = 'c'
                    decoded_value = value.decode('ASCII', 'replace')
                else:
                    lang = namebits[1].lower().decode()
                    lang, encoding = lang.split('.', 1)
                    decoded_value = value.decode(encoding, 'replace')
                if (use_langs is None or lang in use_langs or
                        question in core_names):
                    decoded_value = strip_context(question, decoded_value)
                    descriptions[lang] = decoded_value.replace('\\n', '\n')
            elif name.startswith(b'extended_description'):
                namebits = name.split(b'-', 1)
                if len(namebits) == 1:
                    lang = 'c'
                    decoded_value = value.decode('ASCII', 'replace')
                else:
                    lang = namebits[1].lower().decode()
                    lang, encoding = lang.split('.', 1)
                    decoded_value = value.decode(encoding, 'replace')
                if (use_langs is None or lang in use_langs or
                        question in core_names):
                    decoded_value = strip_context(question, decoded_value)
                    if lang not in descriptions:
                        descriptions[lang] = decoded_value.replace('\\n', '\n')
                    # TODO cjwatson 2006-09-04: a bit of a hack to get the
                    # description and extended description separately ...
                    if question in ('grub-installer/bootdev',
                                    'partman-newworld/no_newworld',
                                    'ubiquity/text/error_updating_installer'):
                        descriptions["extended:%s" % lang] = \
                            decoded_value.replace('\\n', '\n')

        db.stdout.close()
        db.wait()
        devnull.close()

    return _translations


string_questions = {
    'new_size_label': 'partman-partitioning/new_size',
    'partition_create_heading_label': 'partman-partitioning/text/new',
    'partition_create_type_label': 'partman-partitioning/new_partition_type',
    'partition_mount_label': (
        'partman-basicfilesystems/text/specify_mountpoint'),
    'partition_use_label': 'partman-target/text/method',
    'partition_create_place_label': 'partman-partitioning/new_partition_place',
    'partition_edit_format_checkbutton': 'partman-basicmethods/text/format',
    'grub_device_dialog': 'grub-installer/bootdev',
    'grub_device_label': 'grub-installer/bootdev',
    'encryption_algorithm': 'partman-crypto/text/specify_cipher',
    'partition_encryption_key_size': 'partman-crypto/text/specify_keysize',
    'crypto_iv_algorithm': 'partman-crypto/text/specify_ivalgorithm',
    # TODO: it would be nice to have a neater way to handle stock buttons
    'quit': 'ubiquity/imported/quit',
    'back': 'ubiquity/imported/go-back',
    'cancelbutton': 'ubiquity/imported/cancel',
    'exitbutton': 'ubiquity/imported/quit',
    'closebutton1': 'ubiquity/imported/close',
    'cancelbutton1': 'ubiquity/imported/cancel',
    'okbutton1': 'ubiquity/imported/ok',
}

string_extended = set()


def map_widget_name(prefix, name):
    """Map a widget name to its translatable template."""
    if prefix is None:
        prefix = 'ubiquity/text'
    if '/' in name and not name.startswith('password/'):
        question = name
    elif name in string_questions:
        question = string_questions[name]
    else:
        if name.endswith('1'):
            name = name[:-1]
        question = '%s/%s' % (prefix, name)
    return question


def get_string(name, lang, prefix=None):
    """Get the translation of a single string."""
    question = map_widget_name(prefix, name)
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

    return text


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
        return '', exc.start + 1

codecs.register_error('ascii_transliterate', ascii_transliterate)


# Returns a tuple of (current language, sorted choices, display map).
def get_languages(current_language_index=-1, only_installable=False):
    import gzip
    import icu

    current_language = "English"

    if only_installable:
        from apt.cache import Cache
        #workaround for an issue where euid != uid and the
        #apt cache has not yet been loaded causing a SystemError
        #when libapt-pkg tries to load the Cache the first time.
        with misc.raised_privileges():
            cache = Cache()

    languagelist = gzip.open(
        '/usr/lib/ubiquity/localechooser/languagelist.data.gz')
    language_display_map = {}
    i = 0
    for line in languagelist:
        line = misc.utf8(line)
        if line == '' or line == '\n':
            continue
        code, name, trans = line.strip('\n').split(':')[1:]
        if code in ('C', 'dz', 'km'):
            i += 1
            continue
        # KDE fails to round-trip strings containing U+FEFF ZERO WIDTH
        # NO-BREAK SPACE, and we don't care about the NBSP anyway, so strip
        # it.
        #   https://bugs.launchpad.net/bugs/1001542
        #   (comment #5 and on)
        trans = trans.strip(" \ufeff")

        if only_installable:
            pkg_name = 'language-pack-%s' % code
            #special case these
            if pkg_name.endswith('_CN'):
                pkg_name = 'language-pack-zh-hans'
            elif pkg_name.endswith('_TW'):
                pkg_name = 'language-pack-zh-hant'
            elif pkg_name.endswith('_NO'):
                pkg_name = pkg_name.split('_NO')[0]
            elif pkg_name.endswith('_BR'):
                pkg_name = pkg_name.split('_BR')[0]
            try:
                pkg = cache[pkg_name]
                if not (pkg.installed or pkg.candidate):
                    i += 1
                    continue
            except KeyError:
                i += 1
                continue

        language_display_map[trans] = (name, code)
        if i == current_language_index:
            current_language = trans
        i += 1
    languagelist.close()

    if only_installable:
        del cache

    try:
        # Note that we always collate with the 'C' locale.  This is far
        # from ideal.  But proper collation always requires a specific
        # language for its collation rules (languages frequently have
        # custom sorting).  This at least gives us common sorting rules,
        # like stripping accents.
        collator = icu.Collator.createInstance(icu.Locale('C'))
    except:
        collator = None

    def compare_choice(x):
        if language_display_map[x][1] == 'C':
            return None  # place C first
        if collator:
            try:
                return collator.getCollationKey(x).getByteArray()
            except:
                pass
        # Else sort by unicode code point, which isn't ideal either,
        # but also has the virtue of sorting like-glyphs together
        return x

    sorted_choices = sorted(language_display_map, key=compare_choice)

    return current_language, sorted_choices, language_display_map


def default_locales():
    with open('/usr/lib/ubiquity/localechooser/languagelist') as languagelist:
        defaults = {}
        for line in languagelist:
            line = misc.utf8(line)
            if line == '' or line == '\n':
                continue
            bits = line.strip('\n').split(';')
            code = bits[0]
            locale = bits[4]
            defaults[code] = locale
    return defaults

# vim:ai:et:sts=4:tw=80:sw=4:
