#! /bin/sh -e
[ -f /target/boot/grub/grub.cfg ] && ( grep -q /boot/efi /target/etc/fstab )

