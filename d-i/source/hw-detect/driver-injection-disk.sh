#!/bin/sh
set -e
. /usr/share/debconf/confmodule

log () {
	logger -t driver-injection-disk "$@"
}

check_deb_arch () {
	arch=$(ar p "$1" control.tar.gz | tar zxO ./control | grep '^Architecture:' | sed -e 's/Architecture: *//')
	[ "$arch" = all ] || [ "$arch" = "$(udpkg --print-architecture)" ]
}

lsb_info() {
    [ -f /etc/lsb-release ] || return 0
    grep "^$1=" /etc/lsb-release |\
        sed -e 's/\(.*\)/\1/;s/^[^=]*=//; s/^"//; s/"$//' | tr 'A-Z' 'a-z' || true
}

install_driver_pkg () {
	if echo "$1" | grep -q '\.deb$'; then
		# cache deb for installation into /target later
		mkdir -p /var/cache/firmware/
		cp -a "$1" /var/cache/firmware/ || true
		udpkg --unpack "/var/cache/firmware/$(basename "$1")"
	else
		udpkg --unpack "$1"
	fi
}

#try to mount possible driver disk
for device in $(list-devices usb-partition); do
	label=$(block-attr --label $device 2>/dev/null || true)
	if [ "$label" = "OEMDRV" ]; then
		db_input high driver-injection-disk/load || true
		if ! db_go; then
			exit 10 # back up
		fi
		db_get driver-injection-disk/load
		if [ "$RET" = true ]; then
			if mountmedia driver-injection-disk; then
				dir=/media/$(lsb_info DISTRIB_ID)-drivers/$(lsb_info DISTRIB_CODENAME)
				for filename in $dir/*.deb $dir/*.udeb $dir/*.ude; do
					if [ -f "$filename" ] && check_deb_arch "$filename"; then
						log "installing driver package $filename"
						install_driver_pkg "$filename" || true
					fi
				done
			fi
			umount /media || true
		fi
	fi
done
