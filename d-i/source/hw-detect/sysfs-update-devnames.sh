#! /bin/sh -e
# Make sure that /etc/network/devnames is up to date, using sysfs. In
# hotplug land, we may not get a chance to update it otherwise.

if [ ! -d /sys/class/net ] || ! type lspci >/dev/null 2>&1; then
	exit
fi

for dev in $(grep : /proc/net/dev | sort | cut -d: -f1); do
	if grep "^$dev:" /etc/network/devnames >/dev/null 2>&1; then
		continue
	fi
	if [ -f "/sys/class/net/$dev/device/vendor" ] && \
	   [ -f "/sys/class/net/$dev/device/device" ]; then
		vendor="$(sed 's/^0x//' "/sys/class/net/$dev/device/vendor")"
		device="$(sed 's/^0x//' "/sys/class/net/$dev/device/device")"
		# 'tail -n 1' because for some reason lspci outputs two
		# Device: lines.
		vendorname="$(lspci -d "$vendor:$device" -m -v | grep ^Vendor: | tail -n 1 | sed 's/^Vendor:[[:space:]]*//; s/,/\\,/g')"
		devicename="$(lspci -d "$vendor:$device" -m -v | grep ^Device: | tail -n 1 | sed 's/^Device:[[:space:]]*//; s/,/\\,/g')"
		if [ "$vendorname" ] || [ "$devicename" ]; then
			echo "$dev:$vendorname $devicename" >> /etc/network/devnames
		fi
	elif [ "$(readlink -f /sys/class/net/$dev/device/bus)" = /sys/bus/ieee1394 ] || \
	     [ "$(readlink -f /sys/class/net/$dev/device/bus)" = /sys/bus/firewire ]; then
		echo "$dev:FireWire (IEEE 1394) Ethernet device" >> /etc/network/devnames
	fi
done
