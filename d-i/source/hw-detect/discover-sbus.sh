#! /bin/sh
set -e

# Detect hardware from output of prtconf utility to support devices on a Sparc
# sbus. Should be removed once the kernel has sysfs support for these devices.
#
# If the hardware is of use within d-i, then echo it.
# We should probably also call register-module or schedule drivers for addition
# in initramfs initrd generators, but that will be taken care of later.

# If discover is present, then prefer discover for sbus hardware detection.
if type discover >/dev/null 2>&1 ; then
	exit 0
fi

if ! type prtconf >/dev/null 2>&1 ; then
	exit 0
fi

SBUSLIST=/usr/share/hw-detect/sbus.list

PRTCONF=$(prtconf)

grep "^[^#].*:.*:.*" $SBUSLIST | while read DEVLINE; do
	DEVID=$(echo $DEVLINE | cut -d: -f1)
	DEVDESCR=$(echo $DEVLINE | cut -d: -f2)
	DEVMOD=$(echo $DEVLINE | cut -d: -f3)
	TARGET=$(echo $DEVLINE | cut -d: -f4)

	if echo "$PRTCONF" | grep -q "^ *$DEVID "; then
		echo "$DEVMOD:$DEVDESCR"
		if [ "$TARGET" = initrd ]; then
			register-module -i $DEVMOD
		else
			register-module $DEVMOD
		fi
	fi
done
