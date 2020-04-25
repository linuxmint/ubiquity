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
#include <cdebconf/debconfclient.h>
#include <debian-installer.h>

static int nc_wi_netplan_header(FILE *fd)
{
	fprintf(fd, "# This file describes the network interfaces available on your system\n");
	fprintf(fd, "# For more information, see netplan(5).\n");
	fprintf(fd, "network:\n");
	fprintf(fd, "  version: 2\n");
	fprintf(fd, "  renderer: networkd\n");

	return 1;
}

static int nc_wi_header(FILE *fd)
{
	fprintf(fd, "# This file describes the network interfaces available on your system\n");
	fprintf(fd, "# and how to activate them. For more information, see interfaces(5).\n");
	fprintf(fd, "\nsource /etc/network/interfaces.d/*\n");
	
	return 1;
}

static int nc_wi_loopback(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "\n# The loopback network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet loopback\n", interface->name);
	
	return 1;
}

/* Write VLAN settings, such as: vlan_raw_device eth0
*/
static int nc_wi_vlan(const struct netcfg_interface *interface, FILE *fd)
{
	int rv;
	rv = 1;
	if (interface && interface->parentif &&
	    (fprintf(fd, "\tvlan_raw_device %s\n", interface->parentif) < 0)) {
		rv = 0;
	}
	return rv;
}

