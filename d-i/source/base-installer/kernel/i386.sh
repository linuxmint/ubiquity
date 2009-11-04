arch_get_kernel_flavour () {
	VENDOR=`grep '^vendor_id' "$CPUINFO" | head -n1 | cut -d: -f2`
	FAMILY=`grep '^cpu family' "$CPUINFO" | head -n1 | cut -d: -f2`
	MODEL=`grep '^model[[:space:]]*:' "$CPUINFO" | head -n1 | cut -d: -f2`

	# Only offer bigmem if the system supports PAE and the
	# installer itself is already using a bigmem kernel.
	if grep '^flags' "$CPUINFO" | grep -q pae ; then
	    case "$KERNEL_FLAVOUR" in
		686-bigmem*|generic-pae|xen) BIGMEM="-bigmem" ;;
		*) BIGMEM="-may-bigmem" ;;
	    esac
	fi

	# On systems with 3GB or more of RAM, PAE is needed to access it all.
	if [ "x$BIGMEM" = "x-may-bigmem" ] && \
	   [ "$MEMTOTAL" ] && [ "$MEMTOTAL" -gt 3145728 ]; then
		BIGMEM="-bigmem"
	fi

	case "$VENDOR" in
	    " AuthenticAMD"*)
		case "$FAMILY" in
		    " 15"|" 16"|" 17")			# k8
			echo 686$BIGMEM
			;;
		    " 6")				# k7
			case "$MODEL" in
			    " 0"|" 1"|" 2"|" 3"|" 4"|" 5")
				# May not have SSE support
				echo 586 ;;
			    *)	echo 686$BIGMEM ;;
			esac
			;;
		    " 5")				# k6
			echo 586
			;;
		    *)		echo 486 ;;
		esac
		;;
	    " GenuineIntel")
		case "$FAMILY" in
		    " 6"|" 15")	echo 686$BIGMEM ;;
		    " 5")	echo 586 ;;
		    *)		echo 486 ;;
		esac
		;;
	    " GenuineTMx86"*)
		case "$FAMILY" in
		    " 5"|" 6"|" 15")	echo 586 ;;
		    *)			echo 486 ;;
		esac
		;;
	    " CentaurHauls")
		case "$FAMILY" in
		    " 6")
			case "$MODEL" in
			    " 9"|" 10")	echo 686$BIGMEM ;;
			    *)		echo 586 ;;
			esac
			;;
		    *)
			echo 486 ;;
		esac
		;;
	    *)
		echo 486 ;;
	esac
	return 0
}

# Note: the -k7 flavor has been dropped with linux-2.6 (2.6.23-1)

arch_check_usable_kernel () {
	if echo "$1" | grep -Eq -- "-386(-.*)?$"; then return 0; fi
	if [ "$2" = 486 ]; then return 1; fi
	if echo "$1" | grep -Eq -- "-(generic|virtual|rt)(-.*)?$" && ! echo "$1" | grep -Eq -- "-generic-pae(-.*)?$"; then return 0; fi
	if [ "$2" = 586 ] || [ "$2" = 686 ]; then return 1; fi
	if echo "$1" | grep -Eq -- "-(generic-pae|xen)(-.*)?$"; then return 0; fi
	if [ "$2" = 686-may-bigmem ] || [ "$2" = 686-bigmem ]; then return 1; fi

	# default to usable in case of strangeness
	warning "Unknown kernel usability: $1 / $2"
	return 0
}

arch_get_kernel () {
	imgbase=linux-image

	# See older versions of script for more flexible code structure
	# that allows multiple levels of fallbacks
	if [ "$1" = 686-bigmem ]; then
		echo "linux-generic-pae"
		echo "linux-image-generic-pae"
		echo "linux-xen"
		echo "linux-image-xen"
	fi
	if [ "$1" = 686-bigmem ] || [ "$1" = 686-may-bigmem ] || [ "$1" = 686 ] || [ "$1" = 586 ]; then
		echo "linux-generic"
		echo "linux-image-generic"
		echo "linux-virtual"
		echo "linux-image-virtual"
		echo "linux-rt"
		echo "linux-image-rt"
	fi
	if [ "$1" = 686-may-bigmem ]; then
		echo "linux-generic-pae"
		echo "linux-image-generic-pae"
		echo "linux-xen"
		echo "linux-image-xen"
	fi
	echo "linux-386"
	echo "linux-image-386"
}
