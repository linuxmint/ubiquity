arch_get_kernel_flavour () {
	VENDOR=`grep '^vendor_id' "$CPUINFO" | head -n1 | cut -d: -f2`
	case "$VENDOR" in
	    " AuthenticAMD"*)
		echo amd64-k8 ;;
	    " GenuineIntel"*)
		echo em64t-p4 ;;
	    *)
		echo amd64-generic ;;
	esac
	return 0
}

arch_check_usable_kernel () {
	if echo "$1" | grep -Eq -- "-(server|generic|virtual|xen|preempt|rt)(-.*)?$"; then return 0; fi

	return 1
}

arch_get_kernel () {
	if [ "$SUBARCH" = efi ]; then
		echo "linux-signed-generic"
		echo "linux-signed-image-generic"
	fi

	echo "linux-generic"
	echo "linux-image-generic"

	echo "linux-server"
	echo "linux-image-server"

	echo "linux-virtual"
	echo "linux-image-virtual"

	echo "linux-xen"
	echo "linux-image-xen"

	echo "linux-preempt"
	echo "linux-image-preempt"

	echo "linux-rt"
	echo "linux-image-rt"
}
