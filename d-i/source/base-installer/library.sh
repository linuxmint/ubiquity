# waypoint vars
WAYPOINTS=""
NUM_STEPS=0

# progress bar vars
export PB_POSITION=0
export PB_WAYPOINT_LENGTH=0

# used for setting up apt
PROTOCOL=
MIRROR=
DIRECTORY=
COMPONENTS=
DISTRIBUTION=

# used by kernel installation code
KERNEL=
KERNEL_LIST=/tmp/available_kernels.txt
KERNEL_MAJOR="$(uname -r | cut -d . -f 1,2)"
KERNEL_VERSION="$(uname -r | cut -d - -f 1)"
KERNEL_ABI="$(uname -r | cut -d - -f 1,2)"
KERNEL_FLAVOUR=$(uname -r | cut -d - -f 3-)
MACHINE="$(uname -m)"
NUMCPUS=$(cat /var/numcpus 2>/dev/null) || true
CPUINFO=/proc/cpuinfo

# files and directories
APT_SOURCES=/target/etc/apt/sources.list
APT_CONFDIR=/target/etc/apt/apt.conf.d
IT_CONFDIR=/target/etc/initramfs-tools/conf.d

log() {
	logger -t base-installer "$@"
}
error() {
	log "error: $*"
}
warning() {
	log "warning: $*"
}
info() {
	log "info: $*"
}

exit_error() {
	error "exiting on error $1"
	db_progress stop
	db_input critical $1 || [ $? -eq 30 ]
	db_go
	exit 1
}

waypoint () {
	WAYPOINTS="$WAYPOINTS $1:$2"
	NUM_STEPS=$(($NUM_STEPS + $1)) || true
}

run_waypoints () {
	db_progress START 0 $NUM_STEPS $1
	for item in $WAYPOINTS; do
		PB_WAYPOINT_LENGTH=$(echo $item | cut -d: -f 1)
		WAYPOINT=$(echo $item | cut -d: -f 2)
		# Not all of the section headers need exist.
		db_progress INFO "base-installer/section/$WAYPOINT" || true
		eval $WAYPOINT
		PB_POSITION=$(($PB_POSITION + $PB_WAYPOINT_LENGTH)) || true
		db_progress SET $PB_POSITION
	done
	db_progress STOP
}

update_progress () {
	# Updates the progress bar to a new position within the space allocated
	# for the current waypoint.
	NW_POS=$(($PB_POSITION + $PB_WAYPOINT_LENGTH * $1 / $2))
	db_progress SET $NW_POS
}

check_target () {
	# Make sure something is mounted on the target.
	# Partconf causes the latter format.
	if ! grep -q '/target ' /proc/mounts && \
	   ! grep -q '/target/ ' /proc/mounts; then
		exit_error base-installer/no_target_mounted
	fi

	# Warn about installation over an existing unix.
	if [ -e /target/bin/sh -o -L /target/bin/sh ]; then
		warning "attempting to install to unclean target"
		db_capb ""
		db_input high base-installer/use_unclean_target || true
		db_go || exit 10
		db_capb backup
		db_get base-installer/use_unclean_target
		if [ "$RET" = false ]; then
			db_reset base-installer/use_unclean_target
			exit_error base-installer/unclean_target_cancel
		fi
		db_reset base-installer/use_unclean_target
	fi

	# Undo dev bind mounts for idempotency.
	if grep -qE '^[^ ]+ /target/dev' /proc/mounts; then
		umount /target/dev
	fi
	# Unmount /dev/.static/dev if mounted on same device as /target
	mp_stdev=$(grep -E '^[^ ]+ /dev/\.static/dev' /proc/mounts | \
		   cut -d" " -f1)
	if [ "$mp_stdev" ] && grep -q "^$mp_stdev /target " /proc/mounts; then
		umount /dev/.static/dev
	fi
}

setup_dev () {
	# Ensure static device nodes created during install are preserved
	# Tests in MAKEDEV require this is done in the D-I environment
	mkdir -p /dev/.static/dev
	chmod 700 /dev/.static/
	mount --bind /target/dev /dev/.static/dev
	# Mirror device nodes in D-I environment to target
	mount --bind /dev /target/dev/
}

