/* Static network configurator module for netcfg.
 *
 * Licensed under the terms of the GNU General Public License
 */

#include "netcfg.h"
#include <stdlib.h>
#include <string.h>
#include <arpa/inet.h>
#include <debian-installer.h>
#include <assert.h>

struct in_addr old_ipaddress = { 0 };
struct in_addr network = { 0 };
struct in_addr broadcast = { 0 };
struct in_addr netmask = { 0 };
struct in_addr pointopoint = { 0 };

int netcfg_get_ipaddress(struct debconfclient *client)
{
    int ret, ok = 0;
    
    old_ipaddress = ipaddress;
    
    while (!ok) {
        debconf_input (client, "critical", "netcfg/get_ipaddress");
        ret = debconf_go (client);
        
        if (ret)
            return ret;
        
        debconf_get(client, "netcfg/get_ipaddress");
        ok = inet_pton (AF_INET, client->value, &ipaddress);
        
        if (!ok) {
            debconf_capb(client);
            debconf_input (client, "critical", "netcfg/bad_ipaddress");
            debconf_capb(client, "backup");
            debconf_go (client);
        }
    }
    
    return 0;
}

int netcfg_get_pointopoint(struct debconfclient *client)
{
    int ret, ok = 0;
    
    while (!ok) {
        debconf_input(client, "critical", "netcfg/get_pointopoint");
        ret = debconf_go(client);
        
        if (ret)
            return ret;
        
        debconf_get(client, "netcfg/get_pointopoint");
        
      if (empty_str(client->value)) {           /* No P-P is ok */
          memset(&pointopoint, 0, sizeof(struct in_addr));
          return 0;
      }
      
      ok = inet_pton (AF_INET, client->value, &pointopoint);
      
      if (!ok) {
          debconf_capb(client);
          debconf_input (client, "critical", "netcfg/bad_ipaddress");
          debconf_go (client);
          debconf_capb(client, "backup");
      }
    }
    
    inet_pton (AF_INET, "255.255.255.255", &netmask);
    network = ipaddress;
    gateway = pointopoint;
    
    return 0;
}

int netcfg_get_netmask(struct debconfclient *client)
{
    int ret, ok = 0;
    char ptr1[INET_ADDRSTRLEN];
    struct in_addr old_netmask = netmask;
    
    while (!ok) {
        debconf_input (client, "critical", "netcfg/get_netmask");
        ret = debconf_go(client);
        
        if (ret)
            return ret;
        
        debconf_get (client, "netcfg/get_netmask");
        
        ok = inet_pton (AF_INET, client->value, &netmask);
        
        if (!ok) {
            debconf_capb(client);
            debconf_input (client, "critical", "netcfg/bad_ipaddress");
            debconf_go (client);
            debconf_capb(client, "backup");
        }
    }
    
    if (ipaddress.s_addr != old_ipaddress.s_addr ||
        netmask.s_addr != old_netmask.s_addr
        ) {
        network.s_addr = ipaddress.s_addr & netmask.s_addr;
        broadcast.s_addr = (network.s_addr | ~netmask.s_addr);
        
        /* Preseed gateway */
        gateway.s_addr = ipaddress.s_addr & netmask.s_addr;
        gateway.s_addr |= htonl(1);
    }
    
    inet_ntop (AF_INET, &gateway, ptr1, sizeof (ptr1));
    
    /* if you entered a .1 ip, you'll get a .1 back, so makes sense
     * to clear the last bit */
    if (gateway.s_addr == ipaddress.s_addr) {
        char* ptr = strrchr(ptr1, '.');
        assert (ptr); /* if there's no dot in ptr1 we're in deep shit */
        ptr[1] = '\0';
    }
    
    debconf_get(client, "netcfg/get_gateway");
    if (empty_str(client->value))
        debconf_set(client, "netcfg/get_gateway", ptr1);
    
    return 0;
}

