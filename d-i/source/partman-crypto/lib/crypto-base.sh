. /lib/partman/lib/base.sh
. /lib/partman/lib/commit.sh

# Would this partition be allowed as a physical volume for crypto?
crypto_allowed() {
	local dev=$1
	local id=$2

	# Allow unless this is a crypto device
	[ ! -f "$dev/crypt_realdev" ]
}

crypto_list_allowed() {
	partman_list_allowed crypto_allowed
}

crypto_list_allowed_free() {
	local line

	IFS="$NL"
	for line in $(crypto_list_allowed); do
		restore_ifs
		local dev="${line%%$TAB*}"
		local rest="${line#*$TAB}"
		local id="${rest%%$TAB*}"
		if [ -e "$dev/locked" ] || [ -e "$dev/$id/locked" ]; then
			continue
		fi
		echo "$line"
		IFS="$NL"
	done
	restore_ifs
}

# Prepare a partition for use as a physical volume for encryption. If this
# returns true, then it did some work and a commit is necessary. Prints the
# new path.
crypto_prepare () {
	local dev="$1"
	local id="$2"
	local num size parttype fs path

	cd "$dev"
	open_dialog PARTITION_INFO "$id"
	read_line num id size freetype fs path x7
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
		read_line num id x3 x4 x5 path x7
		close_dialog
	fi

	mkdir -p "$id"
	local method="$(cat "$id/method" 2>/dev/null || true)"
	if [ "$method" = swap ]; then
		disable_swap "$dev" "$id"
	fi
	if [ "$method" != crypto ] && [ "$method" != crypto_keep ]; then
		crypto_prepare_method "$id" dm-crypt || return 1
		rm -f "$id/use_filesystem"
		rm -f "$id/format"
		echo dm-crypt >"$id/crypto_type"
		echo crypto >"$id/method"

		while true; do
			local code=0
			ask_active_partition "$dev" "$id" "$num" || code=$?
			if [ "$code" -ge 128 ] && [ "$code" -lt 192 ]; then
				exit "$code" # killed by signal
			elif [ "$code" -ge 100 ]; then
				break
			fi
		done

		update_partition "$dev" "$id"
		echo "$path"
		return 0
	fi

	echo "$path"
	return 1
}