# TODO: as we no longer have to create devices here, the apt-install calls
# could possibly better be done as post-base-installer hooks from partman
install_filesystems () {
	# RAID
	if [ -e /proc/mdstat ] && grep -q ^md /proc/mdstat ; then
		apt-install mdadm
	fi
	# device-mapper
	if grep -q " device-mapper$" /proc/misc; then
		# Avoid warnings from lvm2 tools about open file descriptors
		export LVM_SUPPRESS_FD_WARNINGS=1

		# We can't check the root node directly as is done above because
		# root could be on an LVM LV on top of an encrypted device
		if type dmsetup >/dev/null 2>&1 && \
		   dmsetup table | cut -d' ' -f4 | grep -q "crypt" 2>/dev/null; then
			apt-install cryptsetup
		fi

		if type dmraid >/dev/null 2>&1; then
			if dmraid -s -c >/dev/null 2>&1 && \
			   [ "$(dmraid -s -c | grep -iv "No RAID disks")" ]; then
				apt-install dmraid
			fi
		fi

		if pvdisplay | grep -iq "physical volume ---"; then
			apt-install lvm2
		fi
	fi
}

configure_apt_preferences () {
	[ ! -d "$APT_CONFDIR" ] && mkdir -p "$APT_CONFDIR"

	# Make apt trust Debian CDs. This is not on by default (we think).
	# This will be left in place on the installed system.
	cat > $APT_CONFDIR/00trustcdrom <<EOT
APT::Authentication::TrustCDROM "true";
EOT

	# Avoid clock skew causing gpg verification issues.
	# This file will be left in place until the end of the install.
	cat > $APT_CONFDIR/00IgnoreTimeConflict << EOT
Acquire::gpgv::Options { "--ignore-time-conflict"; };
EOT

	if db_get debian-installer/allow_unauthenticated && [ "$RET" = true ]; then
		# This file will be left in place until the end of the install.
		cat > $APT_CONFDIR/00AllowUnauthenticated << EOT
APT::Get::AllowUnauthenticated "true";
Aptitude::CmdLine::Ignore-Trust-Violations "true";
EOT
	fi
}

apt_update () {
	log-output -t base-installer chroot /target apt-get update \
		|| apt_update_failed=$?

	if [ "$apt_update_failed" ]; then
		warning "apt update failed: $apt_update_failed"
	fi
}

install_extra () {
	info "Installing queued packages into /target/."

	if [ -f /var/lib/apt-install/queue ] ; then
		# We need to install these one by one in case one fails.
		PKG_COUNT=`cat /var/lib/apt-install/queue | wc -w`
		CURR_PKG=0
		for PKG in `cat /var/lib/apt-install/queue`; do
			db_subst base-installer/section/install_extra_package SUBST0 "$PKG"
			db_progress INFO base-installer/section/install_extra_package

			if ! log-output -t base-installer apt-install $PKG; then
				warning "Failed to install $PKG into /target/: $?"
			fi

			# Advance progress bar within space allocated for install_extra
			CURR_PKG=$(($CURR_PKG + 1))
			update_progress $CURR_PKG $PKG_COUNT
		done
	fi
}

pre_install_hooks () {
	# avoid apt-install installing things; apt is not configured yet
	rm -f $APT_SOURCES

	partsdir="/usr/lib/base-installer.d"
	if [ -d "$partsdir" ]; then
		for script in `ls "$partsdir"/* 2>/dev/null`; do
			base=$(basename $script | sed 's/[0-9]*//')
			if ! db_progress INFO base-installer/progress/$base; then
				db_subst base-installer/progress/fallback SCRIPT "$base"
				db_progress INFO base-installer/progress/fallback
		    	fi

		    	if [ -x "$script" ] ; then
				# be careful to preserve exit code
				if log-output -t base-installer "$script"; then
					:
				else
			    		warning "$script returned error code $?"
				fi
		    	else
				error "Unable to execute $script"
		    	fi
		done
	fi
}

