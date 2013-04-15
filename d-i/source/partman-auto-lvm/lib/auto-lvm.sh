# base.sh is already sourced through lvm-base.sh
. /lib/partman/lib/lvm-base.sh
. /lib/partman/lib/commit.sh
. /lib/partman/lib/auto-shared.sh
. /lib/partman/lib/recipes.sh

bail_out() {
	db_input critical partman-auto-lvm/$1 || true
	db_go || true
	exit 1
}

# Add a partition to hold a Physical Volume to the given recipe
# (Need $method in scope.)
add_envelope() {
	local scheme="$1"
	echo "$scheme${NL}100 1000 -1 ext3 method{ $method }"
}

# Create the partitions needed by a recipe to hold all PVs
# (need $scheme and $pv_devices in scope)
auto_lvm_create_partitions() {
	local dev free_size
	dev=$1

	get_last_free_partition_infos $dev
	free_size=$(convert_to_megabytes $free_size)

	expand_scheme

	ensure_primary

	create_primary_partitions
	create_partitions
}

VG_MAP_DIR=/var/lib/partman/auto_lvm_map
DEFAULT_VG="@DEFAULT@"
# Extract a map of which VGs to create on which PVs
#
# The map will be stored in $VG_MAP_DIR, one file for each VG;
# containing one PV per line on which it should be created.
#
# As the name for the default VG will be asked in auto_lvm_perform(), the
# temporary name is stored into $DEFAULT_VG.
auto_lvm_create_vg_map() {
	local pv_device line recipe_device vg_name vg_file pv_device pv_found

	rm -rf $VG_MAP_DIR
	mkdir -p $VG_MAP_DIR

	# Extracting needed VGs
	IFS="$NL"
	for line in $lvmscheme; do
		restore_ifs
		vg_name=$(echo "$line" | sed -n -e 's!.*in_vg{ *\([^ }]*\) *}.*!\1!p')
		[ "$vg_name" ] || vg_name=$DEFAULT_VG
		touch $VG_MAP_DIR/$vg_name
	done

	# Extracting needed PVs and provided VGs
	IFS="$NL"
	for line in $pvscheme; do
		restore_ifs
		vg_name=$(echo "$line" | sed -n -e 's!.*vg_name{ *\([^ }]*\) *}.*!\1!p')
		recipe_device=$(echo "$line" | sed -n -e 's!.*device{ *\([^ }]*\) *}.*!\1!p')
		# If no VG has been specified, use default VG
		[ "$vg_name" ] || vg_name="$DEFAULT_VG"
		# If no PV has been specified, use main device
		[ "$recipe_device" ] || recipe_device="$main_pv"

		# Find the device for this PV from the list of known PVs
		pv_found=
		for pv_device in $pv_devices; do
			if echo $pv_device | grep -q "$recipe_device[[:digit:]]*"; then
				pv_found=1
				break
			fi
		done
		if [ "$pv_found" ]; then
			echo $pv_device >> $VG_MAP_DIR/$vg_name
		else
			bail_out no_such_pv
		fi
	done
	restore_ifs

	# Add unused devices to default VG
	for pv_device in $pv_devices; do
		if ! grep -q "^$pv_device$" $VG_MAP_DIR/*; then
			echo $pv_device >> $VG_MAP_DIR/$DEFAULT_VG
		fi
	done

	# Ensure that all VG have at least one PV
	for vg_file in $VG_MAP_DIR/*; do
		if ! [ -s $vg_file ]; then
			bail_out no_pv_in_vg
		fi
	done
}

auto_lvm_prepare() {
	local devs main_device extra_devices method size free_size normalscheme
	local pvscheme lvmscheme target dev devdir main_pv physdev
	devs="$1"
	method=$2

	size=0
	for dev in $devs; do
		[ -f $dev/size ] || return 1
		size=$(($size + $(cat $dev/size)))
	done

	set -- $devs
	main_device=$1
	shift
	extra_devices="$*"

	# Be sure the modules are loaded
	modprobe dm-mod >/dev/null 2>&1 || true
	modprobe lvm-mod >/dev/null 2>&1 || true

	if type update-dev >/dev/null 2>&1; then
		log-output -t update-dev update-dev --settle
	fi

	if [ "$extra_devices" ]; then
		for dev in $devs; do
			physdev=$(cat $dev/device)
			target="${target:+$target, }${physdev#/dev/}"
		done
		db_metaget partman-auto-lvm/text/multiple_disks description
		target=$(printf "$RET" "$target")
	else
		target="$(humandev $(cat $main_device/device)) - $(cat $main_device/model)"
	fi
	target="$target: $(longint2human $size)"
	free_size=$(convert_to_megabytes $size)

	choose_recipe lvm "$target" "$free_size" || return $?

	auto_init_disks $devs || return $?
	for dev in $devs; do
		get_last_free_partition_infos $dev

		# Check if partition is usable; use existing partman-auto
		# template as we depend on it
		if [ "$free_type" = unusable ]; then
			db_input critical partman-auto/unusable_space || true
			db_go || true
			return 1
		fi
	done

	# Change to any one of the devices - we arbitrarily pick the first -
	# to ensure that partman-auto can detect its label.  Of course this
	# only works if all the labels match, but that should be the case
	# since we just initialised them all following the same rules.
	cd "${devs%% *}"
	decode_recipe $recipe lvm
	cd -

	# Make sure the recipe contains lvmok tags
	if ! echo "$scheme" | grep -q lvmok; then
		bail_out unusable_recipe
	fi

	# Make sure a boot partition isn't marked as lvmok, unless the user
	# has told us it is ok for /boot to reside on a logical volume
	if echo "$scheme" | grep lvmok | grep -q "[[:space:]]/boot[[:space:]]"; then
		db_input critical partman-auto-lvm/no_boot || true
		db_go || return 255
		db_get partman-auto-lvm/no_boot || true
		[ "$RET" = true ] || bail_out unusable_recipe
	fi

	# This variable will be used to store the partitions that will be LVM
	# by create_partitions; zero it to be sure it's not cluttered.
	# It will be used later to provide real paths to partitions to LVM.
	# (still one atm)
	pv_devices=''

	### Situation
	### We have a recipe foo from arch bar. we don't know anything other than what
	### partitions can go on lvm ($lvmok{ } tag).
	### As output we need to have 2 recipes:
	### - recipe 1 (normalscheme) that will contain all non-lvm partitions including /boot.
	###            The /boot partition should already be defined in the schema.
	### - recipe 2 everything that can go on lvm and it's calculated in perform_recipe_by_lvm.

	# Get the scheme of partitions that must be created outside LVM
	normalscheme=$(echo "$scheme" | grep -v lvmok)
	lvmscheme=$(echo "$scheme" | grep lvmok)

	# Check if the scheme contains a boot partition; if not warn the user
	# Except for powerpc/prep as that has the kernel in the prep partition
	if type archdetect >/dev/null 2>&1; then
		archdetect=$(archdetect)
	else
		archdetect=unknown/generic
	fi

	case $archdetect in
	    powerpc/prep)
		: ;;
	    *)
		# TODO: make check more explicit, mountpoint{ / }?
		if ! echo "$normalscheme" | grep -q "[[:space:]]/[[:space:]]" && \
		   ! echo "$normalscheme" | grep -q "[[:space:]]/boot[[:space:]]"; then
			db_input critical partman-auto-lvm/no_boot || true
			db_go || return 255
			db_get partman-auto-lvm/no_boot || true
			[ "$RET" = true ] || return 255
		fi
		;;
	esac

	main_pv=$(cat $main_device/device)

	# Partitions with method $method will hold Physical Volumes
	pvscheme=$(echo "$normalscheme" | grep "method{ $method }")

	# Start with partitions that are outside LVM and not PVs
	scheme="$(echo "$normalscheme" | grep -v "method{ $method }")"
	# Add partitions declared to hold PVs on the main device
	scheme="$scheme$NL$(echo "$pvscheme" | grep "device{ $main_pv[[:digit:]]* }")"
	# Add partitions declared to hold PVs without specifying a device
	scheme="$scheme$NL$(echo "$pvscheme" | grep -v 'device{')"
	# If we still don't have a partition to hold PV, add it
	if ! echo "$scheme" | grep -q "method{ $method }"; then
		scheme="$(add_envelope "$scheme")"
	fi
	auto_lvm_create_partitions $main_device

	# Create partitions for PVs on extra devices
	for dev in $extra_devices; do
		physdev=$(cat $dev/device)
		scheme="$(echo "$pvscheme" | grep "device{ $physdev[[:digit:]]* }")"
		if [ -z "$scheme" ]; then
			scheme="$(add_envelope "")"
		fi
		auto_lvm_create_partitions $dev
	done

	# Extract the mapping of which VG goes onto which PV
	auto_lvm_create_vg_map

	if ! confirm_changes partman-lvm; then
		return 255
	fi

	disable_swap
	# Write the partition tables
	for dev in $devs; do
		cd $dev
		open_dialog COMMIT
		close_dialog
		device_cleanup_partitions
	done

	# Remove zombie LVMs which happed to be left-over on the newly
	# created partition, because the disk was not zeroed out.
	# Wait for devices to settle
	if type update-dev >/dev/null 2>&1; then
		log-output -t update-dev update-dev --settle
	fi
	# Give LVM a kick to rescan devices
	/sbin/vgdisplay 2>/dev/null
	# Finally purge LVM remains
	for dev in $devs; do
	    device_remove_lvm $dev
	done

	update_all
}

auto_lvm_perform() {
	# Use hostname as default vg name (if available)
	local defvgname pv vg_file vg_name
	# $pv_devices will be overridden with content from $VG_MAP_DIR
	local pv_devices

	db_get partman-auto-lvm/new_vg_name
	if [ -z "$RET" ]; then
		if [ -s /etc/hostname ]; then
			defvgname=$(cat /etc/hostname | head -n 1 | tr -d " ")
		fi
		if [ "$defvgname" ]; then
			db_set partman-auto-lvm/new_vg_name $defvgname-vg
		else
			db_set partman-auto-lvm/new_vg_name Ubuntu
		fi
	fi

	# Choose name, create VG and attach each partition as a physical volume
	noninteractive=true
	while true; do
		db_input medium partman-auto-lvm/new_vg_name || eval $noninteractive
		db_go || return 1
		db_get partman-auto-lvm/new_vg_name
		defvgname="$RET"

		# Check that the volume group name is not in use
		if ! vg_get_info "$defvgname" && ! stat "/dev/$defvgname"; then
			break
		fi
		noninteractive="bail_out vg_exists"
		db_register partman-auto-lvm/new_vg_name_exists partman-auto-lvm/new_vg_name
	done

	# auto_lvm_create_vg_map() will have created one file for each VG
	for vg_file in $VG_MAP_DIR/*; do
		pv_devices="$(cat $vg_file)"
		vg_name=$(basename $vg_file)
		[ $vg_name = $DEFAULT_VG ] && vg_name="$defvgname"

		if vg_create "$vg_name" $pv_devices; then
			perform_recipe_by_lvm "$vg_name" $recipe
		else
			bail_out vg_create_error
		fi
		vg_lock_pvs "$vg_name" $pv_devices
	done

	# Default to accepting the autopartitioning
	menudir_default_choice /lib/partman/choose_partition finish finish || true
}