dm_dev_is_safe() {
	local maj min dminfo deps
	maj="$1"
	min="$2"

	# First try the device itself
	dminfo=$(dmsetup table -j$maj -m$min 2> /dev/null | \
		 head -n1 | sed 's/^[^ ]*: //' | cut -d' ' -f3) || return 1
	if [ "$dminfo" = crypt ]; then
		return 0
	fi

	# Then check its deps instead
	deps=$(dmsetup deps -j "$maj" -m "$min" 2> /dev/null) || return 1
	deps=$(echo "$deps" | sed -e 's/.*://;s/[ (]//g;s/)/ /g')

	# deps is now a list like 3,2 3,1
	for dep in $deps; do
		maj=${dep%%,*}
		min=${dep##*,}
		dm_dev_is_safe "$maj" "$min" || return 1
	done

	return 0
}

dm_is_safe() {
	# Might be non-encrypted, e.g. LVM2
	local dminfo major minor
	type dmsetup > /dev/null 2>&1 || return 1

	dminfo=$(dmsetup info -c "$1" | tail -1) || return 1
	major=$(echo "$dminfo" | sed 's/ \+/ /g' | cut -d' ' -f2)
	minor=$(echo "$dminfo" | sed 's/ \+/ /g' | cut -d' ' -f3)

	dm_dev_is_safe "$major" "$minor" || return 1
	return 0
}

swap_is_safe () {
	local swap
	local IFS="
"

	for swap in $(cat /proc/swaps); do
		case $swap in
		    Filename*)
			continue
			;;
		    /dev/mapper/*)
			dm_is_safe ${swap%% *} || return 1
			;;
		    *)
			# Presume not safe
			return 1
			;;
		esac
	done

	return 0
}

get_free_mapping() {
	for n in 0 1 2 3 4 5 6 7; do
		if [ ! -b "/dev/mapper/crypt$n" ]; then
			echo "crypt$n"
			break
		fi
	done
}

setup_dmcrypt () {
	local mapping device cipher iv hash size pass
	mapping=$1
	device=$2
	cipher=$3
	iv=$4
	hash=$5
	size=$6
	pass=$7

	[ -x /sbin/cryptsetup ] || return 1

	# xts modes needs double the key size
	[ "${iv%xts-*}" = "${iv}" ] || size="$(($size * 2))"

	log-output -t partman-crypto \
	/sbin/cryptsetup -c $cipher-$iv -d $pass -h $hash -s $size create $mapping $device
	if [ $? -ne 0 ]; then
		log "cryptsetup failed"
		return 2
	fi

	return 0
}

setup_luks () {
	local mapping device cipher iv size pass
	mapping=$1
	device=$2
	cipher=$3
	iv=$4
	size=$5
	pass=$6

	[ -x /sbin/cryptsetup ] || return 1

	# xts modes needs double the key size
	[ "${iv%xts-*}" = "${iv}" ] || size="$(($size * 2))"

	log-output -t partman-crypto \
	/sbin/cryptsetup -c $cipher-$iv -s $size luksFormat $device $pass
	if [ $? -ne 0 ]; then
		log "luksFormat failed"
		return 2
	fi

	log-output -t partman-crypto \
	/sbin/cryptsetup -d $pass luksOpen $device $mapping
	if [ $? -ne 0 ]; then
		log "luksOpen failed"
		return 2
	fi

	return 0
}

setup_cryptdev () {
	local type id realdev cryptdev
	type=$1
	id=$2
	realdev=$3

	for opt in keytype cipher keyfile ivalgorithm keyhash keysize; do
		eval local $opt

		if [ -r "$id/$opt" ]; then
			eval $opt=$(cat $id/$opt)
		else
			eval $opt=""
		fi
	done

	case $type in
	    dm-crypt)
		cryptdev=$(mapdevfs $realdev)
		cryptdev="${cryptdev##*/}_crypt"
		if [ -b "/dev/mapper/$cryptdev" ]; then
			cryptdev=$(get_free_mapping)
			if [ -z "$cryptdev" ]; then
				return 1
			fi
		fi
		if [ $keytype = passphrase ]; then
			setup_luks $cryptdev $realdev $cipher $ivalgorithm $keysize $keyfile || return 1
		elif [ $keytype = random ]; then
			setup_dmcrypt $cryptdev $realdev $cipher $ivalgorithm plain $keysize /dev/urandom || return 1
		else
			setup_dmcrypt $cryptdev $realdev $cipher $ivalgorithm $keyhash $keysize $keyfile || return 1
		fi
		cryptdev="/dev/mapper/$cryptdev"
		;;

	esac

	echo $cryptdev > $id/crypt_active
	db_subst partman-crypto/text/in_use DEV "${cryptdev##*/}"
	db_metaget partman-crypto/text/in_use description
	partman_lock_unit $(mapdevfs $realdev) "$RET"
	return 0
}

crypto_do_wipe () {
	local template dev fifo pid x
	template=$1
	dev=$2
	fifo=/var/run/wipe_progress

	mknod $fifo p
	/bin/blockdev-wipe -s 65536 $dev > $fifo &
	pid=$!

	cancelled=0
	db_capb backup align progresscancel
	db_progress START 0 65536 $template
	while read x <&9; do
		db_progress STEP 1
		if [ $? -eq 30 ]; then
			cancelled=1
			kill $pid
			break
		fi
	done 9< $fifo
	db_progress STOP
	db_capb backup align

	rm $fifo
	wait $pid
	ret=$?

	[ $cancelled -eq 1 ] && ret=0
	return $ret
}

