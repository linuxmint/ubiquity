arch_get_kernel_flavour () {
	# Should we offer an amd64 kernel?
	local HAVE_LM
	if grep -q '^flags.*\blm\b' "$CPUINFO"; then
		HAVE_LM=y
	else
		HAVE_LM=n
	fi

	# Should we offer a PAE kernel?
	local HAVE_PAE
	if grep -q '^flags.*\bpae\b' "$CPUINFO"; then
		HAVE_PAE=y
	else
		HAVE_PAE=n
	fi

	# Should we prefer a PAE/amd64 kernel - is there RAM above 4GB?
	local WANT_PAE
	if [ -z "$RAM_END" ]; then
		local MAP MAP_END
		RAM_END=0
		for MAP in /sys/firmware/memmap/* ; do
			if [ "$(cat $MAP/type)" = "System RAM" ]; then
				MAP_END="$(cat $MAP/end)"
				if [ $(($MAP_END > $RAM_END)) = 1 ]; then
					RAM_END=$MAP_END
				fi
			fi
		done
	fi
	if [ $(($RAM_END > 0x100000000)) = 1 ]; then
		WANT_PAE=y
	else
		WANT_PAE=n
	fi
	# or is the installer running a PAE kernel?
	case "$KERNEL_FLAVOUR" in
	    686-bigmem* | 686-pae* | generic-pae | xen)
		WANT_PAE=y
		;;
	esac

	case "$HAVE_LM$HAVE_PAE$WANT_PAE" in
	    yyy)
		echo 686-pae 686-bigmem amd64 686 486
		return 0
		;;
	    yyn)
		echo 686 686-pae 686-bigmem amd64 486
		return 0
		;;
	    yn?)
		warning "Processor with LM but no PAE???"
		;;
	    nyy)
		echo 686-pae 686-bigmem 686 486
		return 0
		;;
	    nyn)
		echo 686 686-pae 686-bigmem 486
		return 0
		;;
	    nn?)
		# Need to check whether 686 is suitable
		;;
	esac

	# Should we offer a 686 kernel?
	if grep -q '^flags.*\bfpu\b.*\btsc\b.*\bcx8\b.*\bcmov\b' "$CPUINFO"; then
		echo 686 486
	else
		echo 486
	fi
}

arch_check_usable_kernel () {
	local NAME="$1"

	set -- $2
	while [ $# -ge 1 ]; do
		case "$1:$NAME" in
		    *:*-"$1")
			return 0;
			;;
		    *:*-"$1"-bigmem* | *:*-"$1"-pae*)
			# Don't allow -bigmem or -pae suffix, as these
			# require extra CPU features
			;;
		    *:*-"$1"-*)
			# Do allow any other hyphenated suffix
			return 0
			;;
		    686-pae:*-generic-pae | 686-pae:*-generic-pae-*)
			return 0
			;;
		    *:*-generic-pae | *:*-generic-pae-*)
			# Don't allow -generic-pae for non-pae
			;;
		    686*:*-generic | 686*:*-generic-*)
			return 0
			;;
		    686*:*-virtual | 686*:*-virtual-*)
			return 0
			;;
		    686*:*-rt | 686*:*-rt-*)
			return 0
			;;
		    686-pae:*-xen | 686-pae:*-xen-*)
			return 0
			;;
		esac
		shift
	done
	return 1
}

arch_get_kernel () {
	imgbase="linux-image-$KERNEL_MAJOR"

	set -- $1
	while [ $# -ge 1 ]; do
		case $1 in
		    686-pae)
			echo "linux-generic-pae"
			echo "linux-image-generic-pae"
			echo "linux-xen"
			echo "linux-image-xen"
			;;
		    686)
			echo "linux-generic"
			echo "linux-image-generic"
			echo "linux-virtual"
			echo "linux-image-virtual"
			echo "linux-rt"
			echo "linux-image-rt"
			;;
		esac
		shift
	done
}
