/*
 * Functions to write things into /etc/network/interfaces
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
 */

#include "netcfg.h"
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <debian-installer.h>

static int nc_wi_header(FILE *fd)
{
	fprintf(fd, "# This file describes the network interfaces available on your system\n");
	fprintf(fd, "# and how to activate them. For more information, see interfaces(5).\n");
	
	return 1;
}

static int nc_wi_loopback(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "\n# The loopback network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet loopback\n", interface->name);
	
	return 1;
}

static int nc_wi_wireless_options(const struct netcfg_interface *interface, FILE *fd)
{
	/*
	 * Write wireless-tools options
	 */
	/* FIXME: Whether this is a wireless interface should be stored
	 * with the interface
	 */
	if (interface->wpa_supplicant_status == WPA_QUEUED) {
		fprintf(fd, "\twpa-ssid %s\n", interface->essid);
		fprintf(fd, "\twpa-psk  %s\n", interface->passphrase);
	} else {
		fprintf(fd, "\t# wireless-* options are implemented by the wireless-tools package\n");
		fprintf(fd, "\twireless-mode %s\n",
			(interface->mode == MANAGED) ? "managed" : "ad-hoc");
		fprintf(fd, "\twireless-essid %s\n",
		    (interface->essid && *interface->essid) ? interface->essid : "any");

		if (interface->wepkey != NULL)
			fprintf(fd, "\twireless-key1 %s\n", interface->wepkey);
	}

	return 1;
}

/* Write out a DHCP stanza for the given interface
 */
static int nc_wi_dhcp(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "\n# The primary network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet dhcp\n", interface->name);
	if (!empty_str(interface->dhcp_hostname)) {
		fprintf(fd, "\thostname %s\n", interface->dhcp_hostname);
	}

	return 1;
}

/* Write out a SLAAC stanza for the given interface
 */
static int nc_wi_slaac(const struct netcfg_interface *interface, FILE *fd)
{
	if (interface->dhcp == 0)
		fprintf(fd, "\n# The primary network interface\n");
	fprintf(fd, "# This is an autoconfigured IPv6 interface\n");
	if (interface->dhcp == 0) {
		fprintf(fd, "auto %s\n", interface->name);
	}

	fprintf(fd, "iface %s inet6 auto\n", interface->name);
/*	fprintf(fd, "\t# Activate RFC 4941 privacy extensions for outgoing connections. The\n");
	fprintf(fd, "\t# machine will still be reachable via its EUI-64 interface identifier.\n");
	fprintf(fd, "\tprivext 2\n");*/

	return 1;
}

/* Write out a static IPv4 config stanza for the given interface
 */
static int nc_wi_static_ipv4(const struct netcfg_interface *interface, FILE *fd)
{
	char network[INET_ADDRSTRLEN];
	char broadcast[INET_ADDRSTRLEN];
	char netmask[INET_ADDRSTRLEN];

	netcfg_network_address(interface, network);
	netcfg_broadcast_address(interface, broadcast);
	inet_mtop(AF_INET, interface->masklen, netmask, INET_ADDRSTRLEN);

	fprintf(fd, "\n# The primary network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet static\n", interface->name);
	fprintf(fd, "\taddress %s\n", interface->ipaddress);
	fprintf(fd, "\tnetmask %s\n", empty_str(interface->pointopoint) ? netmask : "255.255.255.255");
	fprintf(fd, "\tnetwork %s\n", network);
	fprintf(fd, "\tbroadcast %s\n", broadcast);
	if (!empty_str(interface->gateway))
		fprintf(fd, "\tgateway %s\n",
		        empty_str(interface->pointopoint) ? interface->gateway : interface->pointopoint);
	if (!empty_str(interface->pointopoint))
		fprintf(fd, "\tpointopoint %s\n", interface->pointopoint);

	return 1;
}

/* Write out a static IPv6 config stanza for the given interface
 */
static int nc_wi_static_ipv6(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "\n# The primary network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet6 static\n", interface->name);
	fprintf(fd, "\taddress %s\n", interface->ipaddress);
	fprintf(fd, "\tnetmask %i\n", interface->masklen);
	if (!empty_str(interface->gateway))
		fprintf(fd, "\tgateway %s\n", interface->gateway);

	return 1;
}

