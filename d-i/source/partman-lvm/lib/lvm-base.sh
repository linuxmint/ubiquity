. /lib/partman/lib/base.sh

# Avoid warnings from lvm2 tools about open file descriptors
# Setting this here should avoid them for partman as a whole
export LVM_SUPPRESS_FD_WARNINGS=1

###############################################################################
#
# Miscellaneous utility functions
#
###############################################################################

# Convert common terms for disk sizes into something LVM understands.
#  e.g. "200 gb" -> "47683"
lvm_extents_from_human() {
	local vg size extent_size
	vg="$1"
	size="$2"

	extent_size=$(vgs --noheadings --units K -o vg_extent_size "$vg")
	echo $(($(human2longint "$size") / $(human2longint "$extent_size")))
}

# Convert LVM disk sizes into something human readable.
#  e.g. "812.15M" -> "812MB"
lvm_size_to_human() {
	echo "${1}B" | sed -e 's/\...//'
}

# Convenience wrapper for lvs/pvs/vgs
lvm_get_info() {
	local type info device output
	type=$1
	info=$2
	device=$3

	output=$($type --noheadings --nosuffix --separator ":" --units M \
		-o "$info" $device 2> /dev/null)
	if [ $? -ne 0 ]; then
		return 1
	fi
	# NOTE: The last sed, s/:$// is necessary due to a bug in lvs which adds a
	#       trailing separator even if there is only one field
	output=$(echo "$output" | sed -e 's/^[:[:space:]]\+//g;s/[:[:space:]]\+$//g')
	# Be careful here, we don't want to output only a newline
	if [ -n "$output" ]; then
		echo "$output"
	fi
	return 0
}

# Converts a list of space (or newline) separated values to comma separated values
ssv_to_csv() {
	local csv value

	csv=""
	for value in $1; do
		if [ -z "$csv" ]; then
			csv="$value"
		else
			csv="$csv, $value"
		fi
	done
	echo "$csv"
}

# Converts a list of comma separated values to space separated values
csv_to_ssv() {
	echo "$1" | sed -e 's/ *, */ /g'
}

# Produces a human readable description of the current LVM config
lvm_get_config() {
	local output pv pvs vg vgs lv lvs line

	# Unallocated PVs
	db_metaget partman-lvm/text/configuration_freepvs description
	output="$RET
"
	pvs=$(pv_list_free)
	if [ -z "$pvs" ]; then
		db_metaget partman-lvm/text/configuration_none_pvs description
		output="$output  * $RET
"
	else
		for pv in $(pv_list_free); do
			pv_get_info "$pv"
			line=$(printf "%-56s (%sMB)" "  * $pv" "$SIZE")
			output="${output}${line}
"
		done
	fi

	# Volume groups
	db_metaget partman-lvm/text/configuration_vgs description
	output="$output
$RET
"
	vgs=$(vg_list)
	if [ -z "$vgs" ]; then
		db_metaget partman-lvm/text/configuration_none_vgs description
		RET="$output  * $RET
"
		return 0
	fi

	for vg in $vgs; do
		# VG name
		vg_get_info "$vg"
		line=$(printf "%-56s (%sMB)" "  * $vg" "$SIZE")
		output="${output}${line}
"

		# PVs used by VG
		# This will return > 0 results, otherwise we'd have no VG
		pvs=$(vg_list_pvs "$vg")
		db_metaget partman-lvm/text/configuration_pv description
		for pv in $pvs; do
			pv_get_info "$pv"
			line=$(printf "%-35s %-20s (%sMB)" "    - $RET" "$pv" "$SIZE")
			output="${output}${line}
"
		done

		# LVs provided by VG
		lvs=$(vg_list_lvs "$vg")
		if [ -z "$lvs" ]; then
			continue
		fi
		db_metaget partman-lvm/text/configuration_lv description
		for lv in $lvs; do
			lv_get_info "$vg" "$lv"
			line=$(printf "%-35s %-20s (%sMB)" "    - $RET" "$lv" "$SIZE")
			output="${output}${line}
"
		done
	done
	RET="$output"
	return 0
}

