# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006 Canonical Ltd.
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

# Simple bindings to allow Python programs to talk to parted_server.
# I don't recommend attempting to use these outside Ubiquity.

from __future__ import print_function

import fcntl
import os
import shutil


devices = '/var/lib/partman/devices'
infifo = '/var/lib/partman/infifo'
outfifo = '/var/lib/partman/outfifo'
stopfifo = '/var/lib/partman/stopfifo'
logfile = '/var/log/partman'


class PartedServerError(Exception):
    """Raised when parted_server throws an exception.

    Attributes:
        exctype -- exception type
        parted_error -- message returned with exception
        options -- list of options for the user to select (e.g. OK, Cancel)

    """

    def __init__(self, exctype, parted_error, options):
        Exception.__init__(self, exctype, parted_error, options)
        self.exctype = exctype
        self.parted_error = parted_error
        self.options = list(options)


class PartedServer(object):
    def __init__(self):
        self.inf = None
        self.outf = None
        self.current_disk = None

    def __del__(self):
        if self.inf is not None or self.outf is not None:
            self.close_dialog()

    def log(self, *args):
        with open(logfile, 'a') as f:
            print('ubiquity:', ' '.join(args), file=f)

    def write_line(self, *args):
        self.log('IN:', *args)
        self.inf.write(' '.join(args) + '\n')
        self.inf.flush()

    def read_line(self, count=0):
        line = self.outf.readline().rstrip('\n')
        # Make sure returned list is always exactly as long as requested, or
        # 1 in the default count=0 case (i.e. the whole line).
        if count == 0:
            ret = ['']
        else:
            ret = [''] * count
            count -= 1
        pieces = line.split(None, count)
        ret[0:len(pieces)] = pieces
        return ret

    def read_paragraph(self):
        paragraph = ''
        while True:
            line = self.read_line()[0]
            if line == '':
                break
            self.log('paragraph: %s' % line)
            paragraph += line
            paragraph += '\n'
        return paragraph

    def read_list(self):
        ret = []
        while True:
            item = self.read_line()[0]
            if item == '':
                break
            self.log('option: %s' % item)
            ret.append(item)
        return ret

    # Do the minimum required to satisfy the parted_server protocol, and
    # raise a Python exception if parted_server throws anything at least as
    # serious as an exception of type Error.
    def error_handler(self):
        while True:
            exception_type = self.read_line()[0]
            if exception_type == 'OK':
                break
            self.log('error_handler: exception with type %s' % exception_type)
            if exception_type == 'Timer':
                while True:
                    (frac, state) = self.read_line(2)
                    if frac == 'ready':
                        break
            else:
                self.log('error_handler: reading message')
                message = self.read_paragraph()
                self.log('error_handler: reading options')
                options = self.read_list()
                if exception_type in ('Information', 'Warning'):
                    pass
                else:
                    raise PartedServerError(exception_type, message, options)

    def sync_server(self):
        with open(stopfifo, 'w'):
            pass

    def open_dialog(self, command, *args):
        self.inf = open(infifo, 'w')
        fcntl.fcntl(self.inf.fileno(), fcntl.F_SETFD, fcntl.FD_CLOEXEC)
        self.write_line(command, self.current_disk, *args)
        self.outf = open(outfifo, 'r')
        fcntl.fcntl(self.outf.fileno(), fcntl.F_SETFD, fcntl.FD_CLOEXEC)
        self.error_handler()

    def close_dialog(self):
        if self.outf is not None:
            self.outf.close()
        if self.inf is not None:
            self.inf.close()
        self.sync_server()
        with open(outfifo, 'w'):
            pass
        self.sync_server()
        self.inf = open(infifo, 'r')
        self.inf.readlines()
        self.inf.close()
        self.sync_server()
        self.outf = None
        self.inf = None

    # Get all disk identifiers (subdirectories of /var/lib/partman/devices).
    def disks(self):
        return sorted(os.listdir(devices))

    # This is stateful in a slightly ugly way, but it corresponds well to
    # the shell interface.
    def select_disk(self, disk):
        self.current_disk = disk

    def device_entry(self, name):
        return os.path.join(devices, self.current_disk, name)

    def readline_device_entry(self, name):
        with open(self.device_entry(name)) as entryfile:
            return entryfile.readline().rstrip('\n')

    def part_entry(self, partition, name):
        return os.path.join(devices, self.current_disk, partition, name)

    def has_part_entry(self, partition, name):
        return os.path.isfile(self.part_entry(partition, name))

    def readline_part_entry(self, partition, name):
        with open(self.part_entry(partition, name)) as entryfile:
            return entryfile.readline().rstrip('\n')

    def write_part_entry(self, partition, name, text):
        with open(self.part_entry(partition, name), 'w') as entryfile:
            entryfile.write(text)

    def remove_part_entry(self, partition, name):
        entry = self.part_entry(partition, name)
        try:
            if os.path.isdir(entry):
                shutil.rmtree(entry)
            else:
                os.unlink(entry)
        except OSError:
            pass

    def mkdir_part_entry(self, partition, name):
        entry = self.part_entry(partition, name)
        if not os.path.isdir(entry):
            os.mkdir(entry)

    def partitions(self):
        partitions = []
        self.open_dialog('PARTITIONS')
        try:
            while True:
                (p_num, p_id, p_size, p_type,
                 p_fs, p_path, p_name) = self.read_line(7)
                if p_id == '':
                    break
                partitions.append((p_num, p_id, p_size, p_type,
                                   p_fs, p_path, p_name))
        finally:
            self.close_dialog()
        return partitions

    def partition_info(self, partition):
        self.open_dialog('PARTITION_INFO', partition)
        try:
            (p_num, p_id, p_size, p_type,
             p_fs, p_path, p_name) = self.read_line(7)
        finally:
            self.close_dialog()
        if p_id == '':
            return ()
        return (p_num, p_id, p_size, p_type, p_fs, p_path, p_name)
