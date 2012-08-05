. /lib/partman/lib/base.sh
. /lib/partman/lib/commit.sh
. /lib/partman/lib/recipes.sh

# Sets $virtual; used by other functions here.
check_virtual () {
	open_dialog VIRTUAL $oldid
	read_line virtual
	close_dialog
}

get_real_device () {
	local backupdev num
	# A weird way to get the real device path. The partition numbers
	# in parted_server may be changed and the partition table is still
	# not commited to the disk.
	backupdev=/var/lib/partman/backup/${dev#/var/lib/partman/devices/}
	if [ -f $backupdev/$oldid/view ] && [ -f $backupdev/device ]; then
		num=$(sed 's/^[^0-9]*\([0-9]*\)[^0-9].*/\1/' $backupdev/$oldid/view)
		bdev=$(cat $backupdev/device)
		case $bdev in
		    */disc)
			bdev=${bdev%/disc}/part$num
			;;
		    /dev/[hsv]d[a-z]|/dev/xvd[a-z])
			bdev=$bdev$num
			;;
		    /dev/cciss/c[0-9]d[0-9]|/dev/cciss/c[0-9]d[0-9][0-9]|/dev/ida/c[0-9]d[0-9]|/dev/ida/c[0-9]d[0-9][0-9]|/dev/mmcblk[0-9])
			bdev=${bdev}p$num
			;;
		    *)
			log "get_real_device: strange device name $bdev"
			return
			;;
		esac
		if [ ! -b $bdev ]; then
			bdev=
		fi
	fi
}

do_ntfsresize () {
	local RET
	ntfsresize="$(ntfsresize $@ 2>&1)"
	RET=$?
	echo "$ntfsresize" | grep -v "percent completed" | \
		logger -t ntfsresize
	return $RET
}

get_ntfs_resize_range () {
	local bdev size
	open_dialog GET_VIRTUAL_RESIZE_RANGE $oldid
	read_line minsize cursize maxsize
	close_dialog
	prefsize=$cursize
	get_real_device
	if [ "$bdev" ]; then
		if ! do_ntfsresize -f -i $bdev; then
			logger -t partman "Error running 'ntfsresize --info'"
			return 1
		fi
		size=$(echo "$ntfsresize" | \
			grep '^You might resize at' | \
			sed 's/^You might resize at \([0-9]*\) bytes.*/\1/' | \
			grep '^[0-9]*$')
		if [ "$size" ]; then
			if ! longint_le "$size" "$cursize"; then
				logger -t partman "ntfsresize reported minimum size $size, but current partition size is $cursize"
				unset minsize cursize maxsize prefsize
				return 1
			elif ! longint_le "$minsize" "$size"; then
				logger -t partman "ntfsresize reported minimum size $size, but minimum partition size is $minsize"
				unset minsize cursize maxsize prefsize
				return 1
			else
				minsize=$size
			fi
		fi
	fi
}

get_ext2_resize_range () {
	local bdev tune2fs block_size block_count free_blocks real_minsize
	open_dialog GET_VIRTUAL_RESIZE_RANGE $oldid
	read_line minsize cursize maxsize
	close_dialog
	prefsize=$cursize
	get_real_device
	if [ "$bdev" ]; then
		if ! tune2fs="$(tune2fs -l $bdev)"; then
			logger -t partman "Error running 'tune2fs -l $bdev'"
			return 1
		fi
		block_size="$(echo "$tune2fs" | grep '^Block size:' | \
			head -n1 | sed 's/.*:[[:space:]]*//')"
		block_count="$(echo "$tune2fs" | grep '^Block count:' | \
			head -n1 | sed 's/.*:[[:space:]]*//')"
		free_blocks="$(echo "$tune2fs" | grep '^Free blocks:' | \
			head -n1 | sed 's/.*:[[:space:]]*//')"
		if expr "$block_size" : '[0-9][0-9]*$' >/dev/null && \
		   expr "$block_count" : '[0-9][0-9]*$' >/dev/null && \
		   expr "$free_blocks" : '[0-9][0-9]*$' >/dev/null; then
			real_minsize="$(expr \( "$block_count" - "$free_blocks" \) \* "$block_size")"
			if ! longint_le "$real_minsize" "$cursize"; then
				logger -t partman "tune2fs reported minimum size $real_minsize, but current partition size is $cursize"
				unset minsize cursize maxsize prefsize
				return 1
			elif ! longint_le "$minsize" "$real_minsize"; then
				logger -t partman "tune2fs reported minimum size $real_minsize, but minimum partition size is $minsize"
				unset minsize cursize maxsize prefsize
				return 1
			else
				minsize="$real_minsize"
			fi
		fi
	fi
	return 0
}