int netcfg_get_gateway(struct debconfclient *client)
{
    int ret, ok = 0;
    char *ptr;
    
    while (!ok) {
        debconf_input (client, "critical", "netcfg/get_gateway");
        ret = debconf_go(client);
        
        if (ret)  
            return ret;
        
        debconf_get(client, "netcfg/get_gateway");
        ptr = client->value;
        
        if (empty_str(ptr) || /* No gateway, that's fine */
            (strcmp(ptr, "none") == 0)) /* special case for preseeding */ {
            /* clear existing gateway setting */
            memset(&gateway, 0, sizeof(struct in_addr));
            return 0;
        }
        
        ok = inet_pton (AF_INET, ptr, &gateway);
        
        if (!ok) {
            debconf_capb(client);
            debconf_input (client, "critical", "netcfg/bad_ipaddress");
            debconf_go (client);
            debconf_capb(client, "backup");
        }
    }
    
    return 0;
}

static int netcfg_write_static(char *domain, struct in_addr nameservers[])
{
    char ptr1[INET_ADDRSTRLEN];
    FILE *fp;
    
    if ((fp = file_open(NETWORKS_FILE, "w"))) {
        fprintf(fp, "default\t\t0.0.0.0\n");
        fprintf(fp, "loopback\t127.0.0.0\n");
        fprintf(fp, "link-local\t169.254.0.0\n");
        fprintf(fp, "localnet\t%s\n", inet_ntop (AF_INET, &network, ptr1, sizeof (ptr1)));
        fclose(fp);
    } else
        goto error;
    
    if ((fp = file_open(INTERFACES_FILE, "a"))) {
        fprintf(fp, "\n# The primary network interface\n");
        fprintf(fp, "auto %s\n", interface);
        fprintf(fp, "iface %s inet static\n", interface);
        fprintf(fp, "\taddress %s\n", inet_ntop (AF_INET, &ipaddress, ptr1, sizeof (ptr1)));
        fprintf(fp, "\tnetmask %s\n", inet_ntop (AF_INET, &netmask, ptr1, sizeof (ptr1)));
        fprintf(fp, "\tnetwork %s\n", inet_ntop (AF_INET, &network, ptr1, sizeof (ptr1)));
        fprintf(fp, "\tbroadcast %s\n", inet_ntop (AF_INET, &broadcast, ptr1, sizeof (ptr1)));
        if (gateway.s_addr)
            fprintf(fp, "\tgateway %s\n", inet_ntop (AF_INET, &gateway, ptr1, sizeof (ptr1)));
        if (pointopoint.s_addr)
            fprintf(fp, "\tpointopoint %s\n", inet_ntop (AF_INET, &pointopoint, ptr1, sizeof (ptr1)));
        /*
         * Write wireless-tools options
         */
        if (is_wireless_iface(interface)) {
            fprintf(fp, "\t# wireless-* options are implemented by the wireless-tools package\n");
            fprintf(fp, "\twireless-mode %s\n",
                    (mode == MANAGED) ? "managed" : "ad-hoc");
            fprintf(fp, "\twireless-essid %s\n",
                    (essid && *essid) ? essid : "any");
            
            if (wepkey != NULL)
                fprintf(fp, "\twireless-key1 %s\n", wepkey);
        }
        /*
         * Write resolvconf options
         *
         * This is useful for users who intend to install resolvconf
         * after the initial installation.
         *
         * This code should be kept in sync with the code that writes
         * this information to the /etc/resolv.conf file.  If netcfg
         * becomes capable of configuring multiple network interfaces
         * then the user should be asked for dns information on a
         * per-interface basis so that per-interface dns options
         * can be written here.
         */
        if (nameservers[0].s_addr || (domain && !empty_str(domain))) {
            int i = 0;
            fprintf(fp, "\t# dns-* options are implemented by the resolvconf package, if installed\n");
            if (nameservers[0].s_addr) {
                fprintf(fp, "\tdns-nameservers");
                while (nameservers[i].s_addr)
                    fprintf(fp, " %s",
                            inet_ntop (AF_INET, &nameservers[i++], ptr1, sizeof (ptr1)));
                fprintf(fp, "\n");
            }
            if (domain && !empty_str(domain))
                fprintf(fp, "\tdns-search %s\n", domain);
        }
        fclose(fp);
    } else
        goto error;
    
    if (netcfg_write_resolv(domain, nameservers))
        goto error;
    
    return 0;
error:
    return -1;
}

