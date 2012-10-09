. /lib/partman/lib/lvm-base.sh

# List PVs to be removed to initialize a device
remove_lvm_find_vgs() {
	local realdev vg pvs pv disk
	realdev="$1"

	# Simply exit if there is no lvm support
	[ -f /var/lib/partman/lvm ] || exit 0

	# Check all VGs to see which PV needs removing
	# BUGME: the greps in this loop should be properly bounded so they
	#	 do not match on partial matches!
	#        Except that we want partial matches for disks...
	for vg in $(vg_list); do
		pvs="$(vg_list_pvs $vg)"

		if ! echo "$pvs" | grep -q "$realdev"; then
			continue
		fi

		pvs="$(echo -n "$pvs" | grep -v "$realdev")"
		# Make sure the VG doesn't span any other disks
		if [ "$pvs" ]; then
			# Except on disks that are going to be auto-partitioned
			db_get partman-auto/disk || RET=""
			for disk in $RET; do
				pvs="$(echo -n "$pvs" | grep -v "$disk")"
			done
			if [ "$pvs" ]; then
				log-output -t partman-lvm vgs
				db_input critical partman-lvm/device_remove_lvm_span || true
				db_go || true
				return 1
			fi
		fi
		echo "$vg"
	done
}

# Wipes any traces of LVM from a disk
# Normally called from a function that initializes a device
# Note: if the device contains an empty PV, it will not be removed
device_remove_lvm() {
	local dev realdev tmpdev restart confirm
	local pvs pv vgs vg lvs lv pvtext vgtext lvtext
	dev="$1"
	cd $dev

	# Check if the device already contains any physical volumes
	realdev=$(mapdevfs "$(cat $dev/device)")
	if ! pv_on_device "$realdev"; then
		return 0
	fi

	vgs="$(remove_lvm_find_vgs $realdev)" || return 1
	[ "$vgs" ] || return 0

	pvs=""
	lvs=""
	for vg in $vgs; do
		pvs="${pvs:+$pvs$NL}$(vg_list_pvs $vg)"
		lvs="${lvs:+$lvs$NL}$(vg_list_lvs $vg)"
	done

	# Ask for permission to erase LVM volumes
	lvtext=""
	for lv in $lvs; do
		lvtext="${lvtext:+$lvtext, }$lv"
	done
	vgtext=""
	for vg in $vgs; do
		vgtext="${vgtext:+$vgtext, }$vg"
	done
	pvtext=""
	for pv in $pvs; do
		pvtext="${pvtext:+$pvtext, }$pv"
	done

	db_fget partman-lvm/device_remove_lvm seen
	if [ $RET = true ]; then
		# Answer has been preseeded
		db_get partman-lvm/device_remove_lvm
		confirm=$RET
	else
		db_subst partman-lvm/device_remove_lvm LVTARGETS "$lvtext"
		db_subst partman-lvm/device_remove_lvm VGTARGETS "$vgtext"
		db_subst partman-lvm/device_remove_lvm PVTARGETS "$pvtext"
		db_input critical partman-lvm/device_remove_lvm
		db_go || return 1
		db_get partman-lvm/device_remove_lvm
		confirm=$RET
		db_reset partman-lvm/device_remove_lvm
	fi
	if [ "$confirm" != true ]; then
		return 255
	fi

	# We need devicemapper support here
	modprobe dm-mod >/dev/null 2>&1

	for vg in $vgs; do
		# Remove LVs from the VG
		for lv in $(vg_list_lvs $vg); do
			lv_delete $vg $lv
		done

		# Remove the VG
		vg_delete $vg
	done
	# Remove the PVs and unlock the devices
	for pv in $pvs; do
		pv_delete $pv
		partman_unlock_unit $pv
	done

	# Make sure that parted has no stale LVM info
	restart=""
	for tmpdev in $DEVICES/*; do
		[ -d "$tmpdev" ] || continue

		realdev=$(cat $tmpdev/device)

		if [ -b "$realdev" ] || \
		   ! $(echo "$realdev" | grep -q "/dev/mapper/"); then
			continue
		fi

		rm -rf $tmpdev
		restart=1
	done

	if [ "$restart" ]; then
		return 99
	fi
	return 0
}
