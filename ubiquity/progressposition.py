# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2006, 2007 Canonical Ltd.
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


class ProgressPosition(object):
    """Tracks the position of a logical progress bar.

    A progress bar is created with start and end points, defining its
    length. The position of the bar may be set or stepped (incremented)
    directly; or else a region of the bar may be marked and a sub-bar
    created to occupy that region, which then has its own independent start
    and end points that are mapped onto the region of the parent bar. This
    class keeps track of progress bars nested in this way, and calculates
    the overall position in the top-level bar.
    """

    def __init__(self):
        # list of [start, end, region_start, region_end, title]
        # TODO cjwatson 2006-02-25: not the neatest data structure in the
        # world ...
        self.positions = []
        self.inner_position = 0.0

    def start(self, start, end, title):
        self.positions.insert(0, [start, end, start, end, title])

    def stop(self):
        self.positions.pop(0)

    def set_region(self, region_start, region_end):
        self.positions[0][2] = region_start
        self.positions[0][3] = region_end

    def get_region(self):
        """Returns the current region in the innermost progress bar.

        This method returns the current region as a (start, end) tuple.
        """
        return (self.positions[0][2], self.positions[0][3])

    def set(self, value):
        self.inner_position = float(value)

    def step(self, increment):
        self.inner_position += increment

    def depth(self):
        return len(self.positions)

    def fraction(self):
        if not self.positions:
            # progress bar not started
            return 0.0
        if self.positions[0][0] == self.positions[0][1]:
            # Somebody screwed up when creating this bar. Deal.
            return 0.0
        fraction = ((self.inner_position - self.positions[0][0]) /
                    (self.positions[0][1] - self.positions[0][0]))
        for bar in range(1, len(self.positions)):
            position = (self.positions[bar][2] +
                        fraction * (self.positions[bar][3] -
                                    self.positions[bar][2]))
            fraction = ((position - self.positions[bar][0]) /
                        (self.positions[bar][1] - self.positions[bar][0]))
        return fraction

    def title(self):
        if not self.positions:
            # progress bar not started
            return ''
        return self.positions[0][4]