crypto_wipe_device () {
	local device method interactive targetdevice
	device=$1
	method=$2
	interactive=$3
	if [ "$interactive" != no ]; then
		interactive=yes
	fi
	ret=1

	if [ $interactive = yes ]; then
		# Confirm before erasing
		template="partman-crypto/warn_erase"
		db_set $template false
		db_subst $template DEVICE $(humandev $device)
		db_input critical $template || true
		db_go || return
		db_get $template
		if [ "$RET" != true ]; then
			return 0
		fi
	fi

	# Setup crypto
	if [ $method = dm-crypt ]; then
		targetdevice=$(get_free_mapping)
		setup_dmcrypt $targetdevice $device aes xts-plain64 plain 128 /dev/urandom || return 1
		targetdevice="/dev/mapper/$targetdevice"
	else
		# Just wipe the device with zeroes
		targetdevice=$device
	fi

	# Erase
	template="partman-crypto/progress/erase"
	db_subst $template DEVICE $(humandev $device)
	if ! crypto_do_wipe $template $targetdevice; then
		template="partman-crypto/erase_failed"
		db_subst $template DEVICE $(humandev $device)
		db_input critical $template || true
		db_go
	else
		ret=0
	fi

	# Teardown crypto
	if [ $method = dm-crypt ]; then
		log-output -t partman-crypto /sbin/cryptsetup remove ${targetdevice##/dev/mapper/}
	fi

	return $ret
}

crypto_dochoice () {
	local part type cipher option value

	part=$1
	type=$2
	cipher=$3
	option=$4

	if [ ! -f /lib/partman/ciphers/$type/$cipher/$option ] && \
	   [ ! -f /lib/partman/ciphers/$type/$option ]; then
		exit 0
	fi

	if [ -f $part/$option ]; then
		value=$(cat $part/$option)
		template="partman-crypto/text/$option/$value"
		db_metaget $template description && value="$RET"
	else
		value="none"
		template=partman-basicfilesystems/text/no_mountpoint
		db_metaget $template description && value="$RET"
	fi

	db_metaget partman-crypto/text/specify_$option description
	printf "%s\t%s\${!TAB}%s\n" "$option" "$RET" "$value"
}

crypto_dooption () {
	local part type cipher option choices altfile template

	part=$1
	type=$2
	cipher=$3
	option=$4

	if [ -f /lib/partman/ciphers/$type/$cipher/$option ]; then
		altfile="/lib/partman/ciphers/$type/$cipher/$option"
	else
		altfile="/lib/partman/ciphers/$type/$option"
	fi

	choices=$(
		for value in $(cat $altfile); do
			description="$value"
			template="partman-crypto/text/$option/$value"
			db_metaget $template description && description="$RET"
			printf "%s\t%s\n" $value "$description"
		done
	)

	template="partman-crypto/$option"
	debconf_select critical $template "$choices" "" || exit 0
	if [ "$RET" = none ]; then
		rm -f $part/$option
		return
	fi

	echo $RET > $part/$option
}

crypto_load_module() {
	local module=$1

	if [ "$module" = dm_mod ]; then
		if dmsetup version >/dev/null 2>&1; then
			return 0
		fi
		modprobe -q $module
		return $?
	elif [ "$module" = dm_crypt ]; then
		if dmsetup targets | cut -d' ' -f1 | grep -q '^crypt$'; then
			return 0
		fi
		modprobe -q $module
		return $?
	else
		if egrep -q "^(name|version) *: $module\$" /proc/crypto; then
			return 0
		fi
		modprobe -q $module
		return $?
	fi
}

# Loads all modules for a given crypto type and cipher
crypto_load_modules() {
	local type cipher moduledir modulefile module
	type=$1
	cipher=$2
	moduledir=/var/run/partman-crypto/modules

	if [ ! -d $moduledir ]; then
		mkdir -p $moduledir
	fi

	for modulefile in \
	  /lib/partman/ciphers/$type/module \
	  /lib/partman/ciphers/$type/$cipher/module; do
		[ -f $modulefile ] || continue
		for module in $(cat $modulefile); do
			if [ -f $moduledir/$module ]; then
				# Already loaded
				continue
			fi

			if crypto_load_module $module; then
				touch $moduledir/$module
			else
				rm -f $moduledir/$module
				return 1
			fi
		done
	done

	return 0
}

# Checks that we have sufficient memory to load crypto udebs
crypto_check_mem() {
	local verbose="$1"

	# A more or less arbitrary limit
	if [ $(memfree) -lt 10000 ]; then
		if [ "$verbose" != true ]; then
			return 1
		fi

		db_set partman-crypto/install_udebs_low_mem false
		db_fset partman-crypto/install_udebs_low_mem seen false
		db_input critical partman-crypto/install_udebs_low_mem
		db_go || true
		db_get partman-crypto/install_udebs_low_mem
		if [ "$RET" != true ]; then
			return 1
		fi
	fi

	return 0
}

# Loads additional crypto udebs
crypto_load_udebs() {
	local packages udebdir package
	packages="$*"
	udebdir=/var/run/partman-crypto/udebs

	if [ -z "$packages" ]; then
		return 0
	fi

	if [ ! -d $udebdir ]; then
		mkdir -p $udebdir
	fi

	local need_depmod=
	for package in $packages; do
		if [ -f $udebdir/$package ]; then
			continue
		fi

		crypto_check_mem true || return 1

		if ! anna-install $package; then
			db_fset partman-crypto/install_udebs_failure seen false
			db_input critical partman-crypto/install_udebs_failure
			db_go || true
			return 1
		fi

		touch $udebdir/$package
		need_depmod=1
	done

	if [ "$need_depmod" ]; then
		# The udeb installation run usually adds new kernel modules
		if [ -x /sbin/depmod ]; then
			depmod -a > /dev/null 2>&1 || true
		fi

		# Reset the capabilities after anna-install
		db_capb backup align
	fi

	return 0
}

# Sets the defaults for a given crypto type
crypto_set_defaults () {
	local part type
	part=$1
	type=$2

	[ -d $part ] || return 1

	case $type in
	    dm-crypt)
		echo aes > $part/cipher
		echo 256 > $part/keysize
		echo xts-plain64 > $part/ivalgorithm
		echo passphrase > $part/keytype
		echo sha256 > $part/keyhash
		;;
	esac
	touch $part/skip_erase
	return 0
}

