arch_has_lpae () {
	if grep -q '^Features.*\blpae\b' "$CPUINFO"; then
		echo y
	else
		echo n
	fi
}

arch_get_kernel_flavour () {
	case "$SUBARCH" in
	    keystone|omap|omap4|mx5|vexpress)
		echo "$SUBARCH armmp"
		return 0 ;;
	    generic)
		case `arch_has_lpae` in
		    y)
			echo "armmp-lpae armmp"
			;;
		    n)
			echo "armmp"
			;;
		esac
		return 0 ;;
	    *)
		warning "Unknown $ARCH subarchitecture '$SUBARCH'."
		return 1 ;;
	esac
}

arch_check_usable_kernel () {
        local NAME="$1"

        set -- $2
        while [ $# -ge 1 ]; do
                TRY="$1"
                case "$TRY:$NAME" in
		    *:*-"$TRY"-lpae | *:*-"$TRY"-lpae-*)
                        # Allow any other hyphenated suffix
			if test `arch_has_lpae` = y ; then
				return 0
			fi
			;;
                    *:*-"$TRY" | *:*-"$TRY"-*)
                        # Allow any other hyphenated suffix
                        return 0
                        ;;
		    armmp-lpae:*-generic-lpae | armmp-lpae:*-generic-lpae-*)
			return 0
			;;
		    armmp:*-generic-lpae | armmp:*-generic-lpae-*)
			# Don't allow -generic-lpae for non-lpae
			;;
		    armmp:*-generic | armmp:*-generic-*)
			return 0
			;;
                esac
                shift
        done
        return 1
}

arch_get_kernel () {
	case "$KERNEL_MAJOR" in
	    2.6|3.*)
		set -- $1
		while [ $# -ge 1 ]; do
			case $1 in
			    armmp)
				echo "linux-generic"
				echo "linux-image-generic"
				;;
			    armmp-lpae)
				echo "linux-generic-lpae"
				echo "linux-image-generic-lpae"
				;;
			    *)
				echo "linux-$1"
				echo "linux-image-$1"
				;;
			esac
			shift
		done
		;;
	    *)	warning "Unsupported kernel major '$KERNEL_MAJOR'."
		;;
	esac
}