post_install_hooks () {
	# locales will now be installed, so unset
	unset IT_LANG_OVERRIDE

	partsdir="/usr/lib/post-base-installer.d"
	if [ -d "$partsdir" ]; then
		scriptcount=`ls "$partsdir"/* 2>/dev/null | wc -l`
		scriptcur=0
		for script in "$partsdir"/*; do
			base="$(basename "$script" | sed 's/[0-9]*//')"
			if ! db_progress INFO base-installer/progress/$base && \
			   ! db_progress INFO finish-install/progress/$base; then
				db_subst base-installer/progress/fallback SCRIPT "$base"
				db_progress INFO base-installer/progress/fallback
			fi

			if [ -x "$script" ]; then
				# be careful to preserve exit code
				if log-output -t base-installer "$script"; then
					:
				else
					warning "$script returned error code $?"
				fi
			else
				error "Unable to execute $script"
			fi

			scriptcur="$(($scriptcur + 1))"
			update_progress "$scriptcur" "$scriptcount"
		done
	fi
}

get_mirror_info () {
	if [ -f /cdrom/.disk/base_installable ]; then
		if db_get cdrom/codename && [ "$RET" ] ; then
			DISTRIBUTION=$RET
		else
			exit_error base-installer/no_codename
		fi

		PROTOCOL=file
		MIRROR=""
		DIRECTORY="/cdrom/"
		if [ -s /cdrom/.disk/base_components ]; then
			if db_get apt-setup/restricted && [ "$RET" = false ]; then
				COMPONENTS=`grep -v '^#' /cdrom/.disk/base_components | egrep -v '^(restricted|multiverse)$' | tr '\n' , | sed 's/,$//'`
			else
				COMPONENTS=`grep -v '^#' /cdrom/.disk/base_components | tr '\n' , | sed 's/,$//'`
			fi
		else
			COMPONENTS="*"
		fi

		# Sanity check: an error reading /cdrom/.disk/base_components can
		# cause ugly errors in debootstrap because $COMPONENTS will be empty
		if [ -z "$COMPONENTS" ]; then
			exit_error base-installer/cannot_install
		fi
	else
		if db_get mirror/codename && [ "$RET" ] ; then
			DISTRIBUTION=$RET
		else
			exit_error base-installer/no_codename
		fi

		mirror_error=""

		db_get mirror/protocol || mirror_error=1
		PROTOCOL="$RET"

		db_get mirror/$PROTOCOL/hostname || mirror_error=1
		MIRROR="$RET"

		db_get mirror/$PROTOCOL/directory || mirror_error=1
		DIRECTORY="$RET"

		if db_get apt-setup/restricted && [ "$RET" = false ]; then
			COMPONENTS="main"
		else
			COMPONENTS="main,restricted"
		fi

		if [ "$mirror_error" = 1 ] || [ -z "$PROTOCOL" ] || [ -z "$MIRROR" ]; then
			exit_error base-installer/cannot_install
		fi
	fi
}

kernel_update_list () {
	# Use 'uniq' to avoid listing the same kernel more then once
	(set +e;
	# Hack to get the metapackages in the right order; should be
	# replaced by something better at some point.
	chroot /target apt-cache search ^linux- | grep '^linux-\(amd64\|386\|686\|k7\|generic\|server\|virtual\|rt\|xen\|power\|cell\|itanium\|mckinley\|sparc\|hppa\|lpia\)';
	chroot /target apt-cache search ^linux-image- | grep -v '^linux-image-2\.';
	chroot /target apt-cache search ^linux-image-2. | sort -r) | \
	cut -d" " -f1 | uniq > "$KERNEL_LIST.unfiltered"
	kernels=`< "$KERNEL_LIST.unfiltered" tr '\n' ' ' | sed -e 's/ $//'`
	for candidate in $kernels; do
		if [ -n "$FLAVOUR" ]; then
			if arch_check_usable_kernel "$candidate" "$FLAVOUR"; then
				echo "$candidate"
				info "kernel $candidate usable on $FLAVOUR"
			else
				info "kernel $candidate not usable on $FLAVOUR"
			fi
		else
			info "could not determine kernel flavour"
		fi
	done > "$KERNEL_LIST"
}

kernel_present () {
	[ "$1" ] || return 1
	grep -q "^$1\$" $KERNEL_LIST
}