# Common checks for VG and LV names
# Rules:
# 1) At least one character
# 2) Only alphanumeric characters (isalnum()) and "._-+"
# 3) May not be "." or ".."
# 4) must not start with a hyphen
# 5) maximum name length 128 characters
# See lvm2 source and bug #254630 for details
lvm_name_ok() {
	local name
	name="$1"

	# Rule 1
	if [ -z "$name" ]; then
		return 1
	fi

	# Rule 2
	if [ "$(echo -n "$name" | sed 's/[^-+_\.[:alnum:]]//g')" != "$name" ]; then
		return 1
	fi

	# Rule 3
	if [ "$name" = "." -o "$name" = ".." ]; then
		return 1
	fi

	# Rule 4
	if [ "$(echo -n "$name" | sed 's/^-//')" != "$name" ]; then
		return 1
	fi

	# Rule 5
	if [ $(echo -n "$name" | wc -c) -gt 128 ]; then
		return 1
	fi

	return 0
}

# Would a PV be allowed on this partition?
pv_allowed () {
	local dev=$1
	local id=$2

	cd $dev

	local lvm=no
	if grep -q "/dev/md" $dev/device; then
		# LVM on software RAID
		lvm=yes
	elif grep -q "/dev/mapper/" $dev/device; then
		# LVM on device-mapper crypto
		if type dmsetup >/dev/null 2>&1; then
			device=$(cat $dev/device)
			if [ "$(dmsetup status $device | cut -d' ' -f3)" = crypt ]; then
				lvm=yes
			fi
		fi
	fi

	# sparc can not have LVM starting at 0 or it will destroy the partition table
	if [ "$(udpkg --print-architecture)" = sparc ] && \
	   [ "${id%%-*}" = 0 ] && [ $lvm = no ]; then
		return 1
	fi

	if [ $lvm = no ]; then
		local fs
		open_dialog PARTITION_INFO $id
		read_line x1 x2 x3 x4 fs x6 x7
		close_dialog
		if [ "$fs" = free ]; then
			# parted can't deal with VALID_FLAGS on free space
			# as yet, so unfortunately we have to special-case
			# label types.
			local label
			open_dialog GET_LABEL_TYPE
			read_line label
			close_dialog
			case $label in
			    amiga|bsd|dasd|gpt|mac|msdos|sun)
				# ... by creating a partition
				lvm=yes
				;;
			esac
		else
			local flag
			open_dialog VALID_FLAGS $id
			while { read_line flag; [ "$flag" ]; }; do
				if [ "$flag" = lvm ]; then
					lvm=yes
				fi
			done
			close_dialog
		fi
	fi

	[ $lvm = yes ]
}

pv_list_allowed () {
	partman_list_allowed pv_allowed
}

pv_list_allowed_free () {
	local line

	IFS="$NL"
	for line in $(pv_list_allowed); do
		restore_ifs
		local dev="${line%%$TAB*}"
		local rest="${line#*$TAB}"
		local id="${rest%%$TAB*}"
		if [ -e "$dev/locked" ] || [ -e "$dev/$id/locked" ]; then
			continue
		fi
		local pv="${line##*$TAB}"
		if [ ! -e "$pv" ]; then
			echo "$line"
		else
			local vg=$(lvm_get_info pvs vg_name "$pv" || true)
			if [ -z "$vg" ]; then
				echo "$line"
			fi
		fi
		IFS="$NL"
	done
	restore_ifs
}

###############################################################################
#
# Physical Volume utility functions
#
###############################################################################

# Check if a device contains PVs
# If called for a disk, this will also check all partitions;
# if called for anything other, it can return false positives!
pv_on_device() {
	local device
	device="$1"

	if $(pvs --noheadings --nosuffix -o pv_name | grep -q "$device"); then
		return 0
	fi
	return 1
}

# Get info on a PV
pv_get_info() {
	local info

	info=$(lvm_get_info pvs pv_size,pv_pe_count,pv_free,pv_pe_alloc_count,vg_name "$1")
	if [ $? -ne 0 ]; then
		return 1
	fi

	SIZE=$(echo "$info"   | cut -d':' -f1 | cut -d'.' -f1)
	SIZEPE=$(echo "$info" | cut -d':' -f2)
	FREE=$(echo "$info"   | cut -d':' -f3 | cut -d'.' -f1)
	FREEPE=$(echo "$info" | cut -d':' -f4) # Used, not free, PEs
	FREEPE=$(( $SIZEPE - $FREEPE ))        # Calculate free PEs
	VG=$(echo "$info"     | cut -d':' -f5)
	return 0
}

