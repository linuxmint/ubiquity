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

	case "$HAVE_LM$HAVE_PAE" in
	    yy)
		echo 686-pae 686-bigmem amd64 486
		return 0
		;;
	    yn)
		warning "Processor with LM but no PAE???"
		;;
	    ny)
		echo 686-pae 686-bigmem 486
		return 0
		;;
	    nn)
		echo 486
		;;
	esac
}

arch_check_usable_kernel () {
	local NAME="$1"

	set -- $2
	while [ $# -ge 1 ]; do
		case "$1:$NAME" in
		    *:*-"$1" | *:*-"$1"-*)
			# Allow any other hyphenated suffix
			return 0
			;;
		    686-*:*-generic | 686-*:*-generic-*)
			return 0
			;;
		    686-*:*-virtual | 686-*:*-virtual-*)
			return 0
			;;
		esac
		shift
	done
	return 1
}

arch_get_kernel () {
	imgbase="linux-image"

	set -- $1
	while [ $# -ge 1 ]; do
		case $1 in
		    686-*)
			echo "linux-generic"
			echo "linux-image-generic"
			echo "linux-virtual"
			echo "linux-image-virtual"
			break
			;;
		esac
		shift
	done
}