# Does initial setup for a crypto method
crypto_prepare_method () {
	local part type package
	part=$1
	type=$2
	packages=''

	[ -d $part ] || return 1
	packages="cdebconf-$DEBIAN_FRONTEND-entropy"
	case $type in
	    dm-crypt)
		packages="$packages partman-crypto-dm"
		;;
	    *)
		return 1
		;;
	esac

	# 1A - Pull in the method package and additional dependencies
	crypto_load_udebs $packages || return 1

	# 1B - Verify that it worked
	crypto_check_required_tools $type || return 1

	# 2 - Set the defaults for the chosen type
	crypto_set_defaults $part $type || return 1

	# 3 - Also load the kernel modules needed for the chosen type/cipher
	[ -f $part/cipher ] || return 1
	crypto_load_modules $type $(cat $part/cipher) || return 1

	return 0
}

crypto_check_required_tools() {
	local tools

	tools="blockdev-keygen"
	case $1 in
	    dm-crypt)
		tools="$tools dmsetup cryptsetup"
		;;
	    *)
		return 1
	esac

	for tool in $tools; do
		if ! type $tool > /dev/null 2>&1 ; then
			db_fset partman-crypto/tools_missing seen false
			db_input critical partman-crypto/tools_missing
			db_go || true
			return 1
		fi
	done
	return 0
}

crypto_check_required_options() {
	local id type list options
	path=$1
	type=$2

	case $type in
	    dm-crypt)
		options="cipher keytype keyhash ivalgorithm keysize"
		;;
	esac

	list=""
	for opt in $options; do
		[ -f $path/$opt ] && continue
		db_metaget partman-crypto/text/specify_$opt description || RET="$opt:"
		desc=$RET
		db_metaget partman-crypto/text/missing description || RET="missing"
		value=$RET
		if [ "$list" ]; then
			list="$list
