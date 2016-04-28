#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cdebconf/debconfclient.h>
#include <debian-installer.h>
#include "netcfg.h"

static char* get_vlan_command(const char* parentif, const char* vlanif, int vlanid) {
#if defined(__linux__)
	const char* vlan_command = "ip link add link %s name %s type vlan id %d";
	int len = strlen(vlan_command) + strlen(parentif) + strlen(vlanif) + 4 + 1;
	char* buf = malloc(len);
	snprintf(buf, len, vlan_command, parentif, vlanif, vlanid);
	return buf;
#elif defined(__FreeBSD_kernel__)
	const char* vlan_command = "ifconfig %s vlan %d vlandev %s";
	int len = strlen(vlan_command) + strlen(parentif) + strlen(vlanif) + 4 + 1;
	char* buf = malloc(len);
	snprintf(buf, len, vlan_command, vlanif, vlanid, parentif);
	return buf;
#endif
}

/* Create a new VLAN interface attached to the currently selected
 * network interface.
 */
int netcfg_set_vlan (struct debconfclient *client, struct netcfg_interface *interface) {
#if defined(__linux__) || defined(__FreeBSD_kernel__)
	int vlanid;

	debconf_get(client, "netcfg/vlan_id");
	/* Empty string: no VLAN preseeded, ask if we should configure VLAN */
	if (strlen(client->value) == 0) {
		debconf_input (client, "medium", "netcfg/use_vlan");
		if (debconf_go(client) == CMD_GOBACK) {
			debconf_fset(client, "netcfg/use_vlan", "seen", "false");
			return GO_BACK;
		}

		debconf_get(client, "netcfg/use_vlan");

		if (!strcmp(client->value, "false")) {
			return 0;
		}

		debconf_input(client, "critical", "netcfg/vlan_id");
		if (debconf_go(client) == CMD_GOBACK) {
			debconf_fset(client, "netcfg/use_vlan", "seen", "false");
			debconf_fset(client, "netcfg/vlan_id", "seen", "false");
			return GO_BACK;
		}
		debconf_get(client, "netcfg/vlan_id");
	}

	for (;;) {
		vlanid = strtol(client->value, NULL, 10);
		/* Valid range: 1-4094 (0 and 4095 are reserved.)
		 * 0 will be returned by strtol if the value cannot be parsed.
		 */
		if (vlanid < 1 || vlanid > 4094) {
			di_error("VLAN ID \"%s\" is invalid.", client->value);
			debconf_fset(client, "netcfg/vlan_failed", "seen", "false");
			debconf_input(client, "critical", "netcfg/vlan_failed");
			debconf_capb(client);
			debconf_go(client);

			debconf_capb(client, "backup");
			debconf_fset(client, "netcfg/vlan_id", "seen", "false");
			debconf_input(client, "critical", "netcfg/vlan_id");
			if (debconf_go(client) == CMD_GOBACK) {
				return GO_BACK;
			}
		} else {
			break;
		}
	}

	int vlaniflen = strlen(interface->name) + 1 + 4 + 1;
	char* vlanif = malloc(vlaniflen);
	snprintf(vlanif, vlaniflen, "%s.%d", interface->name, vlanid);

	char *vlan_command = get_vlan_command(interface->name, vlanif, vlanid);
	int rc = di_exec_shell_log(vlan_command);
	if (rc != 0) {
		di_error("\"%s\" failed to create VLAN interface; return code = %d", vlan_command, rc);
		free(vlan_command);
		debconf_fset(client, "netcfg/vlan_failed", "seen", "false");
		debconf_input(client, "critical", "netcfg/vlan_failed");
		debconf_go(client);
		return GO_BACK;
	}
	free(vlan_command);

	interface->parentif = interface->name;
	interface->name = vlanif;
	interface->vlanid = vlanid;
	di_exec_shell_log("apt-install vlan");
#else
	/* This platform does not support VLANs. */
	debconf_get(client, "netcfg/vlan_id");
	if (strlen(client->value) > 0) {
		di_error("netcfg/vlan_id specified, yet VLAN is not supported on this platfrom");
	}
#endif
	return 0;
}
