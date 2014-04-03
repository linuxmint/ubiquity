# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2013
#
# Author: Daniel Chapman daniel@chapman-mail.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


class InRange(object):

    def __init__(self, start, end):
        self.range_start = start
        self.range_end = end

    def __str__(self):
        return 'InRange(%r, %r)' % (
            self.range_start, self.range_end)

    def match(self, actual):
        if actual in range(self.range_start, self.range_end):
            return None
        else:
            return InRangeMismatch(
                actual, self.range_start, self.range_end)


class InRangeMismatch(object):

    def __init__(self, actual, start, end):
        self.actual = actual
        self.range_start = start
        self.range_end = end

    def describe(self):
        return "%r is not in range %r - %r" % (
            self.actual, self.range_start, self.range_end)

    def get_details(self):
        return {}
