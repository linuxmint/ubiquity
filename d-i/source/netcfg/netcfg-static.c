/*
   netcfg-static.c - Configure a static network for debian-installer

   Copyright (C) 2000-2002  David Kimdon <dwhedon@debian.org>

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 2 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

*/
#include "netcfg.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <cdebconf/debconfclient.h>
#include <debian-installer.h>

int main(int argc, char** argv)
{
    int num_interfaces = 0;
    static struct debconfclient *client;
    static int requested_wireless_tools = 0;
    struct netcfg_interface interface;

    enum { BACKUP, GET_INTERFACE, GET_HOSTNAME_ONLY, GET_STATIC, WCONFIG, WCONFIG_ESSID, WCONFIG_WEP, QUIT} state = GET_INTERFACE;

    /* initialize libd-i */
    di_system_init("netcfg-static");
    if (strcmp(basename(argv[0]), "ptom") != 0)
        di_info("Starting netcfg v.%s (built %s)", NETCFG_VERSION, NETCFG_BUILD_DATE);

    parse_args(argc, argv);
    reap_old_files();
    open_sockets();

    /* initialize debconf */
    client = debconfclient_new();
    debconf_capb(client, "backup");

    while (1) {
        switch(state) {
        case BACKUP:
            return RETURN_TO_MAIN;
        case GET_INTERFACE:
            if (netcfg_get_interface(client, &(interface.name), &num_interfaces, NULL))
                state = BACKUP;
            else if (! interface.name || ! num_interfaces)
                state = GET_HOSTNAME_ONLY;
            else {
                if (is_wireless_iface(interface.name))
                    state = WCONFIG;
                else
                    state = GET_STATIC;
            }
            break;
        case GET_HOSTNAME_ONLY:
            if(netcfg_get_hostname(client, "netcfg/get_hostname", hostname, 0))
                state = BACKUP;
            else {
                netcfg_write_common("", hostname, NULL);
                return 0;
            }
            break;
        case GET_STATIC:
            if (netcfg_get_static(client, &interface))
                state = (num_interfaces == 1) ? BACKUP : GET_INTERFACE;
            else
                state = QUIT;
            break;

        case WCONFIG:
            if (requested_wireless_tools == 0) {
                requested_wireless_tools = 1;
                di_exec_shell("apt-install iw wireless-tools");
            }
            state = WCONFIG_ESSID;
            break;

        case WCONFIG_ESSID:
            if (netcfg_wireless_set_essid (client, &interface))
                state = BACKUP;
            else
                state = WCONFIG_WEP;
            break;

        case WCONFIG_WEP:
            if (netcfg_wireless_set_wep (client, &interface))
                state = WCONFIG_ESSID;
            else
                state = GET_STATIC;
            break;

        case QUIT:
            netcfg_update_entropy();
            return 0;
        }
    }

    return 0;
}
