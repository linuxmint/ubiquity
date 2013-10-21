#!/bin/sh

set -e
. /usr/share/debconf/confmodule
#set -x

if [ -z "$1" ]; then
	PROGRESSBAR=hw-detect/detect_progress_step
else
	PROGRESSBAR=$1
fi

NEWLINE="
"
MISSING_MODULES_LIST=""
SUBARCH="$(archdetect)"

finish_install=/usr/lib/finish-install.d/30hw-detect

LOAD_IDE=""
if db_get hw-detect/load-ide && [ "$RET" = true ]; then
	LOAD_IDE=1
fi

# Check for virtio devices
if [ -d /sys/bus/pci/devices ] && \
	grep -q 0x1af4 /sys/bus/pci/devices/*/vendor 2>/dev/null && \
	! grep -q ^virtio_ /proc/modules; then
	anna-install virtio-modules || true
fi

if [ -x /sbin/depmod ]; then
	depmod -a > /dev/null 2>&1 || true
fi

log () {
	logger -t hw-detect "$@"
}

is_not_loaded() {
	! ((cut -d" " -f1 /proc/modules | grep -q "^$1\$") || \
	   (cut -d" " -f1 /proc/modules | sed -e 's/_/-/g' | grep -q "^$1\$"))
}

is_available () {
	[ "$(modprobe -l $1)" ] || return 1
}

# Module as first parameter, description of device the second.
missing_module () {
	if ! in_list "$1" "$MISSING_MODULES_LIST"; then
		if [ -n "$MISSING_MODULES_LIST" ]; then
			MISSING_MODULES_LIST="$MISSING_MODULES_LIST, "
		fi
		MISSING_MODULES_LIST="$MISSING_MODULES_LIST$1 ($2)"
	fi
}

# The list can be delimited with spaces or spaces and commas.
in_list() {
	echo "$2" | grep -q "\(^\| \)$1\(,\| \|$\)"
}

snapshot_devs() {
	echo -n `grep : /proc/net/dev | cut -d':' -f1`
}

compare_devs() {
	local olddevs="$1"
	local devs="$2"
	local dev newdevs

	newdevs=
	for dev in $devs; do
		if ! echo " $olddevs " | grep -q " $dev "; then
			newdevs="${newdevs:+$newdevs }$dev"
		fi
	done
	echo "$newdevs"
}

load_module() {
	local module="$1"
	local cardname="$2"
	local devs=""
	local olddevs=""
	local newdev=""

	old=`cat /proc/sys/kernel/printk`
	echo 0 > /proc/sys/kernel/printk

	devs="$(snapshot_devs)"
	if log-output -t hw-detect modprobe -v "$module"; then
		olddevs="$devs"
		devs="$(snapshot_devs)"
		newdevs="$(compare_devs "$olddevs" "$devs")"

		# Make sure space is used as a delimiter.
		IFS_SAVE="$IFS"
		IFS=" "
		if [ -n "$newdevs" -a -n "$cardname" ]; then
			mkdir -p /etc/network
			for dev in $newdevs; do
				echo "${dev}:${cardname}" >> /etc/network/devnames
			done
		fi
		IFS="$IFS_SAVE"
	else   
		log "Error loading '$module'"
		if [ "$module" != floppy ] && [ "$module" != ide-floppy ] && \
		   [ "$module" != ide-cd ] && [ "$module" != ide-generic ]; then
			db_subst hw-detect/modprobe_error CMD_LINE_PARAM "modprobe -v $module"
			db_input medium hw-detect/modprobe_error || [ $? -eq 30 ]
			db_go
		fi
	fi

	echo $old > /proc/sys/kernel/printk
}

# Some pci chipsets are needed or there can be DMA or other problems.
get_ide_chipset_info() {
	for ide_module in $(find /lib/modules/*/kernel/drivers/ide/pci/ -type f 2>/dev/null); do
		if [ -e $ide_module ]; then
			baseidemod=$(echo $ide_module | sed 's/\.ko$//; s/.*\///')
			echo "$baseidemod:IDE chipset support"
		fi
	done
}

# Return list of lines formatted "module:Description"
get_detected_hw_info() {
	if [ "${SUBARCH%%/*}" = powerpc ]; then
		discover-mac-io
		if [ "$SUBARCH" = powerpc/chrp_rs6k ] || \
		   [ "$SUBARCH" = powerpc/chrp_ibm ]; then
			discover-ibm
		fi
	fi
	if [ "${SUBARCH%%/*}" = sparc ]; then
		discover-sbus
	fi
	if [ -d /sys/bus/usb ]; then
		echo "usb-storage:USB storage"
	fi
}

