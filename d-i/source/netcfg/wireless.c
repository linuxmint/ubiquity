/* Wireless support using iwlib for netcfg.
 * (C) 2004 Joshua Kwan, Bastian Blank
 *
 * Licensed under the GNU General Public License
 */

#include "netcfg.h"

#ifdef WIRELESS
#include <debian-installer/log.h>
#include <iwlib.h>
#include <sys/types.h>
#include <assert.h>

#define ENTER_MANUALLY 10


int is_wireless_iface (const char* if_name)
{
    wireless_config wc;
    return (iw_get_basic_config (wfd, (char*)if_name, &wc) == 0);
}

void free_network_list(wireless_scan **network_list)
{
    wireless_scan *old, *network;

    if (network_list == NULL) {
        return;
    }

    for (network = *network_list; network; ) {
        old = network;
        network = network->next;
        free(old);
    }

    *network_list = NULL;
}

int netcfg_wireless_choose_essid_manually(struct debconfclient *client,
        struct netcfg_interface *interface, char *question)
{
    wireless_config wconf;

    iw_get_basic_config (wfd, interface->name, &wconf);

    debconf_subst(client, question, "iface", interface->name);
    debconf_subst(client, "netcfg/wireless_adhoc_managed", "iface", interface->name);

    if (debconf_go(client) == CMD_GOBACK) {
        debconf_fset(client, question, "seen", "false");
        return GO_BACK;
    }

    debconf_get(client, "netcfg/wireless_adhoc_managed");

    if (!strcmp(client->value, "Ad-hoc network (Peer to peer)")) {
        interface->mode = ADHOC;
    }

    wconf.has_mode = 1;
    wconf.mode = interface->mode;

get_essid:
    debconf_input(client, "high", question);

    if (debconf_go(client) == CMD_GOBACK) {
        return GO_BACK;
    }

    debconf_get(client, question);

    if (client->value && strlen(client->value) > IW_ESSID_MAX_SIZE) {
        char max_len_string[5];
        sprintf(max_len_string, "%d", IW_ESSID_MAX_SIZE);
        debconf_capb(client, "");
        debconf_subst(client, "netcfg/invalid_essid", "essid", client->value);
        debconf_subst(client, "netcfg/invalid_essid", "max_essid_len",
                max_len_string);
        debconf_input(client, "critical", "netcfg/invalid_essid");
        debconf_go(client);

        debconf_fset(client, question, "seen", "false");
        debconf_capb(client, "backup");
        goto get_essid;
    }

    strdup(client->value);

    memset(wconf.essid, 0, IW_ESSID_MAX_SIZE + 1);
    snprintf(wconf.essid, IW_ESSID_MAX_SIZE + 1, "%s", interface->essid);
    wconf.has_essid = 1;
    wconf.essid_on = 1;

    iw_set_basic_config(wfd, interface->name, &wconf);

    di_info("Network chosen: %s. Proceeding to connect.", interface->essid);

    return 0;
}

int exists_in_network_list(wireless_scan_head list, wireless_scan *network)
{
    wireless_scan *it;

    for (it = list.result; it != network; it = it->next) {
        if (strcmp(it->b.essid, network->b.essid) == 0) {
            return 1;
        }
    }

    return 0;
}

int netcfg_wireless_show_essids(struct debconfclient *client, struct netcfg_interface *interface)
{
    wireless_scan_head network_list;
    wireless_config wconf;
    char *buffer;
    int essid_list_len = 1;

    iw_get_basic_config (wfd, interface->name, &wconf);
    interface_up(interface->name);

    if (iw_scan(wfd, interface->name, iw_get_kernel_we_version(),
                &network_list) >= 0 ) {
        wireless_scan *network;

        di_info("Scan of wireless interface %s succeeded.", interface->name);

        /* Determine the actual length of the buffer. */
        for (network = network_list.result; network; network =
            network->next) {
            if (!exists_in_network_list(network_list, network)) {
                essid_list_len += (strlen(network->b.essid) + 2);
            }
        }
        /* Buffer initialization. */
        buffer = malloc(essid_list_len * sizeof(char));
        if (buffer == NULL) {
            /* Error in memory allocation. */
            di_warning("Unable to allocate memory for network list buffer.");
            return ENTER_MANUALLY;
        }
        strcpy(buffer, "");

        /* Create list of available ESSIDs. */
        for (network = network_list.result; network; network = network->next) {
            if (!exists_in_network_list(network_list, network)) {
                strcat(buffer, network->b.essid);
                strcat(buffer, ", ");
            }
        }

        /* Asking the user. */
        debconf_capb(client, "backup");
        debconf_subst(client, "netcfg/wireless_show_essids", "essid_list", buffer);
        debconf_fset(client, "netcfg/wireless_show_essids", "seen", "false");
        debconf_input(client, "high", "netcfg/wireless_show_essids");

        if (debconf_go(client) == CMD_GOBACK) {
            debconf_fset(client, "netcfg/wireless_show_essids", "seen",
                    "false");
            free_network_list(&network_list.result);
            free(buffer);

            return GO_BACK;
        }

        debconf_get(client, "netcfg/wireless_show_essids");

        /* User wants to enter an ESSID manually. */
        if (strcmp(client->value, "manual") == 0) {
            free_network_list(&network_list.result);
            free(buffer);

            return ENTER_MANUALLY;
        }

        /* User has chosen a network from the list, need to find which one and
         * get its cofiguration. */
        for (network = network_list.result; network; network = network->next) {
            if (strcmp(network->b.essid, client->value) == 0) {
                wconf = network->b;
                interface->essid = strdup(network->b.essid);
                break;
            }
        }

        /* Free the network list. */
        free_network_list(&network_list.result);
        free(buffer);
    }
    else {
        /* Go directly to choosing manually, use the wireless_essid_again
         * question. */
        if (netcfg_wireless_choose_essid_manually(client, interface,
                "netcfg/wireless_essid_again") == GO_BACK) {

            return GO_BACK;
        }

        return 0;
    }

    iw_set_basic_config(wfd, interface->name, &wconf);
    interface_down(interface->name);

    di_info("Network chosen: %s. Proceeding to connect.", interface->essid);

    return 0;
}