pick_kernel () {
	kernel_update_list

	# Check for overrides
	if db_get base-installer/kernel/override-image && [ "$RET" ]; then
		if kernel_present "$RET"; then
			KERNEL="$RET"
			info "Using kernel '$KERNEL'"
			db_set base-installer/kernel/image "$KERNEL"
			return
		else
			warning "Kernel override '$RET' not present"
		fi
	fi

	# For now, only present kernels we believe to be usable. We may have
	# to rethink this later, but if there are no usable kernels it
	# should be accompanied by an error message. The default must still
	# be usable if possible.
	kernels=`< "$KERNEL_LIST" tr '\n' ',' | sed -e 's/,$//'`

	info "Found kernels '$kernels'"

	if [ "$kernels" ]; then
		db_subst base-installer/kernel/image KERNELS "$kernels"
	else
		db_input high base-installer/kernel/skip-install || true
		db_go || true
		db_get base-installer/kernel/skip-install
		if [ "$RET" != true ]; then
			exit_error base-installer/kernel/no-kernels-found
		else
			db_set base-installer/kernel/image "none"
			KERNEL=none
			return
		fi
	fi

	# Allow for preseeding first, try to determine a default next.
	db_get base-installer/kernel/image
	if kernel_present "$RET" || [ "$RET" = none ]; then
		KERNEL="$RET"
		info "preseeded/current kernel: $KERNEL"
	else
		# Unset seen flag in case we had an incorrect preseeded value.
		db_fset base-installer/kernel/image seen false || true

		if [ -n "$FLAVOUR" ]; then
			arch_kernel="$(arch_get_kernel "$FLAVOUR")"

			# Hack to support selection of meta packages with a postfix
			# added to the normal name (for updated kernels in stable).
			if db_get base-installer/kernel/altmeta && [ "$RET" ]; then
				arch_kernel="$(echo "$arch_kernel" | \
					sed "s/$/-$RET/"; \
					echo "$arch_kernel")"
			fi
		else
			arch_kernel=""
		fi

		got_arch_kernel=
		if [ "$arch_kernel" ]; then
			info "arch_kernel candidates: $arch_kernel"
			# Walk through recommended list for this architecture in order.
			for candidate in $arch_kernel; do
				if kernel_present "$candidate"; then
					info "arch_kernel: $candidate (present)"
					KERNEL="$candidate"
					break
				else
					info "arch_kernel: $candidate (absent)"
				fi
			done
		fi
	fi

	KERNEL_PRIO=high
	if kernel_present "$KERNEL" || [ "$KERNEL" = none ]; then
		# Current selection is available
		KERNEL_PRIO=medium
	else
		# No recommendations available; try to guess.
		kernels="$(echo "$kernels" | sed 's/,/\n/g')"

		# Take the first on the list. kernel_update_list orders the
		# list in such a way that the metapackages always come
		# first, in the right order.
		KERNEL=$(echo "$kernels" | head -n 1)
	fi

	if [ "$KERNEL" ]; then
		db_set base-installer/kernel/image "$KERNEL"
	else
		# We have no reasonable default at all.
		KERNEL_PRIO=critical
	fi

	db_input $KERNEL_PRIO base-installer/kernel/image || [ $? -eq 30 ]
	if ! db_go; then
		db_progress stop
		exit 10
	fi

	db_get base-installer/kernel/image
	KERNEL=$RET
	info "Using kernel '$KERNEL'"
}

install_linux () {
	if [ "$KERNEL" = none ]; then
		info "Not installing any kernel"
		return
	fi

	target_kernel_major="$(echo "$KERNEL" | sed 's/^kernel-image-//; s/^linux-image-//; s/-.*//' | cut -d . -f 1,2)"
	case $target_kernel_major in
		2.?)	;;
		*)
			# something went wrong; use major version of
			# installation kernel
			target_kernel_major="$(uname -r | cut -d . -f 1,2)"
			;;
	esac

	do_initrd=no
	if db_get "base-installer/kernel/linux/initrd-$target_kernel_major"; then
		if [ "$RET" = true ]; then
			do_initrd=yes
		fi
	# Note: this template currently does not exist
	elif db_get base-installer/kernel/linux/initrd; then
		if [ "$RET" = true ]; then
			do_initrd=yes
		fi
	else
		warning "Failed to get debconf answer 'base-installer/kernel/linux/initrd'."
		do_initrd=yes
	fi

	if db_get base-installer/kernel/linux/link_in_boot ; then
		if [ "$RET" = "true" ]; then
			link_in_boot=yes
		else
			link_in_boot=no
		fi
	else
		warning "Failed to get debconf answer 'base-installer/kernel/linux/link_in_boot'."
		link_in_boot=no
	fi

	# Create configuration file for kernel-package
	if [ -f /target/etc/kernel-img.conf ]; then
		# Backup old kernel-img.conf
		mv /target/etc/kernel-img.conf /target/etc/kernel-img.conf.$$
	fi

	info "Setting do_initrd='$do_initrd'."
	info "Setting link_in_boot='$link_in_boot'."
	cat > /target/etc/kernel-img.conf <<EOF
