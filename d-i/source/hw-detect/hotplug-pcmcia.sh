#!/bin/sh
#
# hotplug-pcmcia.sh - Handle hotplug events for PCMCIA devices during detection
#

log () {
	logger -t hotplug-pcmcia "$@"
}

TYPE="$1"

case $TYPE in
    net)
	if [ "$INTERFACE" = "" ]; then
		log "Got net event without interface"
		exit 1
	fi

	log "Detected PCMCIA network interface $INTERFACE"
	echo $INTERFACE >>/etc/network/devhotplug
	;;

    # PCI hotplugging is deprecated (2.4 kernels only)
    pci)
	log "PCI event is deprecated."
	exit 1
	;;

    pcmcia_socket)
	log "Got pcmcia_socket event"
	;;
	
    *)
	log "Got unsupported event type \"$TYPE\""
	exit 1
	;;
esac
