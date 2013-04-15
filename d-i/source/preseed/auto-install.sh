#!/bin/sh

set -e

. /usr/share/debconf/confmodule
. /lib/preseed/preseed.sh

if [ -e /var/run/preseed_unspecified_at_boot ]; then
	if [ -n "$(dhcp_preseed_url)" ]; then
		rm /var/run/preseed_unspecified_at_boot
	else
		db_input critical preseed/url || true
		db_go || true
	fi
fi

# BEGIN: testable
db_get preseed/url && url="$RET"
[ "$url" ] || exit 0

if [ "${url%%://*}" != "$url" ]; then
	proto="${url%%://*}"
	base="${url#*://}"
else
	proto=http
	base="$url"
fi

if ! expr "$base" : [^/]*$ >/dev/null; then
	host_port="${base%%/*}"
	dir="${base#*/}"
else
	host_port="$base"
	db_get auto-install/defaultroot && dir="$RET"
fi

if expr $host_port : [^.]*$ >/dev/null; then
	db_get netcfg/get_domain && domain="$RET"

	if [ -n "$domain" ] && [ "$domain" != "unassigned-domain" ] && [ "$domain" != "unnassigned-domain" ]; then
		host=${host_port%%:*}
		if [ "$host" = "$host_port" ]; then
			port=""
		else
			port=":${host_port#*:}"
		fi

		host_port="$host.$domain$port"

	fi
fi

db_set preseed/url $proto://$host_port/$dir
# END: testable
