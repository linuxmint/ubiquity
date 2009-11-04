# apport hook for ubiquity; adds various log files

import os.path

def add_installation_log(report, ident, name):
    if os.path.exists('/var/log/installer/%s' % name):
        report[ident] = ('/var/log/installer/%s' % name,)
    elif os.path.exists('/var/log/%s' % name):
        report[ident] = ('/var/log/%s' % name,)

def add_info(report):
    add_installation_log(report, 'UbiquitySyslog', 'syslog')
    add_installation_log(report, 'UbiquityPartman', 'partman')
    if os.path.exists('/var/log/installer/debug'):
        report['UbiquityDebug'] = ('/var/log/installer/debug',)
    if os.path.exists('/var/log/installer/dm'):
        report['UbiquityDm'] = ('/var/log/installer/dm',)
    add_installation_log(report, 'Casper', 'casper.log')
    if os.path.exists('/var/log/oem-config.log'):
        report['OemConfigLog'] = ('/var/log/oem-config.log',)