get_resize_range () {
	open_dialog GET_RESIZE_RANGE $oldid
	read_line minsize cursize maxsize
	close_dialog
	prefsize=$cursize
}

# This function works only on non-virtual (i.e. committed) filesystems.  It
# calls some external programs to discover the size, so caches for
# efficiency.
get_real_resize_range () {
	# Keep this variable name in sync with other functions above.
	local oldid="$1"
	local fs="$2"

	if [ -f "$oldid/real_resize_range_cache" ]; then
		read minsize cursize maxsize prefsize \
			< "$oldid/real_resize_range_cache"
	else
		local CODE=0
		case $fs in
		    ntfs)		get_ntfs_resize_range || CODE=$? ;;
		    ext2|ext3|ext4)	get_ext2_resize_range || CODE=$? ;;
		    *)			get_resize_range ;;
		esac
		case $CODE in
		    0)
			echo "$minsize $cursize $maxsize $prefsize" \
				> "$oldid/real_resize_range_cache"
			;;
		esac
		return $CODE
	fi
}

human_resize_range () {
	hminsize=$(longint2human $minsize)
	hcursize=$(longint2human $cursize)
	hmaxsize=$(longint2human $maxsize)
	minpercent="$(expr 100 \* "$minsize" / "$maxsize")"
}

decode_swap_size () {
	if [ "$4" = linux-swap ]; then
		echo "$1"
	fi
}

find_swap_size_val=
find_swap_size () {
	if [ -z "$find_swap_size_val" ]; then
		decode_recipe $(get_recipedir)/[0-9][0-9]atomic linux-swap
		find_swap_size_val=$(foreach_partition 'decode_swap_size $*')
	fi
	echo "$find_swap_size_val"
}

ask_for_size () {
	local noninteractive digits minmb minsize_rounded maxsize_rounded

	# Get the original size of the partition being resized.
	open_dialog PARTITION_INFO $oldid
	read_line x1 x2 origsize x4 x5 path x7
	close_dialog

	noninteractive=true
	swap_size="$(find_swap_size)"
	minsize_rounded="$(human2longint "$hminsize")"
	maxsize_rounded="$(human2longint "$hmaxsize")"
	while true; do
		newsize=''
		while [ ! "$newsize" ]; do
			db_set partman-partitioning/new_size "$hcursize"
			db_subst partman-partitioning/new_size MINSIZE "$hminsize"
			db_subst partman-partitioning/new_size MAXSIZE "$hmaxsize"
			db_subst partman-partitioning/new_size PERCENT "$minpercent%"
			# Used by ubiquity to set accurate bounds on resize widgets.
			db_subst partman-partitioning/new_size RAWMINSIZE "$minsize"
			db_subst partman-partitioning/new_size RAWPREFSIZE "$prefsize"
			db_subst partman-partitioning/new_size RAWMAXSIZE "$maxsize"
			db_subst partman-partitioning/new_size PATH "$path"
			db_subst partman-partitioning/new_size SWAPSIZE "$swap_size"
			db_input critical partman-partitioning/new_size || $noninteractive
			noninteractive="return 1"
			db_go || return 1
			db_get partman-partitioning/new_size
			case "$RET" in
			    max)
				newsize=$maxsize
				;;
			    *%)
				digits=$(expr "$RET" : '\([1-9][0-9]*\) *%$')
				if [ "$digits" ]; then
					maxmb=$(convert_to_megabytes $maxsize)
					newsize=$(($digits * $maxmb / 100))000000
				fi
				;;
			    *)
				if valid_human "$RET"; then
					newsize=$(human2longint "$RET")
				fi
				;;
			esac
			if [ -z "$newsize" ]; then
				db_input high partman-partitioning/bad_new_size || true
				db_go || true
			elif ! longint_le "$newsize" "$maxsize"; then
				if longint_le "$newsize" "$maxsize_rounded"; then
					newsize="$maxsize"
				else
					db_input high partman-partitioning/big_new_size || true
					db_go || true
					newsize=''
				fi
			elif ! longint_le "$minsize" "$newsize"; then
				if longint_le "$minsize_rounded" "$newsize"; then
					newsize="$minsize"
				else
					db_input high partman-partitioning/small_new_size || true
					db_go || true
					newsize=''
				fi
			fi
		done

		if perform_resizing; then break; fi
	done
	return 0
}

