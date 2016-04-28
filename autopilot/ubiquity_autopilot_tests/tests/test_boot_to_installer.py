# Testing Desktop Live Session Boot
# Authors: Dan Chapman <daniel@chapman-mail.com>,
#          Nicholas Skaggs <nicholas.skaggs@canonical.com>
# Copyright (C) 2013-2016
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from ubiquity_autopilot_tests.tests import UbiquityAutopilotTestCase
from testtools.matchers import Equals
from autopilot.matchers import Eventually
from ubiquity_autopilot_tests.emulators import gtktoplevel


class BootToInstaller(UbiquityAutopilotTestCase):
    """
    Tests to ensure the image boots to the installer properly
    """

    def test_boot_to_installer(self, ):
        # first check we have an emulator instance
        self.assertIsInstance(self.main_window, gtktoplevel.GtkWindow)
        self.assertThat(self.main_window.visible, Eventually(Equals(True)))
        self.welcome_page_tests(lang='English')
