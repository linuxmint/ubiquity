# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2005, 2006, 2007, 2008 Canonical Ltd.
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

import errno
import fcntl
import os
import re
import signal
import subprocess
import sys

import debconf

from ubiquity import misc


# Each widget should have a run(self, priority, question) method; this
# should ask the question in whatever way is appropriate, and may then
# communicate with the debconf frontend using db. In particular, they may
# want to:
#
#   * fetch the question's description using METAGET
#   * set the question's value using SET
#   * set the question's seen flag using FSET
#
# If run() returns a false value, the next call to GO will return 30
# (backup).
#
# Widgets may also have a set(self, question, value) method; if present,
# this will be called whenever the confmodule uses SET. They may wish to use
# this to adjust the values of questions in their user interface.
#
# If present, the metaget(self, question, field) method will be called
# whenever the confmodule uses METAGET. This may be useful to spot questions
# being assembled out of individually-translatable pieces.
#
# If a widget is registered for the 'ERROR' pseudo-question, then its
# error(self, priority, question) method will be called whenever the
# confmodule asks an otherwise-unhandled question whose template has type
# error.

# command name => maximum argument count (or None if unlimited)
valid_commands = {
    'BEGINBLOCK': 0,
    'CAPB': None,
    'CLEAR': 0,
    'DATA': 3,
    'ENDBLOCK': 0,
    'FGET': 2,
    'FSET': 3,
    'GET': 1,
    'GO': 0,
    'INFO': 1,
    'INPUT': 2,
    'METAGET': 2,
    'PREVIOUS_MODULE': 0,
    'PROGRESS': 4,
    'PURGE': 0,
    'REGISTER': 2,
    'RESET': 1,
    'SET': 2,
    'SETTITLE': 1,
    'STOP': 0,
    'SUBST': 3,
    'TITLE': 1,
    'UNREGISTER': 1,
    'VERSION': 1,
    'X_LOADTEMPLATEFILE': 2
}


