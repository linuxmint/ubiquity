'''apport package hook for shim and shim-signed

(c) 2015 Canonical Ltd.
Author: Brian Murray <brian@ubuntu.com>
'''

import errno
import os
import re

from apport.hookutils import (
    command_available,
    command_output,
    recent_syslog,
    attach_file,
    attach_root_command_outputs)

efiarch = {'amd64': 'x64',
           'i386': 'ia32',
           'arm64': 'aa64'
          }
grubarch = {'amd64': 'x86_64',
            'i386': 'i386',
            'arm64': 'arm64'
           }

def add_info(report, ui):
    efiboot = '/boot/efi/EFI/ubuntu'
    if command_available('efibootmgr'):
        report['EFIBootMgr'] = command_output(['efibootmgr', '-v'])
    else:
        report['EFIBootMgr'] = 'efibootmgr not available'
    commands = {}
    try:
        directory = os.stat(efiboot)
    except OSError as e:
        if e.errno == errno.ENOENT:
            report['Missing'] = '/boot/efi/EFI/ubuntu directory is missing'
            return
        if e.errno == errno.EACCES:
            directory= True
    if directory:
        arch = report['Architecture']
        commands['BootEFIContents'] = 'ls %s' % efiboot
        commands['ShimDiff'] = 'diff %s/shim%s.efi /usr/lib/shim/shim%s.efi.signed' % (efiboot, efiarch[arch], efiarch[arch])
        commands['GrubDiff'] = 'diff %s/grub%s.efi /usr/lib/grub/%s-efi-signed/grub%s.efi.signed' %(efiboot, efiarch[arch], grubarch[arch], efiarch[arch])

    efivars_dir = '/sys/firmware/efi/efivars'
    sb_var = os.path.join(efivars_dir,
                          'SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c')
    mok_var = os.path.join(efivars_dir,
                           'MokSBStateRT-605dab50-e046-4300-abb6-3dd810dd8b23')

    attach_file(report, '/proc/sys/kernel/moksbstate_disabled')
    commands['SecureBoot'] = 'od -An -t u1 %s' % sb_var
    commands['MokSBStateRT'] = 'od -An -t u1 %s' % mok_var
    attach_root_command_outputs(report, commands)
    report['EFITables'] = recent_syslog(re.compile(r'(efi|esrt):|Secure boot'))
