## Shared code for all guided partitioning components

auto_init_disks() {
	local dev

	# Create new disk label; don't prompt for label
	. /lib/partman/lib/disk-label.sh
	prepare_new_labels "$@" || return 1

	for dev in "$@"; do
		create_new_label "$dev" no || return 1
	done
}

get_last_free_partition_infos() {
	local dev
	dev="$1"

	cd $dev

	free_space=''
	open_dialog PARTITIONS
	while { read_line num id size type fs path name; [ "$id" ]; }; do
		if [ "$fs" = free ]; then
			free_space=$id
			free_size=$size
			free_type=$type
		fi
	done
	close_dialog
}

# Mark a partition as LVM and add it to vgpath
mark_partition_as_lvm() {
	local id
	id=$1
	shift

	open_dialog GET_FLAGS $id
	flags=$(read_paragraph)
	close_dialog
	open_dialog SET_FLAGS $id
	write_line "$flags"
	write_line lvm
	write_line NO_MORE
	close_dialog
}

# Each disk must have at least one primary partition after autopartitioning.
ensure_primary() {
	if echo "$scheme" | grep -q '\$primary{'; then
		# Recipe provides one primary partition
		return
	fi

	cd $dev

	open_dialog USES_EXTENDED
	read_line uses_extended
	close_dialog
	if [ "$uses_extended" = no ]; then
		# No need for this on this partition table type
		return
	fi

	open_dialog PARTITIONS
	local have_primary=
	local id type
	while { read_line x1 id x2 type x3 x4 x5; [ "$id" ]; }; do
		if [ "$type" = primary ]; then
			have_primary=1
		fi
	done
	close_dialog

	if [ "$have_primary" ]; then
		# Existing disk provides one primary partition
		return
	fi

	# Neither disk nor recipe provides a primary partition. Force the
	# first partition in the recipe (arbitrarily chosen) to be primary.
	scheme="$(
		local first=1
		foreach_partition '
			if [ "$first" ]; then
				echo "$* \$primary{ }"
				first=
			else
				echo "$*"
			fi'
	)"
}

reuse_partitions() {
	cd $dev
	local scheme

	scheme="$scheme_reused"
	foreach_partition '
		id="$(echo " $*" | sed -n '\''s/.* \$reuse{ \([^}]*\) }.*/\1/p'\'')"
		if [ -z "$id" ]; then
			db_progress STOP
			autopartitioning_failed
		fi
		setup_partition $id $*
		# Hack to stop EFI partitions showing up as formatted when
		# they will actually not be.  We do not have a good
		# interface for this yet.
		if [ -f $id/method ] && [ "$(cat $id/method)" = efi ] && \
		   [ -f $id/detected_filesystem ]; then
			rm -f $id/format
		fi'
}

create_primary_partitions() {
	cd $dev
	while [ "$free_type" = pri/log ] && \
	      echo $scheme | grep -q '\$primary{'; do
		pull_primary
		set -- $primary
		if [ -z "$scheme_rest" ]; then
			open_dialog NEW_PARTITION primary $4 $free_space full ${1}000001
		else
			open_dialog NEW_PARTITION primary $4 $free_space beginning ${1}000001
		fi
		read_line num id size type fs path name
		close_dialog
		if [ -z "$id" ]; then
			db_progress STOP
			autopartitioning_failed
		fi
		neighbour=$(partition_after $id)
		if [ "$neighbour" ]; then
			open_dialog PARTITION_INFO $neighbour
			read_line x1 new_free_space x2 new_free_type fs x3 x4
			close_dialog
		fi
		if [ -z "$scheme_rest" ]; then
			# If this is the last partition to be created, it does
			# not matter if we have space left for more partitions
			:
		elif [ -z "$neighbour" ] || [ "$fs" != free ] || \
		   [ "$new_free_type" = primary ] || \
		   [ "$new_free_type" = unusable ]; then
			open_dialog DELETE_PARTITION $id
			close_dialog
			open_dialog NEW_PARTITION primary $4 $free_space end ${1}000001
			read_line num id size type fs path name
			close_dialog
			if [ -z "$id" ]; then
				db_progress STOP
				autopartitioning_failed
			fi
			neighbour=$(partition_before $id)
			if [ "$neighbour" ]; then
				open_dialog PARTITION_INFO $neighbour
				read_line x1 new_free_space x2 new_free_type fs x3 x4
				close_dialog
			fi
			if [ -z "$neighbour" ] || [ "$fs" != free ] ||
			   [ "$new_free_type" = unusable ]; then
				open_dialog DELETE_PARTITION $id
				close_dialog
				break
			fi
		fi
		shift; shift; shift; shift
		if echo "$*" | grep -q "method{ lvm }"; then
			pv_devices="$pv_devices $path"
			mark_partition_as_lvm $id $*
		elif echo "$*" | grep -q "method{ crypto }"; then
			pv_devices="$pv_devices /dev/mapper/${path##*/}_crypt"
		fi
		setup_partition $id $*
		primary=''
		scheme="$scheme_rest"
		free_space=$new_free_space
		free_type="$new_free_type"
	done
}

