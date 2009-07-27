#!/bin/sh
#
# Hook into net events so that we can record hotpluggable interfaces for
# netcfg.

log () {
	logger -t net/hw-detect.hotplug "$@"
}

if [ -z "$INTERFACE" ]; then
	log "Got net event without interface"
	exit 1
fi

case $ACTION in
    add|register)
	log "Detected hotpluggable network interface $INTERFACE"
	mkdir -p /etc/network
	echo "$INTERFACE" >>/etc/network/devhotplug
	;;
esac

exit 0