perform_resizing () {
	if [ "$virtual" = no ]; then
		commit_changes partman-partitioning/new_size_commit_failed || exit 100
		update_partition "$dev" "$oldid" || true
	fi

	disable_swap "$dev"

	if [ "$virtual" = no ] && \
	   [ -f $oldid/detected_filesystem ] && \
	   [ "$(cat $oldid/detected_filesystem)" = ntfs ]; then

		# Resize NTFS
		db_progress START 0 1000 partman/text/please_wait
		db_progress INFO partman-partitioning/progress_resizing
		if longint_le "$cursize" "$newsize"; then
			open_dialog VIRTUAL_RESIZE_PARTITION $oldid $newsize
			read_line newid
			close_dialog
			open_dialog COMMIT
			close_dialog
			open_dialog PARTITION_INFO $newid
			read_line x1 x2 x3 x4 x5 path x7
			close_dialog
			# Wait for the device file to be created again
			update-dev --settle

			if ! echo y | do_ntfsresize -f $path; then
				logger -t partman "Error resizing the NTFS file system to the partition size"
				db_input high partman-partitioning/new_size_commit_failed || true
				db_go || true
				db_progress STOP
				exit 100
			fi
		else
			open_dialog COMMIT
			close_dialog
			open_dialog PARTITION_INFO $oldid
			read_line x1 x2 x3 x4 x5 path x7
			close_dialog
			# Wait for the device file to be created
			update-dev --settle

			if echo y | do_ntfsresize -f --size "$newsize" $path; then
				open_dialog VIRTUAL_RESIZE_PARTITION $oldid $newsize
				read_line newid
				close_dialog
				# Wait for the device file to be created
				update-dev --settle

				if ! echo y | do_ntfsresize -f $path; then
					logger -t partman "Error resizing the NTFS file system to the partition size"
					db_input high partman-partitioning/new_size_commit_failed || true
					db_go || true
					db_progress STOP
					exit 100
				fi
			else
				logger -t partman "Error resizing the NTFS file system"
				db_input high partman-partitioning/new_size_commit_failed || true
				db_go || true
				db_progress STOP
				exit 100
			fi
		fi
		db_progress SET 1000
		db_progress STOP

	elif [ "$virtual" = no ] && \
	     [ -f $oldid/detected_filesystem ] && \
	     ([ "$(cat $oldid/detected_filesystem)" = ext2 ] || \
	      [ "$(cat $oldid/detected_filesystem)" = ext3 ] || \
	      [ "$(cat $oldid/detected_filesystem)" = ext4 ]); then

		# Resize ext2/ext3/ext4; parted can handle simple cases but can't deal
		# with certain common features such as resize_inode
		fs="$(cat $oldid/detected_filesystem)"
		db_progress START 0 1000 partman/text/please_wait
		open_dialog PARTITION_INFO $oldid
		read_line num x2 x3 x4 x5 x6 x7
		close_dialog

		db_metaget "partman/filesystem_short/$fs" description || RET=
		[ "$RET" ] || RET="$fs"
		db_subst partman-basicfilesystems/progress_checking TYPE "$RET"
		db_subst partman-basicfilesystems/progress_checking PARTITION "$num"
		db_subst partman-basicfilesystems/progress_checking DEVICE "$(humandev $(cat device))"
		db_progress INFO partman-basicfilesystems/progress_checking

		if longint_le "$cursize" "$newsize"; then
			open_dialog VIRTUAL_RESIZE_PARTITION $oldid $newsize
			read_line newid
			close_dialog
			open_dialog COMMIT
			close_dialog
			open_dialog PARTITION_INFO $newid
			read_line x1 x2 x3 x4 x5 path x7
			close_dialog
		else
			open_dialog COMMIT
			close_dialog
			open_dialog PARTITION_INFO $oldid
			read_line x1 x2 x3 x4 x5 path x7
			close_dialog
		fi
		# Wait for the device file to be created
		update-dev --settle

		e2fsck_code=0
		e2fsck -f -p $path || e2fsck_code=$?
		if [ $e2fsck_code -gt 1 ]; then
			db_subst partman-basicfilesystems/check_failed TYPE "$fs"
			db_subst partman-basicfilesystems/check_failed PARTITION "$num"
			db_subst partman-basicfilesystems/check_failed DEVICE "$(humandev $(cat device))"
			db_set partman-basicfilesystems/check_failed true
			db_input critical partman-basicfilesystems/check_failed || true
			db_go || true
			db_get partman-basicfilesystems/check_failed
			if [ "$RET" = true ]; then
				exit 100
			fi
		fi

		db_progress INFO partman-partitioning/progress_resizing
		db_progress SET 500
		if longint_le "$cursize" "$newsize"; then
			if ! resize2fs $path; then
				logger -t partman "Error resizing the ext2/ext3/ext4 file system to the partition size"
				db_input high partman-partitioning/new_size_commit_failed || true
				db_go || true
				db_progress STOP
				exit 100
			fi
		else
			if resize2fs $path "$(expr "$newsize" / 1024)K"; then
				open_dialog VIRTUAL_RESIZE_PARTITION $oldid $newsize
				read_line newid
				close_dialog
				# Wait for the device file to be created
				update-dev --settle

				if ! resize2fs $path; then
					logger -t partman "Error resizing the ext2/ext3/ext4 file system to the partition size"
					db_input high partman-partitioning/new_size_commit_failed || true
					db_go || true
					db_progress STOP
					exit 100
				fi
			else
				logger -t partman "Error resizing the ext2/ext3/ext4 file system"
				db_input high partman-partitioning/new_size_commit_failed || true
				db_go || true
				db_progress STOP
				exit 100
			fi
		fi
		db_progress SET 1000
		db_progress STOP

	else

		# Resize virtual partitions, ext2, ext3, ext4, swap, fat16, fat32
		# and probably reiserfs
		name_progress_bar partman-partitioning/progress_resizing
		open_dialog RESIZE_PARTITION $oldid $newsize
		read_line newid
		close_dialog

	fi

	if [ "$newid" ] && [ "$newid" != "$oldid" ]; then
		rm -rf $newid
		mkdir $newid
		cp -r $oldid/* $newid/
	fi
	if [ "$virtual" = no ]; then
		device_cleanup_partitions

		for s in /lib/partman/init.d/*; do
			if [ -x $s ]; then
				$s || exit 100
			fi
		done
	else
		partitions=''
		open_dialog PARTITIONS
		while { read_line num part size type fs path name; [ "$part" ]; }; do
			partitions="$partitions $part"
		done
		close_dialog
		for part in $partitions; do
			update_partition $dev $part
		done
	fi
}