# Get VG for a PV
pv_get_vg() {
	lvm_get_info pvs vg_name "$1"
}

# Get all PVs
pv_list() {
	# Scan the partman devices and find partitions that have lvm as method.
	# Do not rely on partition flags since it doesn't work for some partitions
	# (e.g. dm-crypt, RAID)
	local dev method

	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			[ -f $id/method ] || continue
			method=$(cat $id/method)
			if [ "$method" = lvm ]; then
				echo $(mapdevfs $path)
			fi
		done
		close_dialog
	done
}

# Get all unused PVs
pv_list_free() {
	local pv vg

	for pv in $(pv_list); do
		vg=$(lvm_get_info pvs vg_name "$pv")
		if [ -z "$vg" ]; then
			echo "$pv"
		fi
	done
}

# Prepare a partition for use as a PV. If this returns true, then it did
# some work and a commit is necessary. Prints the new path.
pv_prepare() {
	local dev="$1"
	local id="$2"
	local size parttype fs path

	cd "$dev"
	open_dialog PARTITION_INFO "$id"
	read_line x1 id size freetype fs path x7
	close_dialog

	if [ "$fs" = free ]; then
		local newtype

		case $freetype in
		    primary)
			newtype=primary
			;;
		    logical)
			newtype=logical
			;;
		    pri/log)
			local parttype
			open_dialog PARTITIONS
			while { read_line x1 x2 x3 parttype x5 x6 x7; [ "$parttype" ]; }; do
				if [ "$parttype" = primary ]; then
					has_primary=yes
				fi
			done
			close_dialog
			if [ "$has_primary" = yes ]; then
				newtype=logical
			else
				newtype=primary
			fi
			;;
		esac

		open_dialog NEW_PARTITION $newtype ext2 $id full $size
		read_line x1 id x3 x4 x5 path x7
		close_dialog
	fi

	mkdir -p "$id"
	local method="$(cat "$id/method" 2>/dev/null || true)"
	if [ "$method" = swap ]; then
		disable_swap "$dev" "$id"
	fi
	if [ "$method" != lvm ]; then
		echo lvm >"$id/method"
		rm -f "$id/use_filesystem"
		rm -f "$id/format"
		update_partition "$dev" "$id"
		echo "$path"
		return 0
	fi

	echo "$path"
	return 1
}

# Initialize a PV
pv_create() {
	local pv
	pv="$1"

	if pvs "$pv" > /dev/null 2>&1; then
		return 0
	fi

	log-output -t partman-lvm pvcreate -ff -y "$pv"
	return $?
}

# Remove the LVM signatures from a PV
pv_delete() {
	local pv
	pv="$1"

	if ! pvs "$pv" > /dev/null 2>&1; then
		return 0
	fi

	log-output -t partman-lvm pvremove -ff -y "$pv"
	return $?
}

###############################################################################
#
# Logical Volume utility functions
#
###############################################################################

# Get LV info
lv_get_info() {
	local info vg lv line tmplv
	vg=$1
	lv=$2
	info=$(lvm_get_info lvs lv_name,lv_size "$vg")

	SIZE=""
	FS="unknown"
	MOUNT="unknown"
	for line in $(lvm_get_info lvs lv_name,lv_size "$vg"); do
		tmplv=$(echo "$line" | cut -d':' -f1)
		if [ $tmplv != $lv ]; then
			continue
		fi

		SIZE=$(echo "$line" | cut -d':' -f2 | cut -d'.' -f1)
		MOUNT=$(grep "^/dev/mapper/$vg-$lv" /proc/mounts | cut -d' ' -f2 | sed -e 's/\/target//')
		# FIXME: Get FS - but we should not use parted for that!
		#FS=$(parted "$tmplv" print | grep '^1' | \
		#	sed -e 's/ \+/ /g' | cut -d " " -f 4)
		break
	done
}

# List all LVs and their VGs
lv_list() {
	lvm_get_info lvs lv_name,vg_name ""
}

# Create a LV
lv_create() {
	local vg lv extents
	vg="$1"
	lv="$2"
	extents="$3"

	log-output -t partman-lvm lvcreate -l "$extents" -n "$lv" $vg
	return $?
}