int netcfg_write_resolv (char* domain, struct in_addr* nameservers)
{
    FILE* fp = NULL;
    char ptr1[INET_ADDRSTRLEN];
    
    if ((fp = file_open(RESOLV_FILE, "w"))) {
        int i = 0;
        if (domain && !empty_str(domain))
            fprintf(fp, "search %s\n", domain);
        
        while (nameservers[i].s_addr)
            fprintf(fp, "nameserver %s\n",
                    inet_ntop (AF_INET, &nameservers[i++], ptr1, sizeof (ptr1)));
        
        fclose(fp);
        return 0;
    }
    else
        return 1;
}

int netcfg_activate_static(struct debconfclient *client)
{
    int rv = 0, masksize;
    char buf[256];
    char ptr1[INET_ADDRSTRLEN];
    
#ifdef __GNU__
    /* I had to do something like this ? */
    /*  di_exec_shell_log ("settrans /servers/socket/2 -fg");  */
    di_exec_shell_log("settrans /servers/socket/2 --goaway");
    snprintf(buf, sizeof(buf),
             "settrans -fg /servers/socket/2 /hurd/pfinet --interface=%s --address=%s",
             interface, inet_ntop (AF_INET, &ipaddress));
    di_snprintfcat(buf, sizeof(buf), " --netmask=%s",
                   inet_ntop (AF_INET, &netmask, ptr1, sizeof (ptr1)));
    buf[sizeof(buf) - 1] = '\0';
    
    if (gateway)
        snprintf(buf, sizeof(buf), " --gateway=%s",
                 inet_ntop (AF_INET, &gateway, ptr1, sizeof (ptr1)));
    
    rv |= di_exec_shell_log(buf);
    
#else
    deconfigure_network();
    
    loop_setup();
    interface_up(interface);
    
    /* Flush all previous addresses, routes */
    snprintf(buf, sizeof(buf), "ip addr flush dev %s", interface);
    rv |= di_exec_shell_log(buf);
    
    snprintf(buf, sizeof(buf), "ip route flush dev %s", interface);
    rv |= di_exec_shell_log(buf);
    
    rv |= !inet_ptom (NULL, &masksize, &netmask);
    
    /* Add the new IP address, P-t-P peer (if necessary) and netmask */
    snprintf(buf, sizeof(buf), "ip addr add %s/%d ",
             inet_ntop (AF_INET, &ipaddress, ptr1, sizeof (ptr1)),
             masksize);
    
    /* avoid using a second buffer */
    di_snprintfcat(buf, sizeof(buf), "broadcast %s dev %s",
                   inet_ntop (AF_INET, &broadcast, ptr1, sizeof (ptr1)),
                   interface);
    
    if (pointopoint.s_addr)
        di_snprintfcat(buf, sizeof(buf), " peer %s",
                       inet_ntop (AF_INET, &pointopoint, ptr1, sizeof (ptr1)));
    
    di_info("executing: %s", buf);
    rv |= di_exec_shell_log(buf);
    
    if (pointopoint.s_addr)
    {
        snprintf(buf, sizeof(buf), "ip route add default dev %s", interface);
        rv |= di_exec_shell_log(buf);
    }
    else if (gateway.s_addr) {
        snprintf(buf, sizeof(buf), "ip route add default via %s",
                 inet_ntop (AF_INET, &gateway, ptr1, sizeof (ptr1)));
        rv |= di_exec_shell_log(buf);
    }
#endif
    
    if (rv != 0) {
        debconf_capb(client);
        debconf_input(client, "high", "netcfg/error");
        debconf_go(client);
        debconf_capb(client, "backup");
        return -1;
    }
    
    return 0;
}

