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

int is_wireless_iface (const char* iface)
{
    wireless_config wc;
    return (iw_get_basic_config (wfd, (char*)iface, &wc) == 0);
}

int netcfg_wireless_set_essid (struct debconfclient * client, struct netcfg_interface *interface, char* priority)
{
    int ret, couldnt_associate = 0;
    wireless_config wconf;
    char* tf = NULL, *user_essid = NULL, *ptr = wconf.essid;

    iw_get_basic_config (wfd, interface->name, &wconf);

    debconf_subst(client, "netcfg/wireless_essid", "iface", interface->name);
    debconf_subst(client, "netcfg/wireless_essid_again", "iface", interface->name);
    debconf_subst(client, "netcfg/wireless_adhoc_managed", "iface", interface->name);

    debconf_input(client, priority ? priority : "low", "netcfg/wireless_adhoc_managed");

    if (debconf_go(client) == 30)
        return GO_BACK;

    debconf_get(client, "netcfg/wireless_adhoc_managed");

    if (!strcmp(client->value, "Ad-hoc network (Peer to peer)"))
        interface->mode = ADHOC;

    wconf.has_mode = 1;
    wconf.mode = interface->mode;

    debconf_input(client, priority ? priority : "high", "netcfg/wireless_essid");

    if (debconf_go(client) == 30)
        return GO_BACK;

    debconf_get(client, "netcfg/wireless_essid");
    tf = strdup(client->value);

automatic:
    /* question not asked or user doesn't care or we're successfully associated */
    if (!empty_str(wconf.essid) || empty_str(client->value))
    {
        int i, success = 0;

        /* Default to any AP */
        wconf.essid[0] = '\0';
        wconf.essid_on = 0;

        iw_set_basic_config (wfd, interface->name, &wconf);

        /* Wait for association.. (MAX_SECS seconds)*/
#define MAX_SECS 3

        debconf_capb(client, "backup progresscancel");
        debconf_progress_start(client, 0, MAX_SECS, "netcfg/wifi_progress_title");
        if (debconf_progress_info(client, "netcfg/wifi_progress_info") == 30)
            goto stop;

        for (i = 0; i <= MAX_SECS; i++) {
            int progress_ret;

            interface_up(interface->name);
            sleep (1);
            iw_get_basic_config (wfd, interface->name, &wconf);

            if (!empty_str(wconf.essid)) {
                /* Save for later */
                debconf_set(client, "netcfg/wireless_essid", wconf.essid);
                debconf_progress_set(client, MAX_SECS);
                success = 1;
                break;
            }

            progress_ret = debconf_progress_step(client, 1);
            interface_down(interface->name);
            if (progress_ret == 30)
                break;
        }

    stop:
        debconf_progress_stop(client);
        debconf_capb(client, "backup");

        if (success)
            return 0;

        couldnt_associate = 1;
    }
    /* yes, wants to set an essid by himself */

    if (strlen(tf) <= IW_ESSID_MAX_SIZE) /* looks ok, let's use it */
        user_essid = tf;

    while (!user_essid || empty_str(user_essid) ||
           strlen(user_essid) > IW_ESSID_MAX_SIZE) {
        /* Misnomer of a check. Basically, if we went through autodetection,
         * we want to enter this loop, but we want to suppress anything that
         * relied on the checking of tf/user_essid (i.e. "", in most cases.) */
        if (!couldnt_associate) {
            debconf_subst(client, "netcfg/invalid_essid", "essid", user_essid);
            debconf_input(client, "high", "netcfg/invalid_essid");
            debconf_go(client);
        }

        if (couldnt_associate)
            ret = debconf_input(client, "critical", "netcfg/wireless_essid_again");
        else
            ret = debconf_input(client, "low", "netcfg/wireless_essid");

        /* we asked the question once, why can't we ask it again? */
        if (ret == 30)
            /* maybe netcfg/wireless_essid was preseeded; if so, give up */
            break;

        if (debconf_go(client) == 30) /* well, we did, but he wants to go back */
            return GO_BACK;

        if (couldnt_associate)
            debconf_get(client, "netcfg/wireless_essid_again");
        else
            debconf_get(client, "netcfg/wireless_essid");

        if (empty_str(client->value)) {
            if (couldnt_associate)
                /* we've already tried the empty string here, so give up */
                break;
            else
                goto automatic;
        }

        /* But now we'd not like to suppress any MORE errors */
        couldnt_associate = 0;

        free(user_essid);
        user_essid = strdup(client->value);
    }

    interface->essid = user_essid;

    memset(ptr, 0, IW_ESSID_MAX_SIZE + 1);
    snprintf(wconf.essid, IW_ESSID_MAX_SIZE + 1, "%s", interface->essid);
    wconf.has_essid = 1;
    wconf.essid_on = 1;

    iw_set_basic_config (wfd, interface->name, &wconf);

    return 0;
}

static void unset_wep_key (const char *iface)
{
    wireless_config wconf;

    iw_get_basic_config(wfd, iface, &wconf);

    wconf.has_key = 1;
    wconf.key[0] = '\0';
    wconf.key_flags = IW_ENCODE_DISABLED | IW_ENCODE_NOKEY;
    wconf.key_size = 0;

    iw_set_basic_config (wfd, iface, &wconf);
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

    if (ret == 30)
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

        if (ret == 30)
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

int is_wireless_iface (const char *iface)
{
    (void) iface;
    return 0;
}

int netcfg_wireless_set_essid (struct debconfclient *client, struct netcfg_interface *interface, char *priority)
{
    (void) client;
    (void) interface;
    (void) priority;
    return 0;
}

int netcfg_wireless_set_wep (struct debconfclient *client, struct netcfg_interface *interface)
{
    (void) client;
    (void) interface;
    return 0;
}

#endif
