#!/bin/sh
set -x
set -e
#git subtree add --prefix=d-i/source/apt-setup https://git.launchpad.net/~ubuntu-installer/apt-setup '1%0.157ubuntu2'
#git subtree add --prefix=d-i/source/base-installer https://git.launchpad.net/~ubuntu-installer/base-installer 1.158ubuntu7
#git subtree add --prefix=d-i/source/bterm-unifont https://git.launchpad.net/bterm-unifont 1.6
#git subtree add --prefix=d-i/source/choose-mirror https://git.launchpad.net/~ubuntu-installer/choose-mirror 2.78ubuntu7
#git subtree add --prefix=d-i/source/clock-setup https://git.launchpad.net/~ubuntu-installer/clock-setup 0.131ubuntu1
git subtree add --prefix=d-i/source/console-setup https://git.launchpad.net/ubuntu/+source/console-setup ubuntu/devel
git subtree add --prefix=d-i/source/debian-installer-utils https://git.launchpad.net/~ubuntu-installer/debian-installer-utils 1.124ubuntu1
git subtree add --prefix=d-i/source/grub-installer https://git.launchpad.net/~ubuntu-installer/grub-installer 1.128ubuntu14
git subtree add --prefix=d-i/source/hw-detect https://git.launchpad.net/~ubuntu-installer/hw-detect 1.117ubuntu7
git subtree add --prefix=d-i/source/localechooser https://git.launchpad.net/ubuntu/+source/localechooser ubuntu/devel
git subtree add --prefix=d-i/source/netcfg https://git.launchpad.net/~ubuntu-installer/netcfg 1.142ubuntu8
git subtree add --prefix=d-i/source/partconf https://git.launchpad.net/~ubuntu-installer/partconf 1.50ubuntu1
git subtree add --prefix=d-i/source/partman-auto https://git.launchpad.net/~ubuntu-installer/partman-auto 134ubuntu13
git subtree add --prefix=d-i/source/partman-auto-crypto https://git.launchpad.net/~ubuntu-installer/partman-auto-crypto 25ubuntu1
git subtree add --prefix=d-i/source/partman-auto-loop https://git.launchpad.net/~ubuntu-installer/partman-auto-loop 0ubuntu21
git subtree add --prefix=d-i/source/partman-auto-lvm https://git.launchpad.net/~ubuntu-installer/partman-auto-lvm 59ubuntu4
git subtree add --prefix=d-i/source/partman-base https://git.launchpad.net/~ubuntu-installer/partman-base 206ubuntu6
git subtree add --prefix=d-i/source/partman-basicfilesystems https://git.launchpad.net/~ubuntu-installer/partman-basicfilesystems 127ubuntu2
git subtree add --prefix=d-i/source/partman-basicmethods https://git.launchpad.net/~ubuntu-installer/partman-basicmethods 70
git subtree add --prefix=d-i/source/partman-btrfs https://git.launchpad.net/~ubuntu-installer/partman-btrfs 29ubuntu1
git subtree add --prefix=d-i/source/partman-crypto https://git.launchpad.net/~ubuntu-installer/partman-crypto 101ubuntu4
git subtree add --prefix=d-i/source/partman-efi https://git.launchpad.net/~ubuntu-installer/partman-efi 84ubuntu1
git subtree add --prefix=d-i/source/partman-ext3 https://git.launchpad.net/~ubuntu-installer/partman-ext3  86ubuntu1
git subtree add --prefix=d-i/source/partman-jfs https://git.launchpad.net/~ubuntu-installer/partman-jfs 58
git subtree add --prefix=d-i/source/partman-lvm https://git.launchpad.net/partman-lvm 133
git subtree add --prefix=d-i/source/partman-partitioning https://git.launchpad.net/~ubuntu-installer/partman-partitioning 120ubuntu3
git subtree add --prefix=d-i/source/partman-swapfile https://git.launchpad.net/partman-swapfile 2
git subtree add --prefix=d-i/source/partman-target https://git.launchpad.net/~ubuntu-installer/partman-target 98ubuntu1
git subtree add --prefix=d-i/source/partman-xfs https://git.launchpad.net/~ubuntu-installer/partman-xfs 66
git subtree add --prefix=d-i/source/preseed https://git.launchpad.net/~ubuntu-installer/preseed 1.71ubuntu11
git subtree add --prefix=d-i/source/tzsetup https://git.launchpad.net/~ubuntu-installer/tzsetup '1%0.94ubuntu2'
git subtree add --prefix=d-i/source/user-setup https://git.launchpad.net/ubuntu/+source/user-setup ubuntu/devel
