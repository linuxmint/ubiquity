arch_get_kernel_flavour () {
	echo "$MACHINE"
	return 0
}

arch_check_usable_kernel () {
	# TODO recent kernels expose os32/os64 in 'capabilities' line in cpuinfo
	if echo "$1" | grep -Eq -- "-(parisc|hppa)(32)?(-.*)?$"; then return 0; fi
	if [ "$2" = parisc ]; then return 1; fi
	if echo "$1" | grep -Eq -- "-(parisc|hppa)(64)?(-.*)?$"; then return 0; fi

	# default to usable in case of strangeness
	warning "Unknown kernel usability: $1 / $2"
	return 0
}

arch_get_kernel () {
	case $1 in
		parisc)		family=hppa32 ;;
		parisc64)	family=hppa64 ;;
	esac

	echo "linux-$family"
	echo "linux-image-$family"
}
