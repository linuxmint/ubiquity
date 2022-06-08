# Calling scripts should also source base.sh if create_new_label is called

default_disk_label () {
	if type archdetect >/dev/null 2>&1; then
		archdetect=$(archdetect)
	else
		archdetect=unknown/generic
	fi
	arch=${archdetect%/*}
	sub=${archdetect#*/}
	case "$arch" in
	    alpha)
		# Load srm_env.o if we can; this should fail on ARC-based systems.
		(modprobe srm_env || true) 2>/dev/null
		if [ -f /proc/srm_environment/named_variables/booted_dev ]; then
			# Have SRM, so need BSD disklabels
			echo bsd
		else
			echo msdos
		fi;;
	    amd64|kfreebsd-amd64|i386|kfreebsd-i386|hurd-i386)
		echo gpt;;
	    arm|armeb|armel|armhf)
		echo msdos;;
	    arm64)
		echo gpt;;
	    hppa)
		echo msdos;;
	    ia64)
		echo gpt;;
	    m68k)
		case "$sub" in
		    amiga)
			echo amiga;;
		    atari|q40)
			echo atari;;
		    mac)
			echo mac;;
		    *vme*)
			echo msdos;;
		    sun*)
			echo sun;;
		    *)
			echo UNKNOWN;;
		esac;;
	    mips|mipsel|mips64el)
		echo msdos;;
	    powerpc|ppc64)
		case "$sub" in
		    apus)
			echo amiga;;
		    amiga)
			echo amiga;;
		    chrp)
			echo msdos;;
		    chrp_rs6k|chrp_ibm)
			echo msdos;;
		    chrp_pegasos)
			echo amiga;;
		    pasemi)
			echo msdos;;
		    prep)
			echo msdos;;
		    powermac_newworld)
			echo mac;;
		    powermac_oldworld)
			echo mac;;
		    ps3)
			echo msdos;;
		    cell)
			echo msdos;;
		    fsl)
			echo gpt;;
		    *)
			echo UNKNOWN;;
		esac;;
	    ppc64el)
		echo gpt;;
	    s390|s390x)
		if [ -e ./label ]; then
		    disklabel=$(cat label)
		fi
		# FBA devices have parted label dasd, but should not use dasd
		# partition table. Maybe FBA|ECKD type should be exposed by
		# partman-base and/or parted. LP: #1650300
		device=$(sed 's|.*/||' ./device)
		if grep -q "(FBA ).*$device" /proc/dasd/devices; then
		    disklabel=msdos
		fi
		if [ "$disklabel" != dasd ]; then
		    disklabel=msdos
		fi
		echo $disklabel;;
	    sh4)
		echo msdos;;
	    sparc|sparc64)
		echo sun;;
	    *)
		echo UNKNOWN;;
	esac
}

prepare_new_labels() {
	local dev devs restart code
	devs="$*"

	restart=
	for dev in $devs; do
		[ -d "$dev" ] || continue

		if [ -e /lib/partman/lib/lvm-remove.sh ]; then
			. /lib/partman/lib/lvm-remove.sh
			device_remove_lvm "$dev"
			code=$?
			if [ $code = 99 ]; then
				restart=1
			elif [ $code != 0 ]; then
				return $code
			fi
		fi
		if [ -e /lib/partman/lib/md-remove.sh ]; then
			. /lib/partman/lib/md-remove.sh
			device_remove_md "$dev"
			code=$?
			if [ $code = 99 ]; then
				restart=1
			elif [ $code != 0 ]; then
				return $code
			fi
		fi
	done

	if [ "$restart" ]; then
		stop_parted_server
		restart_partman || return 1
	fi

	return 0
}

create_new_label() {
	local dev default_type chosen_type types
	dev="$1"
	prompt_for_label="$2"

	[ -d "$dev" ] || return 1

	cd $dev

	open_dialog LABEL_TYPES
	types=$(read_list)
	close_dialog

	db_subst partman-partitioning/choose_label CHOICES "$types"
	PRIORITY=critical

	db_get partman-partitioning/default_label
	if [ "$RET" ]; then
		default_label="$RET"
	else
		default_label=$(default_disk_label)
	fi

	# Use gpt instead of msdos disklabel for disks larger than 2TiB
	if expr "$types" : ".*gpt.*" >/dev/null; then
		if [ "$default_label" = msdos ]; then
			disksize=$(cat size)
			if ! longint_le $disksize "$(expr 2 \* 1024 \* 1024 \* 1024 \* 1024)"; then
				default_label=gpt
			fi
		fi
	fi

	if [ "$prompt_for_label" = no ] && \
	   expr "$types" : ".*${default_label}.*" >/dev/null; then
		chosen_type="$default_label"
	else
		if expr "$types" : ".*${default_label}.*" >/dev/null; then
			db_set partman-partitioning/choose_label "$default_label"
			PRIORITY=low
		fi
		db_input $PRIORITY partman-partitioning/choose_label || true
		db_go || exit 1
		db_get partman-partitioning/choose_label

		chosen_type="$RET"
	fi

	if [ "$chosen_type" = sun ]; then
		db_input critical partman-partitioning/confirm_write_new_label
		db_go || exit 0
		db_get partman-partitioning/confirm_write_new_label
		if [ "$RET" = false ]; then
			db_reset partman-partitioning/confirm_write_new_label
			return 1
		fi
		db_reset partman-partitioning/confirm_write_new_label
	fi

	open_dialog NEW_LABEL "$chosen_type"
	close_dialog

	if [ "$chosen_type" = sun ]; then
		# write the partition table to the disk
		disable_swap "$dev"
		open_dialog COMMIT
		close_dialog
		sync
		# reread it from there
		open_dialog UNDO
		close_dialog
		enable_swap
	fi
}
