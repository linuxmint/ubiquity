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
import unittest
import traceback
import logging

from autopilot.testcase import AutopilotTestCase
from testtools.testcase import MismatchError
from testtools.matchers import (
    Not,
    Equals,
    Annotate,
    Is,
    IsInstance
    )
from testtools.content import text_content

from ubiquity_autopilot_tests.tools import compare
from ubiquity_autopilot_tests.exception import (
    NonFatalErrors,
    FatalError
    )


logger = logging.getLogger(__name__)


class UbiquityTestCase(AutopilotTestCase):

    def setUp(self):
        super(UbiquityTestCase, self).setUp()
        self.non_fatal_errors = []
        self.fatal_errors = []

    def tearDown(self):
        emulator_errors = compare.non_fatal_errors
        if len(emulator_errors) > 0:
            for error in emulator_errors:
                self.non_fatal_errors.append(error)
        self.assertNonFatalErrors()
        self.assertFatalErrors()
        super(UbiquityTestCase, self).tearDown()
        unittest.TestCase.tearDown(self)

    def _compare_system_with_app_snapshot(self):
        pass  # Disable app snapshot support

    def assertFatalErrors(self, ):
        logger.debug('Checking for fatal errors')
        error_list = self.fatal_errors
        if len(error_list) > 0:
            num = 1
            for error in error_list:
                output = """
=======================================================================
!!! FATAL ERROR !!! found during install......
_______________________________________________________________________
%s
_______________________________________________________________________
""" % error
                self.addDetail("FATAL ERROR {0}: ".format(num),
                               text_content(output))
                num += 1
            raise FatalError("{0} fatal error found during install"
                             .format(len(error_list)))
        return

    def assertNonFatalErrors(self, ):
        logger.debug('Checking for non fatal errors')
        error_list = self.non_fatal_errors
        if len(error_list) > 0:
            num = 1
            for error in error_list:
                output = """
=======================================================================
Non-Fatal Errors found during install......
_______________________________________________________________________
%s
_______________________________________________________________________
""" % error
                self.addDetail("Non-Fatal error {0}: ".format(num),
                               text_content(output))
                num += 1
            raise NonFatalErrors("{0} non fatal errors found during install"
                                 .format(len(error_list)))
        return

    def expectEqual(self, expected, observed, message=''):
        """Assert that 'expected' is equal to 'observed'.

        :param expected: The expected value.
        :param observed: The observed value.
        :param message: An optional message to include in the error.
        """
        matcher = Equals(expected)
        try:
            self._expectThat(observed, matcher, message)
        except MismatchError:
            logger.error("Expected %r to equal %r but it didn't" %
                         expected, observed, exc_info=True)
            stck = traceback.format_exc(limit=5)
            self.non_fatal_errors.append(stck)

    def expectIsNotNone(self, observed, message=''):
        """Assert that 'observed' is not equal to None.

        :param observed: The observed value.
        :param message: An optional message describing the error.
        """
        matcher = Not(Is(None))
        try:
            self._expectThat(observed, matcher, message)
        except MismatchError:
            stck = traceback.format_exc(limit=5)
            self.non_fatal_errors.append(stck)

    def expectIsInstance(self, obj, klass, msg=None):
        if isinstance(klass, tuple):
            matcher = IsInstance(*klass)
        else:
            matcher = IsInstance(klass)
        try:
            self._expectThat(obj, matcher, msg)
        except MismatchError:
            logger.error("Expected %r to be instance of %r but it wasn't" %
                         obj, klass, exc_info=True)
            stck = traceback.format_exc(limit=5)
            self.non_fatal_errors.append(stck)

    def expectThat(self, matchee, matcher, message='', verbose=False):
        try:
            self._expectThat(matchee, matcher, message, verbose)
        except MismatchError:
            logger.error("MisMatch found", exc_info=True)
            stck = traceback.format_exc(limit=5)
            self.non_fatal_errors.append(stck)

    def expectNotVisible(self, matchee, message='', verbose=False):
        matcher = Equals(False)
        try:
            self._expectThat(matchee, matcher, message, verbose)
        except MismatchError:
            logger.error("MisMatch found", exc_info=True)
            stck = traceback.format_exc(limit=5)
            self.fatal_errors.append(stck)

    def _expectThat(self, matchee, matcher, message='', verbose=False):

        matcher = Annotate.if_message(message, matcher)
        mismatch = matcher.match(matchee)
        if not mismatch:
            return
        existing_details = self.getDetails()
        for (name, content) in mismatch.get_details().items():
            full_name = name
            suffix = 1
            while full_name in existing_details:
                full_name = "%s-%d" % (name, suffix)
                suffix += 1
                self.addDetail(full_name, content)

        raise MismatchError(matchee, matcher, mismatch, verbose)
