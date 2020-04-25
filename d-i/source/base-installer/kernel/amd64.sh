arch_get_kernel_flavour () {
	echo amd64
}

arch_check_usable_kernel () {
	case "$1" in
		*-unsigned-*|*-18.04|*-18.04-edge|*-oem-osp1|*-oem)
			return 1
			;;
	esac
	if echo "$1" | grep -Eq -- "-(server|generic|oem|lowlatency|virtual|xen|preempt|rt)(-.*)?$"; then return 0; fi

	return 1
}


arch_get_kernel () {

	echo "linux-generic"
	echo "linux-image-generic"

	echo "linux-generic-hwe-20.04"
	echo "linux-image-generic-hwe-20.04"

	echo "linux-lowlatency"
	echo "linux-image-lowlatency"

	echo "linux-lowlatency-hwe-20.04"
	echo "linux-image-lowlatency-hwe-20.04"

	echo "linux-oem-20.04"
	echo "linux-image-oem-20.04"

	echo "linux-virtual"
	echo "linux-image-virtual"
	echo "linux-image-extra-virtual"

	echo "linux-virtual-hwe-20.04"
	echo "linux-image-virtual-hwe-20.04"
	echo "linux-image-extra-virtual-hwe-20.04"
}
