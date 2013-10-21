import os

from autopilot.testcase import AutopilotTestCase
from autopilot.introspection import get_proxy_object_for_existing_process
from testtools.matchers import Equals
from autopilot.input import Mouse, Pointer

class WelcomeTests(AutopilotTestCase):

    def setUp(self):
        super(WelcomeTests, self).setUp()
        self.app = self.launch_application()
        #properties = self.app.get_properties()
        #print(properties)
        #self._find('Install Now')

        self.pointing_device = Pointer(Mouse.create())

    def launch_application(self):
        my_process = int(os.environ['UBIQUITY_PID'])
        my_dbus = str(os.environ['DBUS_SESSION_BUS_ADDRESS'])
        return get_proxy_object_for_existing_process(
            pid=my_process, dbus_bus=my_dbus)

    def test_window_title(self):
        '''
        Check that title is "Install"
        '''

        main_window = self.app.select_single(
            'GtkWindow', name='live_installer')
        self.assertThat(main_window.title, Equals("Install"))