# Delete a LV
lv_delete() {
	local vg lv device
	vg="$1"
	lv="$2"
	device="/dev/$vg/$lv"

	swapoff $device > /dev/null 2>&1
	umount $device > /dev/null 2>&1

	# swapoff or umount may have fiddled with metadata on the block
	# device, so we may need to wait for udev to finish rescanning it.
	update-dev --settle

	log-output -t partman-lvm lvremove -f "$device"
	return $?
}

# Checks that a logical volume name is ok
# Rules:
# 1) The common rules (see lvm_name_ok)
# 2) must not start with "snapshot"
# See lvm2 source and bug #254630 for details
lv_name_ok() {
	local lvname
	lvname="$1"

	# Rule 1
	lvm_name_ok "$lvname" || return 1

	# Rule 2
	if [ "${lvname#snapshot}" != "$lvname" ]; then
		return 1
	fi

	return 0
}

###############################################################################
#
# Volume Group utility functions
#
###############################################################################

# Get VG info
vg_get_info() {
	local info

	info=$(lvm_get_info vgs vg_size,vg_extent_count,vg_free,vg_free_count,lv_count,pv_count "$1")
	if [ $? -ne 0 ]; then
		return 1
	fi

	SIZE=$(echo "$info"   | cut -d':' -f1 | cut -d'.' -f1)
	SIZEPE=$(echo "$info" | cut -d':' -f2)
	FREE=$(echo "$info"   | cut -d':' -f3 | cut -d'.' -f1)
	FREEPE=$(echo "$info" | cut -d':' -f4)
	LVS=$(echo "$info"    | cut -d':' -f5)
	PVS=$(echo "$info"    | cut -d':' -f6)
	return 0
}

# List all VGs
vg_list() {
	lvm_get_info vgs vg_name ""
}

# List all VGs with free space
vg_list_free() {
	local vg

	for vg in $(vg_list); do
		vg_get_info "$vg"
		if [ $FREEPE -gt 0 ]; then
			echo "$vg"
		fi
	done
}

# Get all PVs from a VG
vg_list_pvs() {
	local line vg pv

	# vgs doesn't work with pv_name
	for line in $(lvm_get_info pvs vg_name,pv_name ""); do
		vg=$(echo "$line" | cut -d':' -f1)
		pv=$(echo "$line" | cut -d':' -f2)
		if [ "$vg" = "$1" ]; then
			echo "$pv"
		fi
	done
}

# Get all LVs from a VG
vg_list_lvs() {
	lvm_get_info lvs lv_name "$1"
}

# Lock device(s) holding a PV
vg_lock_pvs() {
	local name pv
	name="$1"
	shift

	db_subst partman-lvm/text/in_use VG "$name"
	db_metaget partman-lvm/text/in_use description
	for pv in $*; do
		partman_lock_unit "$pv" "$RET"
	done
}

# Create a volume group
vg_create() {
	local vg pv
	vg="$1"
	shift

	for pv in $*; do
		pv_create "$pv" || return 1
	done
	log-output -t partman-lvm vgcreate "$vg" $* || return 1
	update-dev --settle
	return 0
}

# Delete a volume group
vg_delete() {
	local vg
	vg="$1"

	log-output -t partman-lvm vgchange -a n "$vg" && \
	update-dev --settle && \
	log-output -t partman-lvm vgremove "$vg" && \
	update-dev --settle && \
	return 0

	# reactivate if deleting failed
	log-output -t partman-lvm vgchange -a y "$vg"
	update-dev --settle
	return 1
}

# Extend a volume group (add a PV)
vg_extend() {
	local vg pv
	vg="$1"
	pv="$2"

	pv_create "$pv" || return 1
	log-output -t partman-lvm vgextend "$vg" "$pv" || return 1
	return 0
}

# Reduce a volume group (remove a PV)
vg_reduce() {
	local vg pv
	vg="$1"
	pv="$2"

	log-output -t partman-lvm vgreduce "$vg" "$pv"
	return $?
}

# Checks that a logical volume name is ok
# Rules:
# 1) The common rules (see lvm_name_ok)
# See lvm2 source and bug #254630 for details
vg_name_ok() {
	local vgname
	vgname="$1"

	# Rule 1
	lvm_name_ok "$vgname" || return 1

	return 0
}