create_partitions() {
    foreach_partition '
	if [ -z "$free_space" ]; then
		db_progress STOP
		autopartitioning_failed
	fi
	open_dialog PARTITION_INFO $free_space
	read_line x1 free_space x2 free_type fs x3 x4
	close_dialog
	if [ "$fs" != free ]; then
		free_type=unusable
	fi

	case "$free_type" in
	    primary|logical)
		type="$free_type"
		;;
	    pri/log)
		type=logical
		;;
	    unusable)
		db_progress STOP
		autopartitioning_failed
		;;
	esac

	if [ "$last" = yes ]; then
		open_dialog NEW_PARTITION $type $4 $free_space full ${1}000001
	else
		open_dialog NEW_PARTITION $type $4 $free_space beginning ${1}000001
	fi
	read_line num id size type fs path name
	close_dialog
	if [ -z "$id" ]; then
		db_progress STOP
		autopartitioning_failed
	fi
	shift; shift; shift; shift
	if echo "$*" | grep -q "method{ lvm }"; then
		pv_devices="$pv_devices $path"
		mark_partition_as_lvm $id $*
	elif echo "$*" | grep -q "method{ crypto }"; then
		pv_devices="$pv_devices /dev/mapper/${path##*/}_crypt"
	fi
	setup_partition $id $*
	free_space=$(partition_after $id)'
}

is_wholedisk_mdraid () {
	local device="`echo $1 | sed -e 's!/\([0-9]*\)$!\1!'`"
	local mddisk=${device#/dev/}
	local ret=0
	local d

	[ -d /sys/block/$mddisk/md ] || return 1

	for d in /sys/block/$mddisk/slaves/*; do
		case "$d" in
			dm-*|md*)
				;;
			*p[0-9]|*p[0-9][0-9])
				ret=1
				break
				;;
		esac
	done

	return $ret
}

get_auto_disks() {
	local dev device dmtype

	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue

		device=$(cat $dev/device)
		
		# Skip devices containing the installation medium
		[ -e "$dev/installation_medium" ] && continue

		# Skip software RAID (mdadm) devices (/dev/md/X and /dev/mdX)
		# unless it's a whole-disk partitionable array
		if echo "$device" | grep -Eq "/dev/md/?[0-9]*$"; then
			if ! is_wholedisk_mdraid "$device"; then
				continue
			fi
		fi

		# Skip installer disk
		$(mount | grep -qF "$device on /cdrom ") && continue

		# Skip device mapper devices (/dev/mapper/),
		# except for dmraid or multipath devices
		if echo $device | grep -q "^/dev/mapper/"; then
			if [ ! -f "$dev/sataraid" ] && \
			   ! is_multipath_dev $device; then
				continue
			fi
		fi
		printf "$dev\t$(device_name $dev)\n"
	done
}

select_auto_disk() {
	local DEVS

	DEVS=$(get_auto_disks)
	[ -n "$DEVS" ] || return 1
	debconf_select critical partman-auto/select_disk "$DEVS" "" || return 1
	echo "$RET"
	return 0
}

# Maps a devfs name to a partman directory
dev_to_partman () {
	local dev_name="$1"

	local mapped_dev_name="$(mapdevfs $dev_name)"
	if [ -n "$mapped_dev_name" ]; then
		dev_name="$mapped_dev_name"
	fi

	for dev in $DEVICES/*; do
		# mapdevfs both to allow for different ways to refer to the
		# same device using devfs, and to allow user input in
		# non-devfs form
		if [ "$(mapdevfs $(cat $dev/device))" = "$dev_name" ]; then
			echo $dev
		fi
	done
}
