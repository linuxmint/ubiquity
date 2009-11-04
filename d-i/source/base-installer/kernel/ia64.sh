arch_get_kernel_flavour () {
	if grep '^features' "$CPUINFO" | grep -q branchlong; then
		echo mckinley
	else
		echo itanium
	fi
	return 0
}

arch_check_usable_kernel () {
	return 0
}

arch_get_kernel () {
	echo "linux-ia64"
	echo "linux-image-ia64"
}
