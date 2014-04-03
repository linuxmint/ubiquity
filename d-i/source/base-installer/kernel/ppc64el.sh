arch_get_kernel_flavour () {
	echo generic
	return 0
}

arch_check_usable_kernel () {
	return 0
}

arch_get_kernel () {
	echo "linux-generic"
	echo "linux-image-generic"
}
