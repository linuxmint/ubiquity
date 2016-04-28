arch_get_kernel_flavour () {
	case "$SUBARCH" in
	    iop32x|kirkwood|orion5x|versatile)
		echo "$SUBARCH"
		return 0 ;;
	    ads)
		# NOTE: this kernel is not in Debian, but makes it
		# easier to offer unofficial support from a private apt-archive
		echo "ads"
		return 0 ;;
	    *)
		warning "Unknown $ARCH subarchitecture '$SUBARCH'."
		return 1 ;;
	esac
}

arch_check_usable_kernel () {
	case "$1" in
	    *-dbg)
		return 1
		;;
	    *-$2|*-$2-*)
		return 0
		;;
	    *)
		return 1
		;;
	esac
}

arch_get_kernel () {
	case "$KERNEL_MAJOR" in
	    2.6|3.*|4.*)
		echo "linux-image-$1"
		;;
	    *)	warning "Unsupported kernel major '$KERNEL_MAJOR'."
		;;
	esac
}