# Kernel image management overrides
# See kernel-img.conf(5) for details
do_symlinks = yes
relative_links = yes
do_bootloader = no
do_bootfloppy = no
do_initrd = $do_initrd
link_in_boot = $link_in_boot
EOF

	# TODO This should probably be restructured to better support
	#      differences between initrd generators
	rd_generator=""
	if [ "$do_initrd" = yes ]; then
		if generators="$(available_initramfs_generators)"; then
			if echo "$generators" | grep -q " "; then
				rd_generator="$(select_initramfs_generator "$generators")"
			else
				rd_generator="$generators"
			fi
		fi

		# initramfs-tools needs busybox-initramfs pre-installed (and
		# only recommends it)
		if [ "$rd_generator" = initramfs-tools ]; then
			if ! log-output -t base-installer apt-install busybox-initramfs; then
				db_subst base-installer/kernel/failed-package-install PACKAGE busybox-initramfs
				exit_error base-installer/kernel/failed-package-install
			fi
		fi

		# Make sure the ramdisk creation tool is installed before we
		# change its configuration
		db_subst base-installer/section/install_kernel_package SUBST0 "$rd_generator"
		db_progress INFO base-installer/section/install_kernel_package
		if ! log-output -t base-installer apt-install "$rd_generator"; then
			db_subst base-installer/kernel/failed-package-install PACKAGE "$rd_generator"
			exit_error base-installer/kernel/failed-package-install
		fi

		# Figure out how to configure the ramdisk creation tool
		# FJP 20070306: Possibly this can go completely
		case "$rd_generator" in
		    initramfs-tools|yaird)
			: ;;
		    *)
			db_subst base-installer/initramfs/unsupported GENERATOR "$rd_generator"
			exit_error base-installer/initramfs/unsupported
			;;
		esac

		# Add modules that have been queued for inclusion in the initrd
		FIRSTMODULE=1
		for QUEUEFILE in /var/lib/register-module/*.initrd; do
			[ ! -e $QUEUEFILE ] && break
			MODULE=$(basename $QUEUEFILE ".initrd")
			addmodule_initramfs_tools "$MODULE" $FIRSTMODULE
			addmodule_yaird "$MODULE" $FIRSTMODULE
			rm $QUEUEFILE
			FIRSTMODULE=0
		done

		# Select and set driver inclusion policy for initramfs-tools
		if [ "$rd_generator" = initramfs-tools ]; then
			if db_get base-installer/initramfs-tools/driver-policy && \
			   [ "$RET" = "" ]; then
				# Get default for architecture
				db_get base-installer/kernel/linux/initramfs-tools/driver-policy
				db_set base-installer/initramfs-tools/driver-policy "$RET"
			fi
			db_input medium base-installer/initramfs-tools/driver-policy || true
			if ! db_go; then
				db_progress stop
				exit 10
			fi

			db_get base-installer/initramfs-tools/driver-policy
			if [ "$RET" != most ]; then
				cat > $IT_CONFDIR/driver-policy <<EOF
# Driver inclusion policy selected during installation
# Note: this setting overrides the value set in the file
# /etc/initramfs-tools/initramfs.conf
MODULES=$RET
EOF
			fi
		fi
	else
		info "Not installing an initrd generator."
	fi

	# Install any extra (kernel related) packages
	EXTRAS=
	if db_get "base-installer/kernel/linux/extra-packages-$target_kernel_major"; then
		EXTRAS="$EXTRAS $RET"
	fi
	if db_get base-installer/kernel/linux/extra-packages; then
		EXTRAS="$EXTRAS $RET"
	fi
	for package in $EXTRAS; do
		info "Installing $package."
		db_subst base-installer/section/install_kernel_package SUBST0 "$package"
		db_progress INFO base-installer/section/install_kernel_package
		# The package might not exist; don't worry about it.
		log-output -t base-installer apt-install "$package" || true
	done

	if [ "$do_initrd" = yes ]; then
		# Set up a default resume partition.
		case $rd_generator in
		    initramfs-tools)
			resumeconf=$IT_CONFDIR/resume
			;;
		    *)
			resumeconf=
			;;
		esac
		resume_devfs="$(get_resume_partition)" || resume_devfs=
		if [ "$resume_devfs" ] && [ -e "$resume_devfs" ]; then
			resume="$(mapdevfs "$resume_devfs")" || resume=
		else
			resume=
		fi
		if [ "$resume" ] && PATH="/lib/udev:$PATH" type vol_id >/dev/null 2>&1; then
			resume_uuid="$(PATH="/lib/udev:$PATH" vol_id -u "$resume" || true)"
			if [ "$resume_uuid" ]; then
				resume="UUID=$resume_uuid"
			fi
		fi
		if [ -n "$resumeconf" ] && [ "$resume" ]; then
			if [ -f $resumeconf ] ; then
				sed -e "s@^#* *RESUME=.*@RESUME=$resume@" < $resumeconf > $resumeconf.new &&
					mv $resumeconf.new $resumeconf
			else
				echo "RESUME=$resume" >> $resumeconf
			fi
		fi

		# Set PReP root partition
		if [ "$ARCH" = powerpc ] && [ "$SUBARCH" = prep ] && \
		   [ "$rd_generator" = initramfs-tools ]; then
			prepconf=$IT_CONFDIR/prep-root
			rootpart_devfs=$(mount | grep "on /target " | cut -d' ' -f1)
			rootpart=$(mapdevfs $rootpart_devfs)
			if [ -f $prepconf ] && grep -q "^#* *ROOT=" $prepconf; then
				sed -e "s@^#* *ROOT=.*@ROOT=$rootpart@" < $prepconf > $prepconf.new &&
					mv $prepconf.new $prepconf
			else
				echo "ROOT=$rootpart" >> $prepconf
			fi
		fi
	fi

	# Advance progress bar to 30% of allocated space for install_linux
	update_progress 30 100

	# Install the kernel
	db_subst base-installer/section/install_kernel_package SUBST0 "$KERNEL"
	db_progress INFO base-installer/section/install_kernel_package
	log-output -t base-installer apt-install "$KERNEL" || kernel_install_failed=$?

	# Advance progress bar to 90% of allocated space for install_linux
	update_progress 90 100

	if [ -f /target/etc/kernel-img.conf.$$ ]; then
		# Revert old kernel-img.conf
		mv /target/etc/kernel-img.conf.$$ /target/etc/kernel-img.conf
	fi

	if [ "$kernel_install_failed" ]; then
		db_subst base-installer/kernel/failed-install KERNEL "$KERNEL"
		exit_error base-installer/kernel/failed-install
	fi
}

get_resume_partition () {
	biggest_size=0
	biggest_partition=
	while read filename type size other; do
		if [ "$type" != partition ]; then
			continue
		fi
		if [ ! -e "$filename" ]; then
			continue
		fi
		if [ "${filename#/dev/ramzswap}" != "$filename" ]; then
			continue
		fi
		if [ "$size" -gt "$biggest_size" ]; then
			biggest_size="$size"
			biggest_partition="$filename"
		fi
	done < /proc/swaps
	echo "$biggest_partition"
}

available_initramfs_generators () {
	irf_list=""
	db_get base-installer/kernel/linux/initramfs-generators || return 1

	for irf in $RET; do
		if LANG=C chroot /target apt-cache policy $irf 2>&1 | \
			grep "Candidate:" | grep -v "(none)" >/dev/null 2>&1; then
			if [ "$irf_list" ]; then
				irf_list="$irf_list $irf"
			else
				irf_list="$irf"
			fi
		fi
	done
	info "Available initramfs generator(s): '$irf_list'"

	[ "$irf_list" ] || return 1
	echo "$irf_list"
	return 0
}

select_initramfs_generator () {
	irf_choices="$(echo "$1" | sed "s/ \+/, /g")"
	irf_default="${1%% *}"
	db_subst base-installer/initramfs/generator GENERATORS "$irf_choices"
	db_set base-installer/initramfs/generator "$irf_default"

	db_input low base-installer/initramfs/generator || [ $? -eq 30 ]
	if ! db_go; then
		db_progress stop
		exit 10
	fi

	db_get base-installer/initramfs/generator
	echo $RET
}

addmodule_easy () {
	if [ -f "$CFILE" ]; then
		if [ "$2" = 1 ]; then
			echo -e "\n# Added by Debian Installer" >>$CFILE
		fi
		echo "$1" >> $CFILE
	fi
}

addmodule_initramfs_tools () {
	CFILE='/target/etc/initramfs-tools/modules'
	addmodule_easy "$1" "$2"
}

addmodule_yaird () {
	CFILE='/target/etc/yaird/Default.cfg'
	if [ -f "$CFILE" ]; then
		if [ "$2" = 1 ]; then
			sed -i "/END GOALS/s/^/\n\t\t#\n\t\t# Added by Debian Installer\n/" $CFILE
		fi
		sed -i "/END GOALS/s/^/\t\tMODULE $1\n/" $CFILE
	fi
}

# Assumes the file protocol is only used for CD (image) installs
configure_apt () {
	if [ "$PROTOCOL" = file ]; then
		rm -f /var/lib/install-cd.id

		# Let apt inside the chroot see the cdrom
		if [ -n "$DIRECTORY" ]; then
			umount /target$DIRECTORY 2>/dev/null || true
			if [ ! -e /target/$DIRECTORY ]; then
				mkdir -p /target/$DIRECTORY
			fi
		fi

		# The bind mount is left mounted, for future apt-install
		# calls to use.
		if ! mount -o bind $DIRECTORY /target$DIRECTORY; then
			warning "failed to bind mount /target$DIRECTORY"
		fi

		# Make apt-cdrom and apt not unmount/mount CD-ROMs;
		# needed to support CD images (hd-media installs).
		# This file will be left in place until the end of the
		# install for hd-media installs, but is removed again
		# during apt-setup for installs using real CD/DVDs.
		cat > $APT_CONFDIR/00NoMountCDROM << EOT
APT::CDROM::NoMount "true";
Acquire::cdrom {
  mount "/cdrom";
  "/cdrom/" {
    Mount  "true";
    UMount "true";
  };
}
EOT

		# Scan CD-ROM or CD image; start with clean sources.list
		# Prevent apt-cdrom from prompting
		: > $APT_SOURCES
		if ! log-output -t base-installer \
		     chroot /target apt-cdrom add </dev/null; then
			error "error while running apt-cdrom"
		fi
		if db_get apt-setup/restricted && [ "$RET" = false ]; then
			sed -i 's/ \(restricted\|multiverse\)//g' $APT_SOURCES
		fi
	else
		# sources.list uses space to separate the components, not comma
		COMPONENTS=$(echo $COMPONENTS | tr , " ")
		APTSOURCE="$PROTOCOL://$MIRROR$DIRECTORY"

		echo "deb $APTSOURCE $DISTRIBUTION $COMPONENTS" > $APT_SOURCES
		echo "deb $APTSOURCE $DISTRIBUTION-updates $COMPONENTS" >> $APT_SOURCES
		if db_get apt-setup/security_host; then
			SECMIRROR="$RET"
		else
			SECMIRROR="$MIRROR"
		fi
		echo "deb $PROTOCOL://$SECMIRROR/ubuntu $DISTRIBUTION-security $COMPONENTS" >> $APT_SOURCES
		if db_get apt-setup/proposed && [ "$RET" = true ]; then
			echo "deb $APTSOURCE $DISTRIBUTION-proposed $COMPONENTS" >> $APT_SOURCES
		fi
	fi
}

cleanup () {
	rm -f "$KERNEL_LIST" "$KERNEL_LIST.unfiltered"
}