int netcfg_wireless_set_essid(struct debconfclient *client, struct netcfg_interface *interface)
{
    wireless_config wconf;
    int choose_ret;

select_essid:
    iw_get_basic_config(wfd, interface->name, &wconf);

    choose_ret = netcfg_wireless_show_essids(client, interface);

    if (choose_ret == GO_BACK) {
        return GO_BACK;
    }

    if (choose_ret == ENTER_MANUALLY) {
        if (netcfg_wireless_choose_essid_manually(client, interface,
                                      "netcfg/wireless_essid") == GO_BACK) {
            goto select_essid;
        }
    }

    return 0;
}

static void unset_wep_key (const char *if_name)
{
    wireless_config wconf;

    iw_get_basic_config(wfd, if_name, &wconf);

    wconf.has_key = 1;
    wconf.key[0] = '\0';
    wconf.key_flags = IW_ENCODE_DISABLED | IW_ENCODE_NOKEY;
    wconf.key_size = 0;

    iw_set_basic_config (wfd, if_name, &wconf);
}

int netcfg_wireless_set_wep (struct debconfclient * client, struct netcfg_interface *interface)
{
    wireless_config wconf;
    char* rv = NULL;
    int ret, keylen, err = 0;
    unsigned char buf [IW_ENCODING_TOKEN_MAX + 1];
    struct iwreq wrq;

    iw_get_basic_config (wfd, interface->name, &wconf);

    debconf_subst(client, "netcfg/wireless_wep", "iface", interface->name);
    debconf_input (client, "high", "netcfg/wireless_wep");
    ret = debconf_go(client);

    if (ret == CMD_GOBACK)
        return GO_BACK;

    debconf_get(client, "netcfg/wireless_wep");
    rv = client->value;

    if (empty_str(rv)) {
        unset_wep_key (interface->name);

        if (interface->wepkey != NULL) {
            free(interface->wepkey);
            interface->wepkey = NULL;
        }

        return 0;
    }

    while ((keylen = iw_in_key (rv, buf)) == -1) {
        debconf_subst(client, "netcfg/invalid_wep", "wepkey", rv);
        debconf_input(client, "critical", "netcfg/invalid_wep");
        debconf_go(client);

        debconf_input (client, "high", "netcfg/wireless_wep");
        ret = debconf_go(client);

        if (ret == CMD_GOBACK)
            return GO_BACK;

        debconf_get(client, "netcfg/wireless_wep");
        rv = client->value;
    }

    /* Now rv is safe to store since it parsed fine */
    interface->wepkey = strdup(rv);

    wrq.u.data.pointer = buf;
    wrq.u.data.flags = 0;
    wrq.u.data.length = keylen;

    if ((err = iw_set_ext(skfd, interface->name, SIOCSIWENCODE, &wrq)) < 0) {
        di_warning("setting WEP key on %s failed with code %d", interface->name, err);
        return -1;
    }

    return 0;
}

#else

int is_wireless_iface (const char *if_name)
{
    (void) if_name;
    return 0;
}

int netcfg_wireless_set_essid (struct debconfclient *client, struct netcfg_interface *interface)
{
    (void) client;
    (void) interface;
    return 0;
}

int netcfg_wireless_set_wep (struct debconfclient *client, struct netcfg_interface *interface)
{
    (void) client;
    (void) interface;
    return 0;
}

#endif
