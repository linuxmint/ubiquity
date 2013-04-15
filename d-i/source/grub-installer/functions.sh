# Make sure mtab in the chroot reflects the currently mounted partitions.
update_mtab_procfs() {
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

# No /proc/mounts available, build one (Hurd)
update_mtab_scratch() {
	echo "$rootfs / $rootfstype defaults 0 1" > $mtab
	if [ "$bootfs" != "$rootfs" ]; then
		echo "$bootfs /boot $bootfstype defaults 0 2" >> $mtab
	fi
}

update_mtab() {
	[ "$ROOT" ] || return 0

	[ ! -h "$ROOT/etc/mtab" ] || return 0

	mtab=$ROOT/etc/mtab

	if [ -e /proc/mounts ]; then
		update_mtab_procfs
	else
		update_mtab_scratch
	fi
}

is_floppy () {
	echo "$1" | grep -q '(fd' || echo "$1" | grep -q "/dev/fd" || echo "$1" | grep -q floppy
}
