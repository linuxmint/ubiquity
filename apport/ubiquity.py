# apport hook for ubiquity; adds various log files

import os.path

def add_info(report):
    if os.path.exists('/var/log/syslog'):
        report['UbiquitySyslog'] = ('/var/log/syslog',)
    if os.path.exists('/var/log/partman'):
        report['UbiquityPartman'] = ('/var/log/partman',)
    if os.path.exists('/var/log/installer/debug'):
        report['UbiquityDebug'] = ('/var/log/installer/debug',)
    if os.path.exists('/var/log/installer/dm'):
        report['UbiquityDm'] = ('/var/log/installer/dm',)
    if os.path.exists('/var/log/casper.log'):
        report['Casper'] = ('/var/log/casper.log',)
