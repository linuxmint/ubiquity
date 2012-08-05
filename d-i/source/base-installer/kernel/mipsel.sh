arch_get_kernel_flavour () {
	case "$SUBARCH" in
	    4kc-malta|5kc-malta|loongson-2e|loongson-2f|r3k-kn02|r4k-kn04|sb1-bcm91250a|sb1a-bcm91480b)
		echo "$SUBARCH"
		return 0 ;;
	    qemu-mips32)
		echo "qemu"
		return 0 ;;
	    cobalt)
		echo r5k-cobalt
		return 0 ;;
	    *)
		warning "Unknown $ARCH subarchitecture '$SUBARCH'."
		return 1 ;;
	esac
}

arch_check_usable_kernel () {
	# Subarchitecture must match exactly
	if echo "$1" | grep -Eq -- "-$2(-.*)?$"; then return 0; fi
	# The 4kc-malta kernel will do for 5kc-malta as well
	if [ "$2" = 5kc-malta ] && \
	   echo "$1" | grep -Eq -- "-4kc-malta(-.*)?$"; then
		return 0
	fi
	return 1
}

arch_get_kernel () {
	case "$KERNEL_MAJOR" in
	    2.6|3.*)
		case $1 in
		    5kc-malta)
			echo "linux-image-$KERNEL_MAJOR-$1"
			set 4kc-malta
			;;
		esac
		echo "linux-image-$KERNEL_MAJOR-$1"
		;;
	    *)
		warning "Unsupported kernel major '$KERNEL_MAJOR'."
		;;
	esac
}
