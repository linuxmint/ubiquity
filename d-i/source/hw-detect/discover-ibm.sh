#! /bin/sh
set -e

# Detect hardware from Open Firmware's exported device tree that are
# related to IBM pseries/js20 blades/rs6k machines.
#
# If the hardware is of use within d-i, then echo it and register-module it;
# otherwise, just use register-module.

for dir in $(find "/proc/device-tree/" -type d); do
	name="$(cat "$dir/name" 2>/dev/null || true)"
	device_type="$(cat "$dir/device_type" 2>/dev/null || true)"
	compatible="$(cat "$dir/compatible" 2>/dev/null || true)"

	# drivers/pseries
	if [ "$name" = l-lan ]; then
		echo "ibmveth:IBM Virtual Ethernet"
		register-module ibmveth
	fi
	# drivers/scsi
	if [ "$name" = v-scsi ]; then
		echo "ibmvscsic:IBM Virtual SCSI"
		register-module ibmvscsic
	fi
done
