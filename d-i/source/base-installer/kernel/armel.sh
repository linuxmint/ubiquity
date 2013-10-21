arch_get_kernel_flavour () {
	case "$SUBARCH" in
	    armadaxp|dove|generic-lpae|generic|imx51|omap|omap4|iop32x|iop33x|ixp4xx|kirkwood|orion5x|versatile|mx5)
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
	# Subarchitecture must match exactly
	if echo "$1" | grep -Eq -- "-$2(-.*)?$"; then return 0; fi
	return 1
}

arch_get_kernel () {
	echo "linux-$1"
	echo "linux-image-$1"
}
