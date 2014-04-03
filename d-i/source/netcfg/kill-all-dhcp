#!/bin/sh
# Killall for dhcp clients.

for client in dhclient udhcpc pump dhcp6c; do
	pid=$(pidof $client) || true
	[ "$pid" ] || continue

	if kill -0 $pid 2>/dev/null; then
		kill -TERM $pid
		sleep 1
		# Still alive? Die!
		if kill -0 $pid 2>/dev/null; then
			kill -KILL $pid
		fi
	fi
done
