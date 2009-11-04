/* 
   netcfg.c - Configure a network via DHCP or manual configuration 
   for debian-installer

   Copyright (C) 2000-2002  David Kimdon <dwhedon@debian.org>
                            and others (see debian/copyright)
   
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

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <cdebconf/debconfclient.h>
#include <debian-installer.h>
#ifdef WIRELESS
#include <iwlib.h>
#endif
#include "netcfg.h"

static method_t netcfg_method = DHCP;

response_t netcfg_get_method(struct debconfclient *client)
{
    int iret, ret;
    
    iret = debconf_input(client, "medium", "netcfg/use_dhcp");
    ret = debconf_go(client);
    
    if (ret == 30)
        return GO_BACK;
    
    debconf_get(client, "netcfg/use_dhcp");
    
    if (strcmp(client->value, "true") == 0)
        netcfg_method = DHCP;
    else 
        netcfg_method = STATIC;
    
    if (iret == 30)
        return NOT_ASKED;
    
    return 0;
}

int main(int argc, char *argv[])
{
    int num_interfaces = 0;
    enum { BACKUP,
           GET_INTERFACE,
           GET_HOSTNAME_ONLY,
           GET_METHOD,
           GET_DHCP,
           GET_STATIC,
           WCONFIG,
           WCONFIG_ESSID,
           WCONFIG_WEP,
           QUIT } state = GET_INTERFACE;
    
    static struct debconfclient *client;
    static int requested_wireless_tools = 0;
    char **ifaces;
    char *defiface = NULL, *defwireless = NULL;
    response_t res;
    
    /* initialize libd-i */
    di_system_init("netcfg");
    
    parse_args (argc, argv);
    reap_old_files ();
    open_sockets();
    
    /* initialize debconf */
    client = debconfclient_new();
    debconf_capb(client, "backup");
    
    /* always always always default back to DHCP, unless you've specified
     * disable_dhcp on the command line. */
    debconf_get(client, "netcfg/disable_dhcp");
    
    if (!strcmp(client->value, "true"))
        debconf_set(client, "netcfg/use_dhcp", "false");
    else
        debconf_set(client, "netcfg/use_dhcp", "true");
    
    for (;;) {
        switch(state) {
        case BACKUP:
            return 10;
        case GET_INTERFACE:
            /* Choose a default from ethtool-lite */
            if (get_all_ifs(1, &ifaces) > 1) {
                while (*ifaces) {
                    if (check_kill_switch(*ifaces)) {
                        debconf_subst(client, "netcfg/kill_switch_enabled", "iface", *ifaces);
                        debconf_input(client, "high", "netcfg/kill_switch_enabled");
                        if (debconf_go(client) == 30) {
                            state = BACKUP;
                            break;
                        }
                        /* Is it still enabled? */
                        if (check_kill_switch(*ifaces)) {
                            ifaces++;
                            continue;
                        }
                    }
                    
                    interface_up(*ifaces);
                    
                    usleep(250);
                    
                    if (ethtool_lite (*ifaces) == 1) /* CONNECTED */ {
                        defiface = strdup(*ifaces);
                        interface_down(*ifaces);
                        break;
                    }
#ifdef WIRELESS
                    else {
                        struct wireless_config wc;
                        
                        if (iw_get_basic_config(wfd, *ifaces, &wc) == 0) {
                            wc.essid[0] = '\0';
                            wc.essid_on = 0;
                            
                            iw_set_basic_config(wfd, *ifaces, &wc);
                            
                            sleep(1);
                            
                            iw_get_basic_config(wfd, *ifaces, &wc);
                            
                            if (!empty_str(wc.essid)) {
                                di_info("%s is associated with %s. Selecting as default", *ifaces, wc.essid);
                                defiface = strdup(*ifaces);
                                interface_down(*ifaces);
                                break;
                            } else {
                                di_info("%s is not associated. Relegating to defwireless", *ifaces);
                                if (defwireless != NULL)
                                    free (defwireless);
                                defwireless = strdup(*ifaces);
                            }
                        }
                        else
                            di_info("%s is not a wireless interface. Continuing.", *ifaces);
                        
                        interface_down(*ifaces);
                    }
#endif
                    
                    interface_down(*ifaces);
                    
                    ifaces++;
                }
            }
            
            if (state == BACKUP)
                break;
            
            if (!defiface && defwireless)
                defiface = defwireless;
            
            if(netcfg_get_interface(client, &interface, &num_interfaces, defiface))
                state = BACKUP;
            else if (! interface || ! num_interfaces)
                state = GET_HOSTNAME_ONLY;
            else {
                if (is_wireless_iface (interface))
                    state = WCONFIG;
                else
                    state = GET_METHOD;
            }
            break;
        case GET_HOSTNAME_ONLY:
            if(netcfg_get_hostname(client, "netcfg/get_hostname", &hostname, 0))
                state = BACKUP;
            else {
                struct in_addr null_ipaddress;
                null_ipaddress.s_addr = 0;
                netcfg_write_common(null_ipaddress, hostname, NULL);
                state = QUIT;
            }
            break;
        case GET_METHOD:
            if ((res = netcfg_get_method(client)) == GO_BACK)
                state = (num_interfaces == 1) ? BACKUP : GET_INTERFACE;
            else {
                if (netcfg_method == DHCP) 
                    state = GET_DHCP;
                else
                    state = GET_STATIC;
            }
            break;
            
        case GET_DHCP:
            switch (netcfg_activate_dhcp(client)) {
            case 0:
                state = QUIT;
                break;
            case 10:
                /*
                 * It doesn't make sense to go back to GET_METHOD because
                 * the user has already been asked whether he wants to
                 * try an alternate method.
                 */
                state = (num_interfaces == 1) ? BACKUP : GET_INTERFACE;
                break;
            case 15:
                state = GET_STATIC;
                break;
            default:
                return 1;
            }
            break;
            
        case GET_STATIC:
            {
                int ret;
                /* Misnomer - this should actually take care of activation */
                if ((ret = netcfg_get_static(client)) == 10)
                    state = GET_INTERFACE;
                else if (ret)
                    state = GET_METHOD;
                else
                    state = QUIT;
                break;
            }
        
        case WCONFIG:
            if (requested_wireless_tools == 0) {
                di_exec_shell_log("apt-install wireless-tools");
                requested_wireless_tools = 1;
            }
            state = WCONFIG_ESSID;
            break;
            
        case WCONFIG_ESSID:
            if (netcfg_wireless_set_essid(client, interface, NULL) == GO_BACK)
                state = BACKUP;
            else
                state = WCONFIG_WEP;
            break;
            
        case WCONFIG_WEP:
            if (netcfg_wireless_set_wep(client, interface) == GO_BACK)
                state = WCONFIG_ESSID;
            else
                state = GET_METHOD;
            break;
            
        case QUIT:
            return 0;
        }
    }
}
