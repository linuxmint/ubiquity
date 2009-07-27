#!/bin/sh
set -e
. /usr/share/debconf/confmodule

LOG=/tmp/missing-firmware
DENIED=/tmp/missing-firmware-denied
NL="
"

log () {
	logger -t check-missing-firmware "$@"
}

read_log () {
	# Give modules some time to request firmware.
	sleep 1
	
	modules=""
	files=""
	if [ -s "$LOG" ]; then
		mv $LOG $LOG.old
		OLDIFS="$IFS"
		IFS="$NL"
		for line in $(sort $LOG.old | uniq); do
			module="${line%% *}"
			file="${line#* }"
			[ -z "$module" ] || [ -z "$file" ] && continue

			if grep -q "^$file$" $DENIED 2>/dev/null; then
				continue
			fi

			modules="$module${modules:+ $modules}"
			files="$file${files:+ $files}"
		done
		IFS="$OLDIFS"
		rm -f $LOG.old
	fi

	if [ -n "$modules" ]; then
		log "missing firmware files ($files) for $modules"
		return 0
	else
		log "no missing firmware in $LOG"
		return 1
	fi
}

first=1
ask_load_firmware () {
	db_subst hw-detect/load_firmware FILES "$files"
	if ! db_input high hw-detect/load_firmware; then
		if [ ! "$first" ]; then
			exit 1;
		else
			first=""
		fi
	fi
	if ! db_go; then
		exit 10 # back up
	fi
	db_get hw-detect/load_firmware
	if [ "$RET" = true ]; then
		return 0
	else
		echo "$files" | tr ' ' '\n' >> $DENIED
		return 1
	fi
}

list_deb_firmware () {
	ar p "$1" data.tar.gz | tar zt \
		| grep '^\./lib/firmware/' \
		| sed -e 's!^\./lib/firmware/!!' \
		| grep -v '^$'
}

check_deb_arch () {
	arch=$(ar p "$1" control.tar.gz | tar zxO ./control | grep '^Architecture:' | sed -e 's/Architecture: *//')
	[ "$arch" = all ] || [ "$arch" = "$(udpkg --print-architecture)" ]
}

install_firmware_pkg () {
	if echo "$1" | grep -q '\.deb$'; then
		# cache deb for installation into /target later
		mkdir -p /var/cache/firmware/
		cp -a "$1" /var/cache/firmware/ || true
		udpkg --unpack "/var/cache/firmware/$(basename "$1")"
	else
		udpkg --unpack "$1"
	fi
}

while read_log && ask_load_firmware; do
	# first, look for loose firmware files on the media.
	if mountmedia; then
		for file in $files; do
			for f in "/media/$file" "/media/firmware/$file"; do
				if [ -e "$f" ]; then
					log "copying loose file $file"
					mkdir -p /lib/firmware
					rm -f "/lib/firmware/$file"
					cp -a "$f" /lib/firmware/ || true
					break
				fi
			done
		done
		umount /media || true
	fi

	# Try to load udebs (or debs) that contain the missing firmware.
	# This does not use anna because debs can have arbitrary
	# dependencies, which anna might try to install.
	if mountmedia driver; then
		echo "$files" | sed -e 's/ /\n/g' >/tmp/grepfor
		for filename in /media/*.deb /media/*.udeb /media/*.ude /media/firmware/*.deb /media/firmware/*.udeb /media/firmware/*.ude; do
			if [ -f "$filename" ]; then
				if check_deb_arch "$filename" && list_deb_firmware "$filename" | grep -qf /tmp/grepfor; then
					log "installing firmware package $filename"
					install_firmware_pkg "$filename" || true
				fi
			fi
		done
		rm -f /tmp/grepfor
		umount /media || true
	fi

	# remove and reload modules so they see the new firmware
	for module in $modules; do
		modprobe -r $module || true
		modprobe $module || true
	done
done
