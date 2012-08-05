arch_get_kernel_flavour () {
	case "$SUBARCH" in
	    amiga|atari|mac|bvme6000|mvme147|mvme16x|q40|sun3|sun3x)
		echo "$SUBARCH"
		return 0
		;;
	    *)
		warning "Unknown $ARCH subarchitecture '$SUBARCH'."
		return 1
		;;
	esac
}

arch_check_usable_kernel () {
	# Subarchitecture must match exactly
	if echo "$1" | grep -Eq -- "-$2(-.*)?$"; then return 0; fi
	return 1
}

arch_get_kernel () {
	case "$KERNEL_MAJOR" in
	    2.6|3.*)
		echo "linux-image-$KERNEL_MAJOR-$1"
		;;
	    *)
		warning "Unsupported kernel major '$KERNEL_MAJOR'."
		;;
	esac
}