$desc $value"
		else
			list="$desc $value"
		fi
	done

	# If list is non-empty, at least one option is missing
	if [ ! -z "$list" ]; then
		templ="partman-crypto/options_missing"
		db_fset $templ seen false
		db_subst $templ DEVICE "$(humandev $path)"
		db_subst $templ ITEMS "$list"
		db_input critical $templ
		db_go || true
		return 1
	fi
	return 0
}

crypto_check_setup() {
	crypt=
	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev

		partitions=
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			[ "$fs" != free ] || continue
			partitions="$partitions $id"
		done
		close_dialog

		for id in $partitions; do
			[ -f $id/method ] || continue
			[ -f $id/crypto_type ] || continue

			method=$(cat $id/method)
			if [ $method != crypto ] && \
			   [ $method != crypto_keep ]; then
				continue
			fi
			type=$(cat $id/crypto_type)
			crypt=yes

			crypto_check_required_tools $type
			crypto_check_required_options "$dev/$id" $type
		done
	done

	if [ -z "$crypt" ]; then
		db_fset partman-crypto/nothing_to_setup seen false
		db_input critical partman-crypto/nothing_to_setup
		db_go || true
		return 1
	fi
	return 0
}

crypto_setup() {
	local interactive s dev id size path methods partitions type keytype keysize
	interactive=$1
	if [ "$interactive" != no ]; then
		interactive=yes
	fi

	commit_changes partman-crypto/commit_failed || return $?

	if ! swap_is_safe; then
		db_fset partman-crypto/unsafe_swap seen false
		db_input critical partman-crypto/unsafe_swap
		db_go || true
		return 1
	fi

	# Erase crypto-backing partitions
	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev

		partitions=
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			[ "$fs" != free ] || continue
			partitions="$partitions $id,$size,$path"
		done
		close_dialog

		for part in $partitions; do
			set -- $(IFS=, && echo $part)
			id=$1
			size=$2
			path=$3

			[ -f $id/method ] || continue
			method=$(cat $id/method)
			if [ $method != crypto ]; then
				continue
			fi

			if [ -f $id/crypt_active ] || [ -f $id/skip_erase ]; then
				continue
			fi

			if ! crypto_wipe_device $path $(cat $id/crypto_type) $interactive; then
				db_fset partman-crypto/commit_failed seen false
				db_input critical partman-crypto/commit_failed
				db_go || true
				return 1
			fi
		done
	done

	# Create keys and do dmsetup
	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev

		partitions=
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			[ "$fs" != free ] || continue
			partitions="$partitions $id,$path"
		done
		close_dialog

		for part in $partitions; do
			id=${part%,*}
			path=${part#*,}

			[ -f $id/method ] || continue
			[ -f $id/crypto_type ] || continue
			[ -f $id/cipher ] || continue
			[ -f $id/keytype ] || continue

			method=$(cat $id/method)
			if [ $method != crypto ]; then
				continue
			fi

			type=$(cat $id/crypto_type)
			keytype=$(cat $id/keytype)
			cipher=$(cat $id/cipher)

			if [ $keytype = keyfile ] || [ $keytype = passphrase ]; then
				keyfile=$(mapdevfs $path | tr / _)
				keyfile="$dev/$id/${keyfile#_dev_}"

				if [ ! -f $keyfile ]; then
					if ! /bin/blockdev-keygen "$(humandev $path)" "$keytype" "$keyfile"; then
						db_fset partman-crypto/commit_failed seen false
						db_input critical partman-crypto/commit_failed
						db_go || true
						failed=1
						break
					fi
				fi

				echo $keyfile > $id/keyfile
			fi

			if [ ! -f $id/crypt_active ]; then
				log "setting up encrypted device for $path"

				if ! setup_cryptdev $type $id $path; then
					db_fset partman-crypto/commit_failed seen false
					db_input critical partman-crypto/commit_failed
					db_go || true
					failed=1
					break
				fi
			fi
		done
	done

	if [ $failed ]; then
		return 1
	fi

	stop_parted_server

	restart_partman
	return 0
}
