arch_get_kernel_flavour () {
	echo $MACHINE
	return 0
}

arch_check_usable_kernel () {
	if echo "$1" | grep -Eq -- "-(generic|virtual)(-.*)?$"; then return 0; fi

	return 1
}

arch_get_kernel () {
	echo "linux-generic"
	echo "linux-image-generic"

	echo "linux-generic-hwe-22.04"
	echo "linux-image-generic-hwe-22.04"

	echo "linux-virtual"
	echo "linux-image-virtual"
	echo "linux-image-extra-virtual"

	echo "linux-virtual-hwe-22.04"
	echo "linux-image-virtual-hwe-22.04"
	echo "linux-image-extra-virtual-hwe-22.04"
}
