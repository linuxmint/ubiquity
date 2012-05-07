#! /bin/sh
set -e

# Detect hardware from Open Firmware's exported device tree, including
# things on the mac-io bus. This is a grab-bag of stuff at the moment; it
# should really move into discover or be hotpluggable.
#
# If the hardware is of use within d-i, then echo it and register-module it;
# otherwise, just use register-module.

for dir in $(find "/proc/device-tree/" -type d); do
	name="$(cat "$dir/name" 2>/dev/null || true)"
	device_type="$(cat "$dir/device_type" 2>/dev/null || true)"
	compatible="$(cat "$dir/compatible" 2>/dev/null || true)"

	# drivers/macintosh
	if [ "$name" = fan ]; then
		case $compatible in
		    adt7460|adt7467)
			# not in d-i yet
			# echo "therm_adt746x:iBook/AlBook G4 ADT746x thermostat"
			register-module therm_adt746x
			;;
		    adm1030)
			# not in d-i yet
			# echo "therm_windtunnel:G4 Windtunnel thermostat"
			register-module therm_windtunnel
			;;
		esac
	# drivers/net
	elif [ "$name" = radio ]; then
		echo "airport:Airport wireless"
		register-module airport
	elif [ "$name" = bmac ] || ([ "$device_type" = network ] && [ "$compatible" = bmac+ ]); then
		echo "bmac:PowerMac BMAC Ethernet"
		register-module bmac
	elif [ "$name" = mace ]; then
		echo "mace:PowerMac MACE Ethernet"
		register-module mace
	# drivers/scsi
	elif [ "$name" = 53c94 ]; then
		echo "mac53c94:PowerMac 53c94 SCSI bus adaptor"
		register-module mac53c94
	elif [ "$name" = mesh ] || ([ "$device_type" = scsi ] && [ "$compatible" = chrp,mesh0 ]); then
		echo "mesh:Macintosh Enhanced SCSI Hardware"
		register-module mesh
	# drivers/ata
	elif [ "$device_type" = ata ] ; then
		case "$compatible" in
		    keylargo-ata)
		        echo "pata_macio:KeyLargo ATA"
		        register-module -i pata_macio
                        ;;
		    heathrow-ata)
		        echo "pata_macio:Heathrow/Paddington ATA"
		        register-module -i pata_macio
                        ;;
		    ohare-ata)
		        echo "pata_macio:OHare ATA"
		        register-module -i pata_macio
		        ;;
		esac
	# sound/ppc, sound/oss/dmasound
	elif [ "$name" = awacs ]; then
		# probably best to go for ALSA
		register-module snd-powermac
	elif [ "$name" = davbus ] || [ "$name" = i2s-a ]; then
		for child in "$dir"/*; do
			if [ -f "$child/name" ]; then
				childname="$(cat "$child/name" 2>/dev/null || true)"
				if [ "$childname" = sound ]; then
					# blacklist snd-aoa modules so snd-powermac is loaded
					register-module -b snd-aoa-codec-tas
					register-module -b snd-aoa-fabric-layout
					register-module -b snd-aoa-i2sbus
					register-module -b snd-aoa-soundbus
					register-module -b snd-aoa
					register-module snd-powermac
				fi
			fi
		done
	elif [ "$name" = via-pmu ]; then
		# APM emulation is useful for some applications, such as the
		# GNOME battery applet.
		register-module apm_emu
	fi
done
