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

"""
For custom install, it would be ideal to try all different partition layouts.

I think the best route would be to select a random configuration for each test
run rather than a seperate test for each configuration.
So lets create some crazy layouts, we have 12GB disk size to play with and the
install still needs to be able to complete.

Our options are:

        'PartitionSize': int,  # an int value of size in MB If set to None,
                                 we use up all remaining space

        # These are the current available mount points
        'MountPoint': /, /boot, /home,
                      /tmp, /usr, /var,
                      /srv, /opt, /usr/local

        'FileSystemType': 'Ext2','Ext3', 'Ext4', 'ReiserFs',
                          'btrfs', 'JFS', 'XFS', 'Fat16', 'Fat32' and 'Swap'

        'PartitionType': 'Primary' or 'Logical'

        'Position': 'Beginning' or 'End

"""

"""
 Swap = 1024MB
/ = Ext4 - Take up half available space
"""
Config1 = [
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Primary',
        'Position': 'End'
    },
    {
        'PartitionSize': None,
        'MountPoint': '/',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    }
]
"""Config 2
    / = Ext4 - Take up half available space - swap

    /home = Ext4 - Take up all remaining space

    Swap = 1024MB
"""
Config2 = [
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Primary',
        'Position': 'End'
    },
    {
        'PartitionSize': 5120,
        'MountPoint': '/',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': None,
        'MountPoint': '/home',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    }
]
"""Config 3
    /boot = Ext2 - 200MB

    / = Ext4 - 5GB

    /home = Ext4 -take up remaining space

    Swap = 1024MB
"""
Config3 = [
    {
        'PartitionSize': 200,
        'MountPoint': '/boot',
        'FileSystemType': 'Ext2',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 5120,
        'MountPoint': '/',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Logical',
        'Position': 'End'
    },
    {
        'PartitionSize': None,
        'MountPoint': '/home',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    }
]
""" Config 4
    /boot = 200MB - Ext2

    / = 5GB - Ext4

    /tmp = 200MB Ext4

    /home = Ext4 take up available space

    /opt = 500MB Ext3

    Swap = 1024MB
"""
Config4 = [
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Logical',
        'Position': 'End'
    },
    {
        'PartitionSize': 200,
        'MountPoint': '/boot',
        'FileSystemType': 'Ext2',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 5120,
        'MountPoint': '/',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 200,
        'MountPoint': '/tmp',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 500,
        'MountPoint': '/opt',
        'FileSystemType': 'Ext3',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    },
    {

        'PartitionSize': None,
        'MountPoint': '/home',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Primary',
        'Position': 'Beginning'

    }
]
"""Config 5


    / = Ext4 5 GB

    /home = btrfs - Take up available space

    swap = 1024MB
"""
Config5 = [
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Logical',
        'Position': 'End'
    },
    {
        'PartitionSize': 200,
        'MountPoint': '/boot',
        'FileSystemType': 'Ext2',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 5120,
        'MountPoint': '/',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': None,
        'MountPoint': '/home',
        'FileSystemType': 'btrfs',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    }
]
"""Config 6
    /boot = 200MB - Ext2

    / = XFS 5 GB

    /home = JFS - Take up available space

    swap = 1024MB
"""
Config6 = [
    {
        'PartitionSize': 200,
        'MountPoint': '/boot',
        'FileSystemType': 'Ext2',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Logical',
        'Position': 'End'
    },
    {
        'PartitionSize': 5120,
        'MountPoint': '/',
        'FileSystemType': 'XFS',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': None,
        'MountPoint': '/home',
        'FileSystemType': 'JFS',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    }
]

"""edubuntuConfig
    / = Ext4 - Has to be larger than 5.8GB

    /home = Ext4 - Take up all remaining space

    Swap = 1024MB
"""
edubuntuConfig = [
    {
        'PartitionSize': 1024,
        'MountPoint': None,
        'FileSystemType': 'Swap',
        'PartitionType': 'Primary',
        'Position': 'End'
    },
    {
        'PartitionSize': 7000,
        'MountPoint': '/',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Logical',
        'Position': 'Beginning'
    },
    {
        'PartitionSize': None,
        'MountPoint': '/home',
        'FileSystemType': 'Ext4',
        'PartitionType': 'Primary',
        'Position': 'Beginning'
    }
]
