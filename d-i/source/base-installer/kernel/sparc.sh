arch_get_kernel_flavour () {
	case "$MACHINE" in
		sparc)
			echo sparc32
			log 'sparc32 not supported'
			return 1
		;;
		sparc64)	echo sparc64 ;;
	esac
	return 0
}

arch_check_usable_kernel () {
	if echo "$1" | grep -Eq -- "-sparc64(-.*)?$"; then return 0; fi
	return 1
}

arch_get_kernel () {
	CPUS=`grep 'ncpus probed' "$CPUINFO" | cut -d: -f2`
	TYPE=`grep '^type' "$CPUINFO" | head -n1 | cut -d: -f2 | sed -e 's/^[[:space:]]//'`
	if [ "$CPUS" -ne 1 ] || [ "$TYPE" = "sun4v" ]; then
		echo "linux-$1-smp"
		echo "linux-image-$1-smp"
	fi
	echo "linux-$1"
	echo "linux-image-$1"
}
