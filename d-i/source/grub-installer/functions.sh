# Make sure mtab in the chroot reflects the currently mounted partitions.
update_mtab() {
	[ "$ROOT" ] || return 0

	mtab=$ROOT/etc/mtab
	grep "$ROOT" /proc/mounts | (
	while read devpath mountpoint fstype options n1 n2 ; do
		devpath=`mapdevfs $devpath || echo $devpath`
		mountpoint=`echo $mountpoint | sed "s%^$ROOT%%"`
		# The sed line removes the mount point for root.
		if [ -z "$mountpoint" ] ; then
			mountpoint="/"
		fi
		echo $devpath $mountpoint $fstype $options $n1 $n2
	done ) > $mtab
}

is_floppy () {
	echo "$1" | grep -q '(fd' || echo "$1" | grep -q "/dev/fd" || echo "$1" | grep -q floppy
}
