#!/bin/sh

set -e
. /usr/share/debconf/confmodule
if [ -e /lib/partman/lib/iscsi-base.sh ]; then
	. /lib/partman/lib/iscsi-base.sh
fi
#set -x

if [ "$(uname)" != Linux ]; then
	exit 0
fi

# Install mmc modules if no other disks are found
# (ex: embedded device with µSD storage)
# TODO: more checks?
if [ -z "$(list-devices disk)" ]; then
	anna-install mmc-modules || true
fi

log () { 
	logger -t disk-detect "$@"
}

is_not_loaded() {
	! ((cut -d" " -f1 /proc/modules | grep -q "^$1\$") || \
	   (cut -d" " -f1 /proc/modules | sed -e 's/_/-/g' | grep -q "^$1\$"))
}

list_modules_dir() {
	if [ -d "$1" ]; then
		find $1 -type f | sed 's/\.ko$//; s/.*\///'
	fi
}

list_disk_modules() {
	# FIXME: not all of this stuff is disk driver modules, find a way
	# to separate out only the disk stuff.
	list_modules_dir /lib/modules/*/kernel/drivers/ide
	list_modules_dir /lib/modules/*/kernel/drivers/scsi
	list_modules_dir /lib/modules/*/kernel/drivers/block
	list_modules_dir /lib/modules/*/kernel/drivers/message/fusion
	list_modules_dir /lib/modules/*/kernel/drivers/message/i2o
}

disk_found() {
	for try in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
		if search-path parted_devices; then
			# Use partman's parted_devices if available.
			if [ -n "$(parted_devices)" ]; then
				return 0
			fi
		else
			# Essentially the same approach used by partitioner and
			# autopartkit to find their disks.
			if [ -n "$(list-devices disk)" ]; then
				return 0
			fi
		fi

		# Wait for disk to be activated.
		if [ "$try" != 15 ]; then
			sleep 2
		fi
	done

	return 1
}

module_probe() {
	local module="$1"
	local priority="$2"
	local modinfo=""
	local devs=""
	local olddevs=""
	local newdev=""
	
	if ! log-output -t disk-detect modprobe -v "$module"; then
		# Prompt the user for parameters for the module.
		local template="hw-detect/retry_params"
		local question="$template/$module"
		db_unregister "$question"
		db_register "$template" "$question"
		db_subst "$question" MODULE "$module"
		db_input critical "$question" || [ $? -eq 30 ]
		db_go
		db_get "$question"
		local params="$RET"

		if [ -n "$params" ]; then
			if ! log-output -t disk-detect modprobe -v "$module" $params; then
				db_unregister "$question"
				db_subst hw-detect/modprobe_error CMD_LINE_PARAM "modprobe -v $module $params"
				db_input critical hw-detect/modprobe_error || [ $? -eq 30 ]
				db_go
				false
			else
				# Module loaded successfully
				if [ "$params" != "" ]; then
					register-module "$module" "$params"
				fi
			fi
		fi
	fi
}

multipath_probe() {
	MP_VERBOSE=2
	# Look for multipaths...
	if [ ! -f /etc/multipath.conf ]; then
		cat <<EOF >/etc/multipath.conf
defaults {
    user_friendly_names yes
}
EOF
	fi
	log-output -t disk-detect /sbin/multipath -v$MP_VERBOSE

	if multipath -l 2>/dev/null | grep -q '^mpath[0-9]\+ '; then
		return 0
	else
		return 1
	fi
}

if ! hw-detect disk-detect/detect_progress_title; then
	log "hw-detect exited nonzero"
fi

# Compatibility with old iSCSI preseeding
db_get open-iscsi/targets || RET=
if [ "$RET" ]; then
	if ! pidof iscsid >/dev/null; then
		iscsi-start
	fi
	for portal in $RET; do
		iscsi_discovery "$portal" -l
	done
fi

# New-style preseeding
if db_fget partman-iscsi/login/address seen && [ "$RET" = true ] && \
   db_get partman-iscsi/login/address && [ "$RET" ]; then
	if ! pidof iscsid >/dev/null; then
		iscsi-start
	fi
	db_capb backup
	iscsi_login
	db_capb
fi

while ! disk_found; do
	CHOICES_C=""
	CHOICES=""
	if type iscsi_login >/dev/null 2>&1; then
		CHOICES_C="${CHOICES_C:+$CHOICES_C, }iscsi"
		db_metaget disk-detect/iscsi_choice description
		CHOICES="${CHOICES:+$CHOICES, }$RET"
	fi
	for mod in $(list_disk_modules | grep -v iscsi | sort); do
		CHOICES_C="${CHOICES_C:+$CHOICES_C, }$mod"
		CHOICES="${CHOICES:+$CHOICES, }$mod"
	done

	if [ -n "$CHOICES" ]; then
		db_capb backup
		db_subst disk-detect/module_select CHOICES-C "$CHOICES_C"
		db_subst disk-detect/module_select CHOICES "$CHOICES"
		db_input high disk-detect/module_select || [ $? -eq 30 ]
		if ! db_go; then
			exit 10
		fi
		db_capb

		db_get disk-detect/module_select
		if [ "$RET" = continue ]; then
			exit 0
		elif [ "$RET" = iscsi ]; then
			if ! pidof iscsid >/dev/null; then
				iscsi-start
			fi
			db_capb backup
			iscsi_login
			db_capb
			continue
		elif [ "$RET" != none ]; then
			module="$RET"
			if [ -n "$module" ] && is_not_loaded "$module" ; then
				register-module "$module"
				module_probe "$module"
			fi
			continue
		fi
	fi

	if [ -e /usr/lib/debian-installer/retriever/media-retriever ]; then
		db_capb backup
		db_input critical hw-detect/load_media
		if ! db_go; then
			exit 10
		fi
		db_capb
		db_get hw-detect/load_media
		if [ "$RET" = true ] && \
		   anna media-retriever && \
		   hw-detect disk-detect/detect_progress_title; then
			continue
		fi
	fi

	db_capb backup
	db_input high disk-detect/cannot_find
	if ! db_go; then
		exit 10
	fi
	db_capb
done

# Activate support for Serial ATA RAID
if anna-install dmraid-udeb; then
	# Device mapper support is required to run dmraid
	if ! dmsetup version >/dev/null 2>&1; then
		module_probe dm-mod || true
	fi

	if dmraid -c -s >/dev/null 2>&1; then
		logger -t disk-detect "Serial ATA RAID disk(s) detected."
		# Ask the user whether they want to activate dmraid devices.
		db_input high disk-detect/activate_dmraid || true
		db_go
		db_get disk-detect/activate_dmraid
		activate_dmraid=$RET

		if [ "$activate_dmraid" = true ]; then
			mkdir -p /var/lib/disk-detect
			touch /var/lib/disk-detect/activate_dmraid
			logger -t disk-detect "Enabling dmraid support."
			# Activate only those arrays which have all disks
			# present.
			for dev in $(dmraid -r -c); do
				[ -e "$dev" ] || continue
				log-output -t disk-detect dmraid-activate "$(basename "$dev")"
			done
		fi
	else
		logger -t disk-detect "No Serial ATA RAID disks detected"
	fi
fi

# Activate support for DM Multipath
db_get disk-detect/multipath/enable
if [ "$RET" = true ]; then
	if anna-install multipath-udeb; then
		# We need some dm modules...
		depmod -a >/dev/null 2>&1 || true
		if ! dmsetup version >/dev/null 2>&1; then
			module_probe dm-mod || true
		fi
		if ! dmsetup targets | cut -d' ' -f1 | grep -q '^multipath$'; then
			module_probe dm-multipath || true
		fi
		# No way to check whether this is loaded already?
		log-output -t disk-detect modprobe -v dm-round-robin || true

		# Look for multipaths...
		if multipath_probe; then
			logger -t disk-detect "Multipath devices found; enabling multipath support"
			if ! anna-install partman-multipath; then
				/sbin/multipath -F
				logger -t disk-detect "Error loading partman-multipath; multipath devices deactivated"
			fi
		else
			logger -t disk-detect "No multipath devices detected"
		fi
	fi
fi

check-missing-firmware
