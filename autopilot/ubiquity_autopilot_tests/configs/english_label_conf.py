# Config file for english label values
# Author: Dan Chapman <daniel@chapman-mail.com>
# Copyright (C) 2013
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
import configparser


def get_distribution():
    """Returns the name of the running distribution."""
    with open('/cdrom/.disk/info') as f:
        for line in f:
            distro = line[:max(line.find(' '), 0) or None]
            if distro:
                if distro == 'Ubuntu-GNOME':
                    return str(distro.replace('-', ' '))
                else:
                    return str(distro)
            raise SystemError("Could not get distro name")


def generate_config():
    distro_flavor = get_distribution()
    config = configparser.ConfigParser()

    #CREATE STEP LANGUAGE CONFIG
    config['stepLanguage'] = {}
    stepLanguage = config['stepLanguage']
    stepLanguage['release_notes_label'] = \
        'You may wish to read the <a href="release-notes">release notes</a>.'
    stepLanguage["page_title"] = \
        '<span size="xx-large">Welcome</span>'

    # CREATE STEP PREPARE CONFIG
    config['stepPrepare'] = {}
    stepPrepare = config['stepPrepare']
    stepPrepare['page_title'] = \
        '<span size="xx-large">Preparing to install {0}</span>'\
        .format(distro_flavor)
    stepPrepare['prepare_best_results'] = \
        'For best results, please ensure that this computer:'
    stepPrepare['prepare_foss_disclaimer'] = \
        '{0} uses third-party software to play ' \
        'Flash, MP3 and other media, and to work with some graphics ' \
        'and wi-fi hardware. Some of this software is proprietary. ' \
        'The software is subject to license terms included with its ' \
        'documentation.'.format(distro_flavor)
    stepPrepare['prepare_download_updates'] = \
        'Download updates while installing'
    stepPrepare['prepare_nonfree_software'] = \
        'Install this third-party software'
    stepPrepare['prepare_network_connection'] = \
        'is connected to the Internet'
    stepPrepare['prepare_sufficient_space'] = \
        'has at least 6.0 GB available drive space'

    #CREATE STEP PART ASK CONFIG
    config['stepPartAsk'] = {}
    stepPartAsk = config['stepPartAsk']
    stepPartAsk['page_title'] = \
        '<span size="xx-large">Installation type</span>'
    stepPartAsk['use_device'] = \
        'Erase disk and install {0}'.format(distro_flavor)
    stepPartAsk['use_device_desc'] = \
        '<span size="small"><span foreground="darkred">Warning:</span> ' \
        'This will delete any files on the disk.</span>'
    stepPartAsk['use_crypto'] = \
        'Encrypt the new {0} installation for security'.format(distro_flavor)
    stepPartAsk['use_crypto_desc'] = \
        '<span size="small">You will choose a security key in the ' \
        'next step.</span>'
    stepPartAsk['use_lvm'] = 'Use LVM with the new {0} installation'.format(
        distro_flavor
    )
    stepPartAsk['use_lvm_desc'] = \
        '<span size="small">This will set up Logical Volume ' \
        'Management. It allows taking snapshots and easier partition ' \
        'resizing.</span>'
    stepPartAsk['custom_partitioning'] = 'Something else'
    stepPartAsk['custom_partitioning_desc'] = \
        '<span size="small">You can create or resize partitions yourself, ' \
        'or choose multiple partitions for {0}.</span>'.format(distro_flavor)

    #CREATE STEP PART CRYPTO CONFIG
    config['stepPartCrypto'] = {}
    stepPartCrypto = config['stepPartCrypto']
    stepPartCrypto["page_title"] = \
        '<span size="xx-large">Choose a security key:</span>'
    stepPartCrypto["verified_crypto_label"] = 'Confirm the security key:'
    stepPartCrypto["crypto_label"] = 'Choose a security key:'
    stepPartCrypto["crypto_description"] = \
        'Disk encryption protects your files in case you lose your computer.' \
        ' It requires you to enter a security key each time the computer ' \
        'starts up.'
    stepPartCrypto["crypto_warning"] = \
        '<span foreground="darkred">Warning:</span> If you lose ' \
        'this security key, all data will be lost. If you need to, ' \
        'write down your key and keep it in a safe place elsewhere.'
    stepPartCrypto["crypto_extra_label"] = 'For more security:'
    stepPartCrypto["crypto_extra_time"] = \
        'The installation may take much longer.'
    stepPartCrypto["crypto_description_2"] = \
        'Any files outside of {0} will not be encrypted.'.format(distro_flavor)
    stepPartCrypto["crypto_overwrite_space"] = 'Overwrite empty disk space'

    #CREATE STEP LOCATION CONFIG
    config['stepLocation'] = {}
    stepLocation = config['stepLocation']
    stepLocation["page_title"] = '<span size="xx-large">Where are you?</span>'

    #CREATE STEP KEYBOARD CONFIG
    config['stepKeyboardConf'] = {}
    stepKeyboardConf = config['stepKeyboardConf']
    stepKeyboardConf["page_title"] = \
        '<span size="xx-large">Keyboard layout</span>'

    #CREATE STEP USER INFO CONFIG
    config['stepUserInfo'] = {}
    stepUserInfo = config['stepUserInfo']
    stepUserInfo["page_title"] = '<span size="xx-large">Who are you?</span>'
    stepUserInfo["hostname_label"] = "Your computer's name:"
    stepUserInfo["username_label"] = 'Pick a username:'
    stepUserInfo["password_label"] = 'Choose a password:'
    stepUserInfo["verified_password_label"] = 'Confirm your password:'
    stepUserInfo["hostname_extra_label"] = \
        'The name it uses when it talks to other computers.'
    stepUserInfo["login_encrypt"] = 'Require my password to log in'

    #write config to tmp file
    with open('/tmp/english_config.ini', 'w') as configfile:
        config.write(configfile)