/* The main function for writing things to INTERFACES_FILE (aka
 * /etc/network/interfaces).
 *
 * In principle, this function is very simple: just examine the interface
 * we've been passed, and call out to the relevant private helper function. 
 * In practice...
 *
 * Takes the interface struct to write out.  If you pass NULL, the file gets
 * deleted and a helpful comment header gets written.
 *
 * Returns a true/false boolean representing "did everything go OK"; if 0 is
 * returned, the interfaces file will not have been modified, and errno will
 * contain the details.
 */
int netcfg_write_interface(const struct netcfg_interface *interface)
{
	FILE *fd;
	int rv;
	struct stat stat_buf;
	
	if (!interface) {
		di_debug("No interface given; clearing " INTERFACES_FILE);
		rv = unlink(INTERFACES_FILE);
		if (rv < 0 && errno != ENOENT) {
			di_info("Error clearing %s: %s", INTERFACES_FILE, strerror(errno));
			return 0;
		}
	}
	
	fd = file_open(INTERFACES_FILE ".tmp", "w");
	if (!fd) {
		di_warning("Failed to open %s.tmp: %s", INTERFACES_FILE, strerror(errno));
		return 0;
	}

	/* All of this code is to handle the apparently simple task of
	 * copying the existing interfaces file to the tmpfile (if it exists)
	 * so we can add our new stuff to it.  Bloody longwinded way of doing
	 * it, I'm sure you'll agree.
	 */
	rv = stat(INTERFACES_FILE, &stat_buf);
	if (rv < 0 && errno != ENOENT) {
		di_warning("Failed to stat %s: %s", INTERFACES_FILE, strerror(errno));
		unlink(INTERFACES_FILE ".tmp");
		return 0;
	}
	if (rv == 0) {
		char *tmpbuf = malloc(stat_buf.st_size + 1);
		int origfd;
		origfd = open(INTERFACES_FILE, O_RDONLY);
		if (origfd < 0) {
			di_warning("Failed to open %s: %s", INTERFACES_FILE, strerror(errno));
			fclose(fd);
			unlink(INTERFACES_FILE ".tmp");
			free(tmpbuf);
			return 0;
		}
		rv = read(origfd, tmpbuf, stat_buf.st_size);
		if (rv < 0) {
			di_warning("Failed to read %s: %s", INTERFACES_FILE, strerror(errno));
			fclose(fd);
			unlink(INTERFACES_FILE ".tmp");
			free(tmpbuf);
			close(origfd);
			return 0;
		}
		if (rv != stat_buf.st_size) {
			di_warning("Short read on %s", INTERFACES_FILE);
			fclose(fd);
			unlink(INTERFACES_FILE ".tmp");
			free(tmpbuf);
			close(origfd);
			return 0;
		}
		rv = fwrite(tmpbuf, sizeof(char), stat_buf.st_size, fd);
		if (rv != (int)stat_buf.st_size) {
			di_warning("Short write on %s.tmp", INTERFACES_FILE);
			fclose(fd);
			unlink(INTERFACES_FILE ".tmp");
			free(tmpbuf);
			close(origfd);
			return 0;
		}
		free(tmpbuf);
		close(origfd);
	}
		
	
	/* Thank $DEITY all that's out of the way... now we can write a
	 * freaking interfaces file entry */
	rv = 1;

	if (!interface) {
		di_debug("Writing informative header");
		rv = nc_wi_header(fd);
	} else if (interface->loopback == 1) {
		di_debug("Writing loopback interface");
		rv = nc_wi_loopback(interface, fd);
	} else if (interface->dhcp == 1 || interface->slaac == 1) {
		if (interface->dhcp == 1) {
			di_debug("Writing DHCP stanza for %s", interface->name);
			rv = nc_wi_dhcp(interface, fd);
		}
		if (interface->slaac == 1) {
			di_debug("Writing SLAAC stanza for %s", interface->name);
			rv = nc_wi_slaac(interface, fd);
		}
	} else if (interface->address_family == AF_INET) {
		di_debug("Writing static IPv4 stanza for %s", interface->name);
		rv = nc_wi_static_ipv4(interface, fd);
	} else if (interface->address_family == AF_INET6) {
		di_debug("Writing static IPv6 stanza for %s", interface->name);
		rv = nc_wi_static_ipv6(interface, fd);
	}
	
	if (rv && interface && is_wireless_iface(interface->name)) {
		di_debug("Writing wireless options for %s", interface->name);
		rv = nc_wi_wireless_options(interface, fd);
	}

	if (rv) {
		di_debug("Success!");
		rename(INTERFACES_FILE ".tmp", INTERFACES_FILE);
	}

	fclose(fd);
	unlink(INTERFACES_FILE ".tmp");
	return rv;
}