int netcfg_get_static(struct debconfclient *client) 
{
    char *nameservers = NULL;
    char ptr1[INET_ADDRSTRLEN];
    char *none;
    
    enum { BACKUP, GET_HOSTNAME, GET_IPADDRESS, GET_POINTOPOINT, GET_NETMASK,
           GET_GATEWAY, GATEWAY_UNREACHABLE, GET_NAMESERVERS, CONFIRM,
           GET_DOMAIN, QUIT }
    state = GET_IPADDRESS;
    
    ipaddress.s_addr = network.s_addr = broadcast.s_addr = netmask.s_addr = gateway.s_addr = pointopoint.s_addr =
        0;
    
    debconf_metaget(client,  "netcfg/internal-none", "description");
    none = client->value ? strdup(client->value) : strdup("<none>");
    
    for (;;) {
        switch (state) {
        case BACKUP:
            return 10; /* Back to main */
            break;
            
        case GET_IPADDRESS:
            if (netcfg_get_ipaddress (client)) {
                state = BACKUP;
            } else {
                if (strncmp(interface, "plip", 4) == 0
                    || strncmp(interface, "slip", 4) == 0
                    || strncmp(interface, "ctc", 3) == 0
                    || strncmp(interface, "escon", 5) == 0
                    || strncmp(interface, "iucv", 4) == 0)
                    state = GET_POINTOPOINT;
                else
                    state = GET_NETMASK;
            }
            break;
            
        case GET_POINTOPOINT:
            state = netcfg_get_pointopoint(client) ?
                GET_IPADDRESS : GET_NAMESERVERS;
            break;
            
        case GET_NETMASK:
            state = netcfg_get_netmask(client) ?
                GET_IPADDRESS : GET_GATEWAY;
            break;
            
        case GET_GATEWAY:
            if (netcfg_get_gateway(client))
                state = GET_NETMASK;
            else 
                if (gateway.s_addr && ((gateway.s_addr & netmask.s_addr) != network.s_addr))
                    state = GATEWAY_UNREACHABLE;
                else
                    state = GET_NAMESERVERS;
            break;
        case GATEWAY_UNREACHABLE:
            debconf_capb(client); /* Turn off backup */
            debconf_input(client, "high", "netcfg/gateway_unreachable");
            debconf_go(client);
            state = GET_GATEWAY;
            debconf_capb(client, "backup");
            break;
        case GET_NAMESERVERS:
            state = (netcfg_get_nameservers (client, &nameservers)) ?
                GET_GATEWAY : CONFIRM;
            break;
        case GET_HOSTNAME:
            seed_hostname_from_dns(client, &ipaddress);
            state = (netcfg_get_hostname(client, "netcfg/get_hostname", &hostname, 1)) ?
                GET_NAMESERVERS : GET_DOMAIN;
            break;
        case GET_DOMAIN:
            if (!have_domain) {
                state = (netcfg_get_domain (client, &domain, "high")) ?
                    GET_HOSTNAME : QUIT;
            } else {
                di_info("domain = %s", domain);
                state = QUIT;
            }
            break;
            
        case CONFIRM:
            debconf_subst(client, "netcfg/confirm_static", "interface", interface);
            debconf_subst(client, "netcfg/confirm_static", "ipaddress",
                          (ipaddress.s_addr ? inet_ntop (AF_INET, &ipaddress, ptr1, sizeof (ptr1)) : none));
            debconf_subst(client, "netcfg/confirm_static", "pointopoint",
                          (pointopoint.s_addr ? inet_ntop (AF_INET, &pointopoint, ptr1, sizeof (ptr1)) : none));
            debconf_subst(client, "netcfg/confirm_static", "netmask",
                          (netmask.s_addr ? inet_ntop (AF_INET, &netmask, ptr1, sizeof (ptr1)) : none));
            debconf_subst(client, "netcfg/confirm_static", "gateway",
                          (gateway.s_addr ? inet_ntop (AF_INET, &gateway, ptr1, sizeof (ptr1)) : none));
            debconf_subst(client, "netcfg/confirm_static", "nameservers",
                          (nameservers ? nameservers : none));
            netcfg_nameservers_to_array(nameservers, nameserver_array);
            
            debconf_capb(client); /* Turn off backup for yes/no confirmation */
            
            debconf_input(client, "medium", "netcfg/confirm_static");
            debconf_go(client);
            debconf_get(client, "netcfg/confirm_static");
            if (strstr(client->value, "true")) {
                state = GET_HOSTNAME;
                netcfg_write_resolv(domain, nameserver_array);
                netcfg_activate_static(client);
            }
            else
                state = GET_IPADDRESS;
            
            debconf_capb(client, "backup");
            
            break;
            
        case QUIT:
            netcfg_write_common(ipaddress, hostname, domain);
            netcfg_write_static(domain, nameserver_array);
            return 0;
            break;
        }
    }
    return 0;
}
