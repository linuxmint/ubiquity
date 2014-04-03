# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#
# Copyright (C) 2013
#
# Author: Daniel Chapman daniel@chapman-mail.com
#
# Inspired and re-worked version of RudyLattae's 'Compare' module
# URL: https://github.com/rudylattae/compare
#
# Implementing using rich comparison matchers
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
import logging
import traceback

non_fatal_errors = []

logger = logging.getLogger(__name__)


class expectThat(object):
    """
    expectThat is a tool for asserting non-fatal errors

    It should only be used as to assert non-fatal errors. Errors which it
    doesn't make sense to halt the test if it fails. At the end of the test you
    need to use the global non_fatal_errors list and test it is empty

        i.e self.assertThat(len(non_fatal_errors), Equals(0))

    If there are errors then in your test pass each error to self.addDetail()
    and finally re-raise the exception so we get a failed test.

    This will result in the formatted exceptions stored in the non_fatal_errors
    list being printed to the test result

    """

    def __init__(self, value):
        self.value = value

    def __getattr__(self, name):
        return getattr(super(expectThat, self), name)

    def __repr__(self,):
        return 'expectThat(%s)' % repr(self.value)

    #now som rich comparisons
    #all we really need is just ==, != and is_unicode and a contains
    def __eq__(self, compareValue, msg=None):
        message = "Expected {0} but instead we got {1}".format(
            repr(compareValue), repr(self.value))
        try:
            assert self.value == compareValue, message
        except AssertionError:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            e = traceback.format_exc(limit=5)
            non_fatal_errors.append(e)

    def __ne__(self, compareValue):
        message = "Expected {0} to not equal {1}, but it does!!!".format(
            repr(self.value), repr(compareValue)
        )
        try:
            assert self.value != compareValue, message
        except AssertionError as e:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            e = traceback.format_exc(limit=5)
            non_fatal_errors.append(e)

    def equals(self, compareValue, msg=None):
        if msg:
            message = msg
        else:
            message = "Expected {0} to equal {1} but it doesn't!!".format(
                repr(compareValue), repr(self.value))
        try:
            assert self.value == compareValue, message
        except AssertionError:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            e = traceback.format_exc(limit=5)
            non_fatal_errors.append(e)

    def not_equals(self, compareValue, msg=None):
        if msg:
            message = msg
        else:
            message = "Expected {0} to not equal {1}, but it does!!!".format(
                repr(self.value), repr(compareValue))

        try:
            assert self.value != compareValue, message
        except AssertionError as e:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            e = traceback.format_exc(limit=5)
            non_fatal_errors.append(e)

    def is_unicode(self, msg=None):
        if msg:
            message = msg
        else:
            message = "Expected to be instance of type 'unicode' but is an "\
                "instance of type '{0}'".format(self.value.__class__.__name__)
        try:
            assert isinstance(self.value, str), message
        except AssertionError as e:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            non_fatal_errors.append(e)

    def contains(self, compareValue, msg=None):
        if msg:
            message = msg
        else:
            message = '{0} does not contain {1}.'.format(
                repr(self.value), repr(compareValue))
        try:
            assert compareValue in self.value, message
        except AssertionError as e:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            non_fatal_errors.append(e)

    def almost_equals(self, compareValue, msg=None):
        if msg:
            message = msg
        else:
            message = 'Expected {0} to almost equal {1}, but it '\
                'doesnt'.format(repr(self.value), repr(compareValue))
        try:
            result = self._approx_equal(self.value, compareValue)
            assert result, message
        except AssertionError as e:
            logger.error("NON_FATAL_ERROR: %s" % message, exc_info=True)
            global non_fatal_errors
            non_fatal_errors.append(e)
