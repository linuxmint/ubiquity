arch_get_kernel_flavour () {
        echo "$ARCH"
}

arch_check_usable_kernel () {
	if echo "$1" | grep -Eq -- "-$2(-.*)?$"; then return 0; fi
	return 1
}

arch_get_kernel () {
	echo "linux-image-$KERNEL_MAJOR-$1"
}