class DebconfFilter:
    def __init__(self, db, widgets={}, automatic=False):
        self.db = db
        self.widgets = widgets
        self.automatic = automatic
        if 'DEBCONF_DEBUG' in os.environ:
            self.debug_re = re.compile(os.environ['DEBCONF_DEBUG'])
        else:
            self.debug_re = None
        self.escaping = False
        self.progress_cancel = False
        self.progress_bars = []
        self.toread = b''
        self.toreadpos = 0
        self.question_type_cache = {}

    def debug_enabled(self, key):
        if key == 'filter' and os.environ.get('UBIQUITY_DEBUG_CORE') == '1':
            return True
        if self.debug_re is not None and self.debug_re.search(key):
            return True
        return False

    def debug(self, key, *args):
        if self.debug_enabled(key):
            import time
            # bizarre time formatting code per syslogd
            time_str = time.ctime()[4:19]
            print("%s debconf (%s): %s" % (time_str, key, ' '.join(args)),
                  file=sys.stderr)

    # Returns None if non-blocking and can't read a full line right now;
    # returns '' at end of file; otherwise as fileobj.readline().
    def tryreadline(self):
        ret = b''
        while True:
            newlinepos = self.toread.find(b'\n', self.toreadpos)
            if newlinepos != -1:
                ret = self.toread[self.toreadpos:newlinepos + 1]
                self.toreadpos = newlinepos + 1
                if self.toreadpos >= len(self.toread):
                    self.toread = b''
                    self.toreadpos = 0
                break

            try:
                text = os.read(self.subout_fd, 512)
                if text == b'':
                    ret = self.toread
                    self.toread = b''
                    self.toreadpos = 0
                    break
                self.toread += text
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return None
                else:
                    raise

        return ret.decode()

    def reply(self, code, text='', log=False):
        if self.escaping and code == 0:
            text = text.replace('\\', '\\\\').replace('\n', '\\n')
            code = 1
        ret = '%d %s' % (code, text)
        if log:
            self.debug('filter', '-->', ret)
        self.subin.write('%s\n' % ret)
        self.subin.flush()

    def question_type(self, question):
        try:
            return self.question_type_cache[question]
        except KeyError:
            try:
                qtype = self.db.metaget(question, 'Type')
            except debconf.DebconfError:
                qtype = ''
            self.question_type_cache[question] = qtype
            return qtype

    def find_widgets(self, questions, method=None):
        found = set()
        for pattern in self.widgets.keys():
            widget = self.widgets[pattern]
            if widget not in found:
                for question in questions:
                    matches = False
                    if pattern.startswith('type:') and '/' in question:
                        try:
                            qtype = self.question_type(question)
                            if qtype == pattern[5:]:
                                matches = True
                        except debconf.DebconfError:
                            pass
                    elif re.search(pattern, question):
                        matches = True
                    if matches:
                        if method is None or hasattr(widget, method):
                            found.add(widget)
                            break
        return list(found)

    def start(self, command, blocking=True, extra_env={}):
        def subprocess_setup():
            os.environ['DEBIAN_HAS_FRONTEND'] = '1'
            if 'DEBCONF_USE_CDEBCONF' in os.environ:
                # cdebconf expects to be able to redirect standard output to fd
                # 5. Make this stderr to match debconf.
                os.dup2(2, 5)
            else:
                os.environ['PERL_DL_NONLAZY'] = '1'
            os.environ['HOME'] = '/root'
            os.environ['LC_COLLATE'] = 'C'
            for key, value in extra_env.items():
                os.environ[key] = value
            # Python installs a SIGPIPE handler by default. This is bad for
            # non-Python subprocesses, which need SIGPIPE set to the default
            # action or else they won't notice if the debconffilter dies.
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)
            # Regain root.
            misc.regain_privileges()

        self.subp = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            preexec_fn=subprocess_setup, universal_newlines=True)
        self.subin = self.subp.stdin
        self.subout = self.subp.stdout
        self.subout_fd = self.subout.fileno()
        self.blocking = blocking
        if not self.blocking:
            flags = fcntl.fcntl(self.subout_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.subout_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.next_go_backup = False
        self.waiting = False

        # Always use the escape capability for our own communications with
        # the underlying frontend. This does not affect communications
        # between this filter and the confmodule.
        self.db.capb('escape')

    def process_line(self):
        line = self.tryreadline()
        if line is None:
            return True
        if line == '':
            return False

        # TODO: handle escaped input
        line = line.rstrip('\n')
        params = line.split(None, 1)
        if not params:
            return True
        command = params[0].upper()
        if len(params) > 1:
            rest = params[1]
        else:
            rest = ''

        # Split parameters according to the command name.
        if valid_commands.get(command, 0) == 0:
            params = [rest]
        elif valid_commands[command] is None:
            params = rest.split()
        else:
            params = rest.split(None, valid_commands[command] - 1)

        self.debug('filter', '<--', command, *params)

        if line == '' or line.startswith(' ') or command not in valid_commands:
            # Work around confmodules that try to send multi-line commands;
            # this works (sort of, and by fluke) in cdebconf, but debconf
            # doesn't like it.
            self.debug('filter', 'ignoring unknown (multi-line?) command')
            return True

        if command == 'CAPB':
            self.escaping = 'escape' in params
            self.progress_cancel = 'progresscancel' in params
            for widget in self.find_widgets(['CAPB'], 'capb'):
                self.debug('filter', 'capb widget found')
                widget.capb(params)
            if 'escape' not in params:
                params.append('escape')

        if command == 'INPUT' and len(params) == 2:
            (priority, question) = params
            input_widgets = self.find_widgets([question])

            if len(input_widgets) > 0:
                if self.automatic:
                    if self.db.fget(question, 'seen') == 'true':
                        self.reply(30, 'question skipped', log=True)
                        self.next_go_backup = False
                        return True
                self.debug('filter', 'widget found for', question)
                if not input_widgets[0].run(priority, question):
                    self.debug('filter', 'widget requested backup')
                    self.next_go_backup = True
                else:
                    self.next_go_backup = False
                self.reply(0, 'question will be asked', log=True)
                return True
            elif 'ERROR' in self.widgets:
                # If it's an error template, fall back to generic error
                # handling.
                try:
                    if self.question_type(question) == 'error':
                        widget = self.widgets['ERROR']
                        self.debug('filter', 'error widget found for',
                                   question)
                        if not widget.error(priority, question):
                            self.debug('filter', 'widget requested backup')
                            self.next_go_backup = True
                        else:
                            self.next_go_backup = False
                        self.reply(0, 'question will be asked', log=True)
                        return True
                except debconf.DebconfError:
                    pass

        if command == 'SET' and len(params) >= 2:
            question = params[0]
            value = ' '.join(params[1:])
            for widget in self.find_widgets([question], 'set'):
                self.debug('filter', 'widget found for', question)
                widget.set(question, value)

        if command == 'SUBST' and len(params) >= 3:
            (question, key) = params[0:2]
            value = ' '.join(params[2:])
            for widget in self.find_widgets([question], 'subst'):
                self.debug('filter', 'widget found for', question)
                widget.subst(question, key, value)

        if command == 'METAGET' and len(params) == 2:
            (question, field) = params
            for widget in self.find_widgets([question], 'metaget'):
                self.debug('filter', 'widget found for', question)
                widget.metaget(question, field)

        if command == 'PROGRESS' and len(params) >= 1:
            subcommand = params[0].upper()
            cancelled = False
            if subcommand == 'START' and len(params) == 4:
                progress_min = int(params[1])
                progress_max = int(params[2])
                progress_title = params[3]
                for widget in self.find_widgets(
                        [progress_title, 'PROGRESS'], 'progress_start'):
                    self.debug('filter', 'widget found for', progress_title)
                    widget.progress_start(progress_min, progress_max,
                                          progress_title)
                self.progress_bars.insert(0, progress_title)
            elif len(self.progress_bars) != 0:
                if subcommand == 'SET' and len(params) == 2:
                    progress_val = int(params[1])
                    for widget in self.find_widgets(
                            [self.progress_bars[0], 'PROGRESS'],
                            'progress_set'):
                        self.debug('filter', 'widget found for',
                                   self.progress_bars[0])
                        if not widget.progress_set(self.progress_bars[0],
                                                   progress_val):
                            cancelled = True
                elif subcommand == 'STEP' and len(params) == 2:
                    progress_inc = int(params[1])
                    for widget in self.find_widgets(
                            [self.progress_bars[0], 'PROGRESS'],
                            'progress_step'):
                        self.debug('filter', 'widget found for',
                                   self.progress_bars[0])
                        if not widget.progress_step(self.progress_bars[0],
                                                    progress_inc):
                            cancelled = True
                elif subcommand == 'INFO' and len(params) == 2:
                    progress_info = params[1]
                    for widget in self.find_widgets(
                            [self.progress_bars[0], 'PROGRESS'],
                            'progress_info'):
                        self.debug('filter', 'widget found for',
                                   self.progress_bars[0])
                        if not widget.progress_info(self.progress_bars[0],
                                                    progress_info):
                            cancelled = True
                elif subcommand == 'STOP' and len(params) == 1:
                    for widget in self.find_widgets(
                            [self.progress_bars[0], 'PROGRESS'],
                            'progress_stop'):
                        self.debug('filter', 'widget found for',
                                   self.progress_bars[0])
                        widget.progress_stop()
                    self.progress_bars.pop()
                elif subcommand == 'REGION' and len(params) == 3:
                    progress_region_start = int(params[1])
                    progress_region_end = int(params[2])
                    for widget in self.find_widgets(
                            [self.progress_bars[0], 'PROGRESS'],
                            'progress_region'):
                        self.debug('filter', 'widget found for',
                                   self.progress_bars[0])
                        widget.progress_region(self.progress_bars[0],
                                               progress_region_start,
                                               progress_region_end)
            # We handle all progress bars ourselves; don't pass them through
            # to the debconf frontend.
            if self.progress_cancel and cancelled:
                self.reply(30, 'progress bar cancelled', log=True)
            else:
                self.reply(0, 'OK', log=True)
            return True

        if command == 'GO' and self.next_go_backup:
            self.reply(30, 'backup', log=True)
            return True

        if command == 'PURGE':
            # PURGE probably corresponds to a package being removed, but
            # since we don't know which package that is at this level,
            # passing it through will purge our own templates rather than
            # the package's.
            self.reply(0, log=True)
            return True

        if command == 'STOP':
            return True

        if command == 'X_LOADTEMPLATEFILE' and len(params) >= 1:
            # The template file we've been asked to load might actually be
            # in the /target chroot rather than in the root filesystem. If
            # so, rewrite the command.
            if params[0].startswith('/'):
                target_template = os.path.join('/target', params[0][1:])
                if os.path.exists(target_template):
                    params[0] = target_template

        try:
            if not self.escaping:
                params = [misc.debconf_escape(param) for param in params]
            data = self.db.command(command, *params)
            self.reply(0, data)

            # Visible elements reset the backup state. If we just reset the
            # backup state on GO, then invisible elements would not be
            # properly skipped over in multi-stage backups.
            if command == 'INPUT':
                self.next_go_backup = False
        except debconf.DebconfError as e:
            self.reply(*e.args)

        return True

    def wait(self):
        if self.subin is not None and self.subout is not None:
            self.subin.close()
            self.subin = None
            self.subout.close()
            self.subout = None
            return self.subp.wait()

    def run(self, command):
        self.start(command)
        while self.process_line():
            pass
        return self.wait()
