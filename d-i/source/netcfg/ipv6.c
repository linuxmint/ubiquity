/*
 * IPv6-specific functions for netcfg.
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
#include <debian-installer.h>

/* Obsessively watch the network configuration for the given interface,
 * waiting for it to be properly configured.  If the +interface+ struct has
 * an address configured, we'll wait until that address is available,
 * otherwise we're just interested in any global address.
 */
void nc_v6_wait_for_complete_configuration(const struct netcfg_interface *interface)
{
	while (!nc_v6_interface_configured(interface, 0)) {
		usleep(250000);
	}
}

/* Obsessively watch the network configuration for the given interface,
 * waiting for it to have completed configuration of a link-local address.
 */
void nc_v6_wait_for_link_local(const struct netcfg_interface *interface)
{
	while (!nc_v6_interface_configured(interface, 1)) {
		usleep(250000);
	}
}

/* Inspect the live configuration of the given interface, and return a boolean
 * indicating whether it's configuration is complete.  "Complete" is defined
 * as having an IPv6 address properly assigned (ie not "tentative").  If
 * +link_local+ is true, then we'll be satisfied with a link-scope address;
 * if +link_local+ is false, then we require a global scope address.
 *
 * If an IP address is specified in the +interface+ struct, then we require that
 * address to have been configured.
 */
int nc_v6_interface_configured(const struct netcfg_interface *interface, const int link_local)
{
	FILE *cmdfd;
	char l[256];
	char cmd[512];
	int address_found = 0;

	di_debug("nc_v6_interface_configured(%s, scope %s)", interface->name, link_local ? "local" : "global");

#if defined(__FreeBSD_kernel__)
	snprintf(cmd, 512, "ifconfig %s", interface->name);
#else
	snprintf(cmd, 512, "ip addr show %s", interface->name);
#endif
	di_debug("Running %s to look for address", cmd);
	
	if ((cmdfd = popen(cmd, "r")) != NULL) {
		while (fgets(l, 256, cmdfd) != NULL) {
			di_debug("ip line: %s", l);
			/* Aah, string manipulation in C.  What fun. */
#if defined(__FreeBSD_kernel__)
			if (strncmp("\tinet6 ", l, 7)) {
				continue;
			}
			/* An address with a scopeid isn't a global
			 * address, apparently
			 */
			if (!link_local && strstr(l, " scopeid")) {
				continue;
			}
#else
			if (strncmp("    inet6 ", l, 10)) {
				continue;
			}
			if (!link_local && !strstr(l, " scope global")) {
				continue;
			}
#endif
			if (!empty_str(interface->ipaddress)) {
				if (!strstr(l, interface->ipaddress)) {
					continue;
				}
			}
			if (strstr(l, " tentative")) {
				continue;
			}
			
			/* The address is in the interface and not tentative.
			 * Good enough for me.
			 */
			di_debug("Configured address found");
			address_found = 1;
		}

		pclose(cmdfd);
	}

	return address_found;
}

/* Discover if the ManageConfig and/or OtherConfig flags are set in the RAs
 * that we're receiving.
 *
 * Calls out to rdisc6 to get the data we're looking for.  If we get a good
 * response out of rdisc6, we set the v6_stateful_config and v6_stateless_config
 * flags to true/false (1/0) as appropriate and return true.  If ndisc6
 * doesn't give us anything, we set the flags to unknown (-1) and return
 * false.
 *
 * We call out to rdisc6 multiple times, as it seems like it can take a little
 * while for radvd to get into gear.  Yay for progress bars.
 */
int nc_v6_get_config_flags(struct debconfclient *client, struct netcfg_interface *interface)
{
	FILE *cmdfd;
	char l[512], cmd[512];
	const int RDISC6_TRIES = 12;
	int count, ll_ok = 0;
	
	/* First things first... we need to have a link-local address before
	 * we can send/receive RAs... and those can take some time to
	 * appear due to DAD
	 */
	debconf_capb(client, "progresscancel");
	debconf_progress_start(client, 0, RDISC6_TRIES, "netcfg/ipv6_link_local_wait_title");
	
	for (count = 0; count < RDISC6_TRIES; count++) {
		usleep(250000);

		if (debconf_progress_step(client, 1) == 30) {
			/* User cancel */
			break;
		}
		if (nc_v6_interface_configured(interface, 1)) {
			/* We got a useful response */
			debconf_progress_set(client, RDISC6_TRIES);
			ll_ok = 1;
			break;
		}
	}

	debconf_progress_stop(client);
	
	if (!ll_ok) {
		di_info("No IPv6 support found... how does that happen?");
		return 0;
	}
	
	snprintf(cmd, sizeof(cmd), "rdisc6 -1 -r 1 -w 500 -n %s", interface->name);

	di_debug("Running %s to get IPv6 config flags", cmd);
	
	interface->v6_stateful_config = -1;
	interface->v6_stateless_config = -1;
	
	debconf_capb(client, "progresscancel");
	debconf_progress_start(client, 0, RDISC6_TRIES, "netcfg/ipv6_config_flags_wait_title");
	
	for (count = 0; count < RDISC6_TRIES; count++) {
		if ((cmdfd = popen(cmd, "r")) != NULL) {
			while (fgets(l, sizeof(l), cmdfd) != NULL) {
				di_debug("rdisc6 line: %s", l);
				
				if (strncmp("Stateful address conf", l, 21) == 0) {
					di_debug("Got stateful address line");
					/* stateful_config flag */
					if (strstr(l, "    No")) {
						di_debug("stateful=0");
						interface->v6_stateful_config = 0;
					} else if (strstr(l, "    Yes")) {
						di_debug("stateful=1");
						interface->v6_stateful_config = 1;
					}
				} else if (strncmp("Stateful other conf", l, 19) == 0) {
					/* other_config flag */
					if (strstr(l, "    No")) {
						di_debug("stateless=0");
						interface->v6_stateless_config = 0;
					} else if (strstr(l, "    Yes")) {
						di_debug("stateless=1");
						interface->v6_stateless_config = 1;
					}
				}
			}
			di_debug("rdisc6 parsing finished");
			
			pclose(cmdfd);
		}

		if (debconf_progress_step(client, 1) == 30) {
			/* User cancel */
			break;
		}
		if (interface->v6_stateful_config != -1 &&
		    interface->v6_stateless_config != -1) {
			/* We got a useful response */
			debconf_progress_set(client, RDISC6_TRIES);
			break;
		}
	}

	/* In theory managed and other are independent of each other. In
	 * practise both being present means that addresses and configuration
	 * are available via DHCPv6. Hence set stateless_config to 0.
	 * Otherwise the autoconfiguration logic will only spawn a stateless
	 * client.
	 */
	if (interface->v6_stateful_config == 1 &&
	    interface->v6_stateless_config == 1) {
		interface->v6_stateless_config = 0;
	}

	debconf_progress_stop(client);

	if (interface->v6_stateful_config != -1 &&
	    interface->v6_stateless_config != -1) {
		return 1;
	} else {
		return 0;
	}
}
