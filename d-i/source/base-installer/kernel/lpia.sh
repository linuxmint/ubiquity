arch_get_kernel_flavour () {
	echo lpia
	return 0
}

arch_check_usable_kernel () {
	return 0
}

arch_get_kernel () {
	echo "linux-$1"
	echo "linux-image-$1"
}