# NewWorld PowerMacs don't want floppy or ide-floppy, and on some models
# (e.g. G5s) the kernel hangs when loading the module.
get_floppy_info() {
	case $SUBARCH in
		powerpc/powermac_newworld) ;;
		*) echo "floppy:Linux Floppy" ;;
	esac
}

get_ide_floppy_info() {
	case $SUBARCH in
		powerpc/powermac_newworld) ;;
		*) echo "ide-floppy:Linux IDE floppy" ;;
	esac
}

get_rtc_info() {
	# On i386, this gets loaded by hotplug through isapnp, but that
	# doesn't work on amd64.
	case $SUBARCH in
		amd64/*) register-module rtc ;;
	esac
}

# Manually load modules to enable things we can't detect.
# XXX: This isn't the best way to do this; we should autodetect.
# The order of these modules are important.
get_manual_hw_info() {
	if [ "$LOAD_IDE" ]; then
		get_floppy_info
		get_ide_chipset_info
		echo "ide-generic:Linux IDE support"
		get_ide_floppy_info
		echo "ide-disk:Linux ATA DISK"
		echo "ide-cd:Linux ATAPI CD-ROM"
	fi
	get_rtc_info
}

# Should be greater than the number of kernel modules we can reasonably
# expect it will ever need to load.
MAX_STEPS=1000
OTHER_STEPS=4
# Use 1/10th of the progress bar for the non-module-load steps.
OTHER_STEPSIZE=$(expr $MAX_STEPS / 10 / $OTHER_STEPS)
db_progress START 0 $MAX_STEPS $PROGRESSBAR

db_progress INFO hw-detect/detect_progress_step

# TODO: Can possibly be removed if udev will load yenta_socket automatically
# Load yenta_socket, if hardware is available, for Cardbus cards.
if [ -d /sys/bus/pci/devices ] && \
	grep -q 0x060700 /sys/bus/pci/devices/*/class 2>/dev/null && \
	! grep -q ^yenta_socket /proc/modules; then
	db_subst hw-detect/load_progress_step CARDNAME "Cardbus bridge"
	db_subst hw-detect/load_progress_step MODULE "yenta_socket"
	db_progress INFO hw-detect/load_progress_step
	
	log "Detected Cardbus bridge, loading yenta_socket"
	load_module yenta_socket
	# Ugly hack, but what's the alternative?
	sleep 3 || true
fi

# Load the ethernet gadget network driver (g_ether) on S3C2410/S3C2440 (Openmoko GTA01/02)
if [ -d /sys/bus/platform/devices/s3c2440-usbgadget -o \
	-d /sys/bus/platform/devices/s3c2410-usbgadget ] ; then
	db_subst hw-detect/load_progress_step CARDNAME "S3C2410/S3C2440 SoC"
	db_subst hw-detect/load_progress_step MODULE "g_ether"
	db_progress INFO hw-detect/load_progress_step
	
	log "Detected S3C2410/S3C2440 SoC, loading g_ether"
	load_module g_ether
	register-module g_ether
fi

# Load xenbus_probe_frontend if we're running under the Xen hypervisor, so
# that it can deal with autoloading such things as xen-blkfront and
# xen-netfront.
if [ "$(cat /sys/hypervisor/type 2>/dev/null || true)" = xen ] && \
   [ ! -d /sys/bus/xen ]; then
	db_subst hw-detect/load_progress_step CARDNAME "Xen frontend"
	db_subst hw-detect/load_progress_step MODULE "xenbus_probe_frontend"
	db_progress INFO hw-detect/load_progress_step

	log "Detected Xen hypervisor, loading xenbus_probe_frontend"
	load_module xenbus_probe_frontend
	register-module -i xenbus_probe_frontend
fi

# If using real hotplug, re-run the rc scripts to pick up new modules.
# TODO: this just loads modules itself, rather than handing back a list
# Since we've just run depmod, new modules might be available, so we
# must trigger as well as settle.
update-dev >/dev/null

ALL_HW_INFO=$(get_detected_hw_info; get_manual_hw_info)
db_progress STEP $OTHER_STEPSIZE

# Remove modules that are already loaded or not available, and construct
# the list for the question.
LIST=""
PROCESSED=""
AVAIL_MODULES="$(find /lib/modules/$(uname -r)/ | sed 's!.*/!!' | cut -d . -f 1)"
LOADED_MODULES="$(cut -d " " -f 1 /proc/modules) $(cut -d " " -f 1 /proc/modules | sed -e 's/_/-/g')"
IFS_SAVE="$IFS"
IFS="$NEWLINE"
for device in $ALL_HW_INFO; do
	module="${device%%:*}"
	cardname="${device##*:}"
	if [ "$module" != "ignore" -a "$module" != "" ] &&
	   ! in_list "$module" "$LOADED_MODULES" &&
	   ! in_list "$module" "$PROCESSED"
	then
		if [ -z "$cardname" ]; then
			cardname="[Unknown]"
		fi
		
		if in_list "$module" "$AVAIL_MODULES"; then
			LIST="${LIST:+$LIST, }$module ($(echo "$cardname" | sed 's/,/ /g'))"
			PROCESSED="$PROCESSED $module"
		else
			missing_module "$module" "$cardname"
		fi
	fi
done
IFS="$IFS_SAVE"
db_progress STEP $OTHER_STEPSIZE

if [ "$LIST" ]; then
	# Ask which modules to install.
	db_subst hw-detect/select_modules list "$LIST"
	db_set hw-detect/select_modules "$LIST"
	db_input medium hw-detect/select_modules || true
	db_go || exit 10 # back up
	db_get hw-detect/select_modules
	LIST="$RET"
fi

list_to_lines() {
	echo "$LIST" | sed 's/, /\n/g'
}

# Work out amount to step per module load. expr rounds down, so 
# it may not get quite to 100%, but will at least never exceed it.
MODULE_STEPS=$(expr \( $MAX_STEPS - \( $OTHER_STEPS \* $OTHER_STEPSIZE \) \))
if [ "$LIST" ]; then
	MODULE_STEPSIZE=$(expr $MODULE_STEPS / $(list_to_lines | wc -l))
fi

IFS="$NEWLINE"

for device in $(list_to_lines); do
	module="${device%% *}"
	cardname="`echo $device | cut -d'(' -f2 | sed 's/)$//'`"
	# Restore IFS after extracting the fields.
	IFS="$IFS_SAVE"

	if [ -z "$module" ] ; then module="[Unknown]" ; fi
	if [ -z "$cardname" ] ; then cardname="[Unknown]" ; fi

	log "Detected module '$module' for '$cardname'"

	if is_not_loaded "$module"; then
		db_subst hw-detect/load_progress_step CARDNAME "$cardname"
		db_subst hw-detect/load_progress_step MODULE "$module"
		db_progress INFO hw-detect/load_progress_step
		if [ "$cardname" = "[Unknown]" ]; then
			load_module "$module"
		else
			load_module "$module" "$cardname"
		fi
	fi

	db_progress STEP $MODULE_STEPSIZE
	IFS="$NEWLINE"
done
IFS="$IFS_SAVE"

if [ -z "$LIST" ]; then
	db_progress STEP $MODULE_STEPS
fi

# Load ide-generic and check if that results in new block devices.
# If so, make sure it is added to the initrd for the installed system.
# Note: this may need to be done for more systems than just systems
# that have an ISA bus, but that seems like a good start; it could also
# be done unconditionally.
if [ -z "$LOAD_IDE" ] && is_not_loaded ide-generic && \
   [ -e /sys/bus/isa ] && is_available ide-generic; then
	update-dev --settle >/dev/null
	blockdev_count=$(ls /sys/block | wc -w)

	log "ISA bus detected; loading module 'ide-generic'"
	load_module ide-generic
	update-dev --settle >/dev/null
	if [ $(ls /sys/block | wc -w) -gt $blockdev_count ]; then
		log "New devices detected after loading ide-generic"

		# This will tell initramfs-tools to load ide-generic
		kopts=
		if db_get debian-installer/add-kernel-opts && [ "$RET" ]; then
			kopts="$RET"
		fi
		if ! echo "$kopt" | grep -Eq "(^| )all_generic_ide(=1|)( |$)"; then
			db_set debian-installer/add-kernel-opts \
				"${kopts:+$kopts }all_generic_ide=1"
		fi
	fi
fi

if ! is_not_loaded ohci1394 || ! is_not_loaded firewire-ohci; then
	# if firewire was found, try to enable firewire cd support
	if is_not_loaded sbp2 && is_not_loaded firewire-sbp2 && \
	    is_available scsi_mod; then
	    	sbp2module=
		if is_available firewire-sbp2; then
			sbp2module=firewire-sbp2
		elif is_available sbp2; then
			sbp2module=sbp2
		fi
		if [ -n "$sbp2module" ]; then
			db_subst hw-detect/load_progress_step CARDNAME "FireWire CDROM support"
			db_subst hw-detect/load_progress_step MODULE "$sbp2module"
			db_progress INFO hw-detect/load_progress_step
			load_module "$sbp2module"
			register-module "$sbp2module"
		else
			missing_module firewire-sbp2 "FireWire CDROM"
		fi
	fi
	db_progress STEP $OTHER_STEPSIZE
fi

# Always load the printer driver on i386 and amd64; it's hard to autodetect.
case $SUBARCH in
	i386/*|amd64/*)
		register-module lp
		;;
esac

apply_pcmcia_resource_opts() {
	local config_opts=/etc/pcmcia/config.opts
	
	# Idempotency
	if ! [ -f ${config_opts}.orig ]; then
		cp $config_opts ${config_opts}.orig
	fi
	cp ${config_opts}.orig $config_opts

	local mode=""
	local rmode=""
	local type=""
	local value=""
	while [ -n "$1" ] && [ -n "$2" ] && [ -n "$3" ]; do
		if [ "$1" = exclude ]; then
			mode=exclude
			rmode=include
			shift
		elif [ "$1" = include ]; then
			mode=include
			rmode=exclude
			shift
		fi
		type="$1"
		shift
		value="$1"
		shift
		
		if grep -q "^$rmode $type $value\$" $config_opts; then
			sed "s/^$rmode $type $value\$/$mode $type $value/" \
				$config_opts >${config_opts}.new
			mv ${config_opts}.new $config_opts
		else
			echo "$mode $type $value" >>$config_opts
		fi
	done
}

# get pcmcia running if possible
PCMCIA_INIT=/etc/init.d/pcmciautils
if [ -x "$PCMCIA_INIT" ]; then
	if is_not_loaded pcmcia_core; then
		db_input low hw-detect/pcmcia_resources || true
		db_go || true

		if db_get hw-detect/pcmcia_resources && [ "$RET" ]; then
			apply_pcmcia_resource_opts $RET
		fi
		# cdebconf doesn't set seen flags, so this would normally be
		# asked again on subsequent hw-detect runs, which is
		# annoying.
		db_fset hw-detect/pcmcia_resources seen true || true

		db_progress INFO hw-detect/pcmcia_step
		$PCMCIA_INIT start 2>&1 | log
		db_progress STEP $OTHER_STEPSIZE
	fi
fi

have_pcmcia=0
if ls /sys/class/pcmcia_socket/* >/dev/null 2>&1; then
	if db_get hw-detect/start_pcmcia && [ "$RET" = false ]; then
		have_pcmcia=0
	else
		have_pcmcia=1
	fi
fi

# find Cardbus network cards
cardbus_check_netdev()
{
	local socket="$1"
	local netdev="$2"
	if [ -L "$netdev/device" ] && \
		[ -d "$socket/device/$(basename "$(readlink "$netdev/device")")" ]; then
		echo "$(basename "$netdev")" >> /etc/network/devhotplug
	fi
}

# Try to do this only once..
if [ "$have_pcmcia" -eq 1 ] && \
   ! grep -q pcmciautils /var/lib/apt-install/queue 2>/dev/null; then
	log "Detected PCMCIA, installing pcmciautils."
	apt-install pcmciautils || true

	for socket in /sys/class/pcmcia_socket/*; do
		for netdev in /sys/class/net/*; do
			cardbus_check_netdev "$socket" "$netdev"
		done
	done

	if db_get hw-detect/pcmcia_resources && [ -n "$RET" ]; then
		echo "mkdir /target/etc/pcmcia 2>/dev/null || true" \
			>>$finish_install
		echo "cp /etc/pcmcia/config.opts /target/etc/pcmcia/config.opts" \
			>>$finish_install
	fi
fi

# Install udev into target
apt-install udev || true

# Install pciutils/usbutils
if [ -d /sys/bus/pci ]; then
	apt-install pciutils || true
fi

if [ -d /sys/bus/usb ]; then
	apt-install usbutils || true
fi

# If hardware has support for pmu, install pbbuttonsd
if [ -d /sys/class/misc/pmu/ ]; then
	apt-install pbbuttonsd || true
fi

# Install eject?
if [ -n "$(list-devices cd; list-devices maybe-usb-floppy)" ]; then
	apt-install eject || true
fi

# Install optimised libc based on CPU type
case "$(udpkg --print-architecture)" in
    i386)
	case "$(grep '^cpu family' /proc/cpuinfo | head -n1 | cut -d: -f2)" in
	    " 6"|" 15")
		# intel 686 or Amd k6.
		apt-install libc6-i686 || true
                ;;
	esac
	;;
    sparc)
	if grep -q '^type.*: sun4u' /proc/cpuinfo ; then
		# sparc v9 or v9b
		if grep -q '^cpu.*: .*UltraSparc III' /proc/cpuinfo; then
			apt-install libc6-sparcv9b || true
		else
			apt-install libc6-sparcv9 || true
		fi
	fi
	;;
esac

db_progress SET $MAX_STEPS
db_progress STOP

if [ -n "$MISSING_MODULES_LIST" ]; then
	log "Missing modules '$MISSING_MODULES_LIST"
fi

check-missing-firmware

sysfs-update-devnames

# Let userspace /dev tools rescan the devices
update-dev --settle >/dev/null

exit 0
