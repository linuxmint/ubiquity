'''apport package hook for console-setup

Copyright (C) 2009 Canonical Ltd.
Author: Colin Watson <cjwatson@ubuntu.com>
'''

import apport.hookutils

def add_info(report):
    apport.hookutils.attach_file_if_exists(
        report, '/etc/default/keyboard', 'Keyboard')
    apport.hookutils.attach_file_if_exists(
        report, '/etc/default/console-setup', 'ConsoleSetup')
