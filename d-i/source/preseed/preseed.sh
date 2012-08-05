#!/bin/sh

logfile=/var/lib/preseed/log

log () {
	logger -t preseed "$@"
}

error () {
	error="$1"
	location="$2"
	db_subst preseed/$error LOCATION "$location"
	db_input critical preseed/$error || true
	db_go || true
	exit 1
}

# Function to implement the behaviour documented in README.preseed_fetch
make_absolute_url() {
	url="$1"
	last="$2"

	if [ -n "${url##*://*}" ]; then
		# url does not contain ://
		if [ -z "${url##/*}" ]; then
			# url starts with /
			if [ -z "${last##*/./*}" ]; then
				# if last has a /./, start the "root" there
				url="${last%%/./*}/.$url"
			else
				# if not, strip the path component of $last
				url="$(expr $last : '\([^:]*://[^/]*/\)')$url"
			fi
		else
			# for relative urls, just replace the old filename
			url="${last%/*}/$url"
		fi
	fi
	echo "$url"
}

preseed_location () {
	local location="$1"
	local checksum="$2"
	
	local tmp=/tmp/debconf-seed
	
	if ! preseed_fetch "$location" "$tmp"; then
		error retrieve_error "$location"
	fi
	if [ -n "$checksum" ] && \
	   [ "$(md5sum $tmp | cut -d' ' -f1)" != "$checksum" ]; then
		error retrieve_error "$location"
	fi

	db_set preseed/include ""
	db_set preseed/include_command ""
	db_set preseed/run ""
	UNSEEN=
	db_get preseed/interactive
	if [ "$RET" = true ]; then
		UNSEEN=--unseen
	fi
	if ! debconf-set-selections $UNSEEN $tmp; then
		error load_error "$location"
	fi
	rm -f $tmp

	log "successfully loaded preseed file from $location"
	[ -e /var/run/delay_choosers ] && rm /var/run/delay_choosers
	local last_location="$location"
	
	while true ; do
		db_get preseed/include
		local include="$RET"
		db_get preseed/include_command
		if [ -n "$RET" ]; then
			include="$include $(eval $RET)" || true # TODO error handling?
		fi
		if db_get preseed/include/checksum; then
			checksum="$RET"
		else
			checksum=""
		fi
		db_get preseed/run
		local torun="$RET"

		# not really sure if the ones above are required if this is here
		db_set preseed/include ""
		db_set preseed/include_command ""
		db_set preseed/run ""

		[ -n "$include" -o -n "$torun" ] || break

		for location in $include; do
			sum="${checksum%% *}"
			checksum="${checksum#$sum }"

			location=$(make_absolute_url "$location" "$last_location")
			# BTW -- is this test for empty strings really needed?
			if [ -n "$location" ]; then
				preseed_location "$location" "$sum"
			fi
		done
	
		echo $last_location > /var/run/preseed.last_location

		for location in $torun; do
			location=$(make_absolute_url "$location" "$last_location")
			# BTW -- is this test for empty strings really needed?
			if [ -n "$location" ]; then
				if ! preseed_fetch "$location" "$tmp"; then
					log "error fetching \"$location\""
					error retrieve_error "$location"
				fi
				chmod +x $tmp
				if ! log-output -t preseed/run $tmp; then
					log "error running \"$location\""
					error load_error "$location"
				fi
				log "successfully ran \"$location\""
				rm -f $tmp
			fi
		done
	done
}
	
preseed () {
	template="$1"

	db_get $template
	location="$RET"
	if db_get $template/checksum; then
		checksum="$RET"
	else
		checksum=""
	fi
	for loc in $location; do
		sum="${checksum%% *}"
		checksum="${checksum#$sum }"
		
		preseed_location "$loc" "$sum"
	done
}

# Check for DHCP filename preseeding
dhcp_preseed_url () {
	for file in /var/lib/dhcp/dhclient.leases /var/lib/dhcp3/dhclient.leases /var/lib/udhcp/udhcpc.leases; do
		if [ -r "$file" ]; then
			FN="$(sed -n -e '/ filename "/ s/.*"\(.*\)"./\1/p' $file | tail -n1)"
			if echo "$FN" | grep -q "://" ; then
				echo "$FN"
			fi
		fi
	done
}