static int nc_wi_netplan_vlan(const struct netcfg_interface *interface, FILE *fd)
{
	int rv;
	rv = 1;

        fprintf(fd, "  vlans:\n");
        fprintf(fd, "    %s:\n", interface->name);
	fprintf(fd, "      link: %s\n", interface->parentif);
	fprintf(fd, "      id: %d\n", interface->vlanid);

	return rv;
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

static int nc_wi_netplan_wireless_aps(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "      access-points:\n");

	if (interface->essid && *interface->essid) {
		fprintf(fd, "        %s:\n", interface->essid);
	} else {
		fprintf(fd, "        any:\n");
	}

	if (interface->wpa_supplicant_status == WPA_QUEUED) {
		fprintf(fd, "          password: %s\n", interface->passphrase);
	} else {
		fprintf(fd, "          mode: %s\n",
			(interface->mode == MANAGED) ? "infrastructure" : "adhoc");

		if (interface->wepkey != NULL)
			fprintf(fd, "          password: %s\n", interface->wepkey);
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

/* Write nameservers for netplan
 */
static int nc_wi_netplan_write_nameservers(const struct netcfg_interface *interface, FILE *fd, const char *domain)
{
	int i;

	if (empty_str(domain) && empty_str(interface->nameservers[0]))
		return 1;

	fprintf(fd, "      nameservers:\n");
	if (!empty_str(domain))
		fprintf(fd, "          search: [ %s ]\n", domain);
	fprintf(fd, "          addresses:\n");
	for (i = 0; i < NETCFG_NAMESERVERS_MAX; i++) {
		if (!empty_str(interface->nameservers[i])) {
			fprintf(fd, "              - \"%s\"\n", interface->nameservers[i]);
		}
	}

	return 1;
}

/* Write out a static IPv4 config stanza for the given interface
 */
static int nc_wi_static_ipv4(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "\n# The primary network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet static\n", interface->name);
	fprintf(fd, "\taddress %s/%i\n", interface->ipaddress,
	        empty_str(interface->pointopoint) ? interface->masklen : 32);
	if (!empty_str(interface->gateway))
		fprintf(fd, "\tgateway %s\n",
		        empty_str(interface->pointopoint) ? interface->gateway : interface->pointopoint);
	if (!empty_str(interface->pointopoint))
		fprintf(fd, "\tpointopoint %s\n", interface->pointopoint);

	return 1;
}

static int nc_wi_netplan_static_ipv4(const struct netcfg_interface *interface, FILE *fd, const char *domain)
{
	fprintf(fd, "      addresses: [ %s/%i ]\n", interface->ipaddress,
	        empty_str(interface->pointopoint) ? interface->masklen : 32);
	if (!empty_str(interface->gateway))
		fprintf(fd, "      gateway4: %s\n",
		        empty_str(interface->pointopoint) ? interface->gateway : interface->pointopoint);

	return nc_wi_netplan_write_nameservers(interface, fd, domain);
}

/* Write out a static IPv6 config stanza for the given interface
 */
static int nc_wi_static_ipv6(const struct netcfg_interface *interface, FILE *fd)
{
	fprintf(fd, "\n# The primary network interface\n");
	fprintf(fd, "auto %s\n", interface->name);
	fprintf(fd, "iface %s inet6 static\n", interface->name);
	fprintf(fd, "\taddress %s/%i\n", interface->ipaddress, interface->masklen);
	if (!empty_str(interface->gateway))
		fprintf(fd, "\tgateway %s\n", interface->gateway);

	return 1;
}

static int nc_wi_netplan_static_ipv6(const struct netcfg_interface *interface, FILE *fd, const char *domain)
{
	fprintf(fd, "      addresses: [ \"%s/%i\" ]\n", interface->ipaddress, interface->masklen);
	if (!empty_str(interface->gateway))
		fprintf(fd, "      gateway6: \"%s\"\n", interface->gateway);

	return nc_wi_netplan_write_nameservers(interface, fd, domain);
}

static int nc_wi_write_eni(const struct netcfg_interface *interface, FILE *fd)
{
	int rv;

        rv = 1;

	di_debug("Using /etc/network/interfaces for network config");

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
	if (rv && interface && interface->parentif) {
		di_debug("Writing VLAN: %s", interface->name);
		rv = nc_wi_vlan(interface, fd);
	}
	if (rv && interface && is_wireless_iface(interface->name)) {
		di_debug("Writing wireless options for %s", interface->name);
		rv = nc_wi_wireless_options(interface, fd);
	}

	return rv;
}

static int nc_wi_write_netplan_yaml(const struct netcfg_interface *interface, FILE *fd, off_t size, const char *domain)
{
	int rv;

        rv = 1;

	di_warning("Using netplan for network config");

	if (size <= 0)
		rv = nc_wi_netplan_header(fd);

	/* No interface given, just clear the file */
	if (!interface)
		return rv;

	/* With netplan, let loopback alone */
	if (interface->loopback == 1)
		return rv;

	if (is_wireless_iface(interface->name)) {
		fprintf(fd, "  wifis:\n");
	} else {
		fprintf(fd, "  ethernets:\n");
	}

	/* Take care of handling VLANs correctly */
	fprintf(fd, "    %s:\n", interface->parentif ? interface->parentif : interface->name);

	if (rv && interface && interface->parentif) {
		/* Make sure our parent doesn't get an IP */
		fprintf(fd, "      dhcp4: no\n");
		fprintf(fd, "      dhcp6: no\n");

		di_debug("Writing VLAN: %s", interface->name);
		rv = nc_wi_netplan_vlan(interface, fd);
	}

	if (interface->dhcp == 1 || interface->slaac == 1) {
		if (interface->dhcp == 1) {
			di_debug("Writing DHCP stanza for %s", interface->name);
			fprintf(fd, "      dhcp4: yes\n");
		}
		if (interface->slaac == 1) {
			di_debug("Writing SLAAC stanza for %s", interface->name);
			fprintf(fd, "      dhcp6: yes\n");
		}

	}

	/* Write all other static addresses */
	if (interface->address_family == AF_INET) {
		di_debug("Writing static IPv4 stanza for %s", interface->name);
		rv = nc_wi_netplan_static_ipv4(interface, fd, domain);
	} else if (interface->address_family == AF_INET6) {
		di_debug("Writing static IPv6 stanza for %s", interface->name);
		rv = nc_wi_netplan_static_ipv6(interface, fd, domain);
	}

	if (rv && interface && is_wireless_iface(interface->name)) {
		di_debug("Writing wireless options for %s", interface->name);
		rv = nc_wi_netplan_wireless_aps(interface, fd);
	}

	return rv;
}

void unlink_config_tmp_file(int use_netplan)
{
	if (use_netplan)
		unlink(NETPLAN_YAML ".tmp");
	else
		unlink(INTERFACES_FILE ".tmp");
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
int netcfg_write_interface(struct debconfclient *client, const struct netcfg_interface *interface, const char *domain)
{
	FILE *fd;
	int rv;
	struct stat stat_buf;
	int use_netplan;
	char *config_file_path;

	use_netplan = 1;

	if (client) {
        	debconf_get(client,"netcfg/do_not_use_netplan");
	}

	/* If this undocumented debconf key is set to true, skip netplan
	 * and fallback to /e/n/i as before.
	 */
	if (!client || !strcmp(client->value, "false")) {
		config_file_path = NETPLAN_YAML;
	} else {
		use_netplan = 0;
		config_file_path = INTERFACES_FILE;
		di_exec_shell_log("apt-install ifupdown");
	}

	di_warning("Using %s", config_file_path);

	if (!interface) {
		di_debug("No interface given; clearing %s", config_file_path);
		rv = unlink(config_file_path);
		if (rv < 0 && errno != ENOENT) {
			di_info("Error clearing %s: %s", config_file_path, strerror(errno));
			return 0;
		}
	}
	
	if (use_netplan)
		fd = file_open(NETPLAN_YAML ".tmp", "w");
	else
		fd = file_open(INTERFACES_FILE ".tmp", "w");

	if (!fd) {
		di_warning("Failed to open %s.tmp: %s", config_file_path, strerror(errno));
		return 0;
	}

	/* All of this code is to handle the apparently simple task of
	 * copying the existing interfaces file to the tmpfile (if it exists)
	 * so we can add our new stuff to it.  Bloody longwinded way of doing
	 * it, I'm sure you'll agree.
	 */
	rv = stat(config_file_path, &stat_buf);
	if (rv < 0 && errno != ENOENT) {
		di_warning("Failed to stat %s: %s", config_file_path, strerror(errno));
		unlink_config_tmp_file(use_netplan);
		return 0;
	}
	if (rv == 0) {
		char *tmpbuf = malloc(stat_buf.st_size + 1);
		int origfd;
		origfd = open(config_file_path, O_RDONLY);
		if (origfd < 0) {
			di_warning("Failed to open %s: %s", config_file_path, strerror(errno));
			fclose(fd);
			unlink_config_tmp_file(use_netplan);
			free(tmpbuf);
			return 0;
		}
		rv = read(origfd, tmpbuf, stat_buf.st_size);
		if (rv < 0) {
			di_warning("Failed to read %s: %s", config_file_path, strerror(errno));
			fclose(fd);
			unlink_config_tmp_file(use_netplan);
			free(tmpbuf);
			close(origfd);
			return 0;
		}
		if (rv != stat_buf.st_size) {
			di_warning("Short read on %s", config_file_path);
			fclose(fd);
			unlink_config_tmp_file(use_netplan);
			free(tmpbuf);
			close(origfd);
			return 0;
		}
		rv = fwrite(tmpbuf, sizeof(char), stat_buf.st_size, fd);
		if (rv != (int)stat_buf.st_size) {
			di_warning("Short write on %s.tmp", config_file_path);
			fclose(fd);
			unlink_config_tmp_file(use_netplan);
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

	if (use_netplan) {
		rv = nc_wi_write_netplan_yaml(interface, fd, stat_buf.st_size, domain);
	} else {
		rv = nc_wi_write_eni(interface, fd);
	}

	if (rv)
		di_debug("Success!");

	if (use_netplan)
		rename(NETPLAN_YAML ".tmp", NETPLAN_YAML);
	else
		rename(INTERFACES_FILE ".tmp", INTERFACES_FILE);

	fclose(fd);

	unlink_config_tmp_file(use_netplan);

	return rv;
}
