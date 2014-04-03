/*
* WPA module for netcfg
*
* Copyright (C) 2008 Glenn Saberton <gsaberton@foomagic.org>
*
* Licensed under the terms of the GNU General Public License version 2
*
*/

#include "netcfg.h"
#include <errno.h>
#include <stdlib.h>
#include <unistd.h>
#include <debian-installer.h>

#ifdef WIRELESS
#include "wpa_ctrl.h"
#include <iwlib.h>

pid_t wpa_supplicant_pid = -1;
struct wpa_ctrl *ctrl;
static int wpa_is_running = 0;

int init_wpa_supplicant_support(struct netcfg_interface *interface)
{
    if (access("/sbin/wpa_supplicant", F_OK) == 0)
        interface->wpa_supplicant_status = WPA_OK;
    else {
        interface->wpa_supplicant_status = WPA_UNAVAIL;
        di_info("Wpasupplicant not found on the system. Disabling WPA options");
    }
    return 0;
}

int kill_wpa_supplicant(void)
{
    pid_t wpa_pid;
    FILE *fp;

    fp = (fopen(WPAPID, "r"));
    if (fp == NULL) {
        di_warning("Couldn't read Wpasupplicant pid file, not trying to kill.");
        return 0;
    }
    else {
        if (fscanf(fp, "%d", &wpa_pid) != 1) {
            di_warning("Couldn't read pid from Wpasupplicant pid file, not trying to kill.");
            return 0;
        }
        fclose(fp);
    }
      if ((kill(wpa_pid, SIGTERM)) == 0)
          return 0;
      else {
          kill(wpa_pid, SIGKILL);
          unlink(WPAPID);
          return 0;
      }
}

int wireless_security_type (struct debconfclient *client, const char *if_name)
{
    debconf_subst(client, "netcfg/wireless_security_type", "iface", if_name);
    debconf_input(client, "high", "netcfg/wireless_security_type");

    if (debconf_go(client) == CMD_GOBACK)
        return GO_BACK;

    debconf_get(client, "netcfg/wireless_security_type");

    if (!strcmp(client->value, "wep/open"))
        return REPLY_WEP;
    else
        return REPLY_WPA;

}

int netcfg_set_passphrase (struct debconfclient *client, struct netcfg_interface *interface)
{
    debconf_subst(client, "netcfg/wireless_wpa", "iface", interface->name);
    debconf_input(client, "high", "netcfg/wireless_wpa");

    if (debconf_go(client) == CMD_GOBACK)
        return GO_BACK;

    if (interface->passphrase != NULL)
        free(interface->passphrase);
        
    debconf_get(client, "netcfg/wireless_wpa");
    interface->passphrase = strdup(client->value);

    while (strlen(interface->passphrase) < WPA_MIN || strlen(interface->passphrase) > WPA_MAX) {
        debconf_subst(client, "netcfg/invalid_pass", "passphrase", interface->passphrase);
        debconf_input(client, "critical", "netcfg/invalid_pass");
        debconf_go(client);
        free(interface->passphrase);

        debconf_input(client, "high", "netcfg/wireless_wpa");

        if (debconf_go(client) == CMD_GOBACK)
            return GO_BACK;

        debconf_get(client, "netcfg/wireless_wpa");
        interface->passphrase = strdup(client->value);
    }

    return 0;
}

static int start_wpa_daemon(struct debconfclient *client, const char *if_name)
{
    wpa_supplicant_pid = fork();

    if (wpa_supplicant_pid == 0) {
        fclose(client->out);
        if (execlp("wpa_supplicant", "wpa_supplicant", "-i", if_name, "-C",
                   WPASUPP_CTRL, "-P", WPAPID, "-B", NULL) == -1) {
            di_error("could not exec wpasupplicant: %s", strerror(errno));
            return 1;
        }
        else
            return 0;
    }
    else {
        waitpid(wpa_supplicant_pid, NULL, 0);
        return 0;
    }
}

void wpa_daemon_running(void)
{
    FILE *fp = fopen(WPAPID, "r");
    if (fp) {
        wpa_is_running = 1;
        fclose(fp);
    }
}

static int wpa_connect(const char *if_name)
{
    char *cfile;
    int flen, res;

    flen = (strlen(WPASUPP_CTRL) + strlen(if_name) + 2);

    cfile = malloc(flen);
    if (cfile == NULL) {
        di_info("Can't allocate memory for WPA control interface.");
        return 1;
    }

    res = snprintf(cfile, flen, "%s/%s", WPASUPP_CTRL, if_name);
    if ((res < 0) || (res >= flen)) {
        free(cfile);
        return 1;
    }
    ctrl = wpa_ctrl_open(cfile);
    free(cfile);

    if (ctrl == NULL) {
        di_info("Couldn't connect to wpasupplicant");
        return 1;
    }
    else
        return 0;
}

static int netcfg_wpa_cmd (char *cmd)
{
    char buf[256];
    size_t len;
    int ret;

    len = sizeof(buf) -1;
    ret = wpa_ctrl_request(ctrl, cmd, strlen(cmd), buf, &len, NULL);

    if (ret < 0) {
        di_info("Sending %s to wpasupplicant failed", cmd);
        return 1;
    }

    return 0;
}

static int wpa_set_ssid (char *ssid)
{
    int ret, res;
    size_t len;
    char cmd[256];
    char buf[256];

    res = snprintf(cmd, sizeof(cmd), "SET_NETWORK 0 %s \"%s\"", "ssid", ssid);
    if (res < 0)
        return 1;

    len = sizeof(buf) -1;
    ret = wpa_ctrl_request(ctrl, cmd, sizeof(cmd), buf, &len, NULL);
    if (ret != 0) {
        di_info("Failed to set the ssid with wpasupplicant");
        return 1;
    }
    return 0;
}

static int wpa_set_psk(char *passphrase)
{
    int ret, res;
    size_t len;
    char buf[256];
    char cmd[256];

    res = snprintf(cmd, sizeof(cmd), "SET_NETWORK 0 %s \"%s\"", "psk", passphrase);
    if (res < 0)
        return 1;

    len = sizeof(buf) -1;
    ret = wpa_ctrl_request(ctrl, cmd, sizeof(cmd), buf, &len, NULL);
    if (ret != 0)
        return 1;

    return 0;
}

static int wpa_status(void)
{
    int ret;
    size_t len;
    char buf[2048];
    const char *success = "wpa_state=COMPLETED";

    len = sizeof(buf) -1;
    ret = wpa_ctrl_request(ctrl, "STATUS", 7, buf, &len, NULL);

    if (ret == 0) {
        buf[len] = '\0';
        di_info("buf = %s", buf);
    }
    else
        return 1;

    if (strstr(buf, success) == NULL)
        return 1;
    else {
        di_info("success");
        return 0;
    }
}

int poll_wpa_supplicant(struct debconfclient *client)
{
    int wpa_timeout = 60;
    int seconds_slept = 0;
    int state = 1;

    debconf_capb(client, "backup progresscancel");
    debconf_progress_start(client, 0, wpa_timeout, "netcfg/wpa_progress");

    for (seconds_slept = 0; seconds_slept <= wpa_timeout; seconds_slept++) {

         if (debconf_progress_info(client, "netcfg/wpa_progress_note") ==
                 CMD_PROGRESSCANCELLED)
             goto stop;

             if (debconf_progress_step(client, 1) == CMD_PROGRESSCANCELLED)
                 goto stop;

             sleep(1);

             if ((seconds_slept <= wpa_timeout) && (seconds_slept % 5) == 0) {
                 if (!wpa_status()) {
                     debconf_progress_set(client, wpa_timeout);
                     debconf_progress_info(client, "netcfg/wpa_success_note");
                     state = 0;
                     sleep(2);
                     goto stop;
                 }
             }
             if (seconds_slept == wpa_timeout) {
                 debconf_progress_stop(client);
                 debconf_capb(client, "backup");
                 debconf_capb(client, "");
                 debconf_input(client, "critical", "netcfg/wpa_supplicant_failed");
                 debconf_go(client);
                 debconf_capb(client, "backup");
                 return 1;
             }
    }
    stop:
        debconf_progress_stop(client);
        debconf_capb(client, "backup");
        if (!state)
            return 0;
        else
            return 1;

}

int wpa_supplicant_start(struct debconfclient *client, const struct netcfg_interface *interface)
{
    int retry = 0;

    enum { CHECK_DAEMON,
           START_DAEMON,
           CONNECT,
           PING,
           ADD_NETWORK,
           SET_ESSID,
           SET_PSK,
           SET_SCAN_SSID,
           ENABLE_NETWORK,
           POLL,
           ABORT,
           SUCCESS } state = CHECK_DAEMON;

    for (;;) {
        switch(state) {

        case CHECK_DAEMON:
            wpa_daemon_running();
            if (wpa_is_running)
                state = CONNECT;
            else
                state = START_DAEMON;
            break;

        case START_DAEMON:
            if (!start_wpa_daemon(client, interface->name))
                state = CONNECT;
            else
                state = ABORT;
            break;

        case CONNECT:
            if (wpa_connect(interface->name) == 0)
                state = PING;
            else
                state = ABORT;
            break;

        case PING:
            /* if the daemon doesn't respond, try and ping
             * it and increment retry. If we have done
             * this 4 times, something must be wrong
             * so bail out.  */
            retry++;
            if (retry > 4)
                state = ABORT;
            else if (netcfg_wpa_cmd("PING")) {
                kill_wpa_supplicant();
                state = START_DAEMON;
                break;
            }
            else
                state = ADD_NETWORK;
            break;

        case ADD_NETWORK:
            if (wpa_is_running) {
                state = SET_ESSID;
                break;
            }
            if (netcfg_wpa_cmd("ADD_NETWORK"))
                state = PING;
            else
                state = SET_ESSID;
            break;

        case SET_ESSID:
            if (wpa_set_ssid(interface->essid))
                state = PING;
            else
                state = SET_PSK;
            break;

        case SET_PSK:
            if (wpa_set_psk(interface->passphrase))
                state = PING;
            else
                state = SET_SCAN_SSID;
            break;

        case SET_SCAN_SSID:
            if (netcfg_wpa_cmd("SET_NETWORK 0 scan_ssid 1"))
                state = PING;
            else
                state = ENABLE_NETWORK;
            break;

        case ENABLE_NETWORK:
             if (netcfg_wpa_cmd("ENABLE_NETWORK 0"))
                 state = PING;
             else
                 state = POLL;
             break;

        case POLL:
            if (poll_wpa_supplicant(client))
                state = ABORT;
            else
                state = SUCCESS;
            break;

        case ABORT:
            if (ctrl == NULL)
                return GO_BACK;
            else {
                wpa_ctrl_close(ctrl);
                ctrl = NULL;
                return GO_BACK;
            }

         case SUCCESS:
             if (ctrl == NULL)
                 return 0;
             else {
                 wpa_ctrl_close(ctrl);
                 ctrl = NULL;
                 return 0;
             }
        }
    }
}

#else  /* Non-WIRELESS stubs of public API */

int init_wpa_supplicant_support(struct netcfg_interface *interface)
{
    (void)interface;
    return 0;
}

int kill_wpa_supplicant(void)
{
    return 0;
}

int wireless_security_type(struct debconfclient *client, const char *if_name)
{
    (void)client;
    (void)if_name;

    return 0;
}

int netcfg_set_passphrase(struct debconfclient *client, struct netcfg_interface *interface)
{
    (void)client;
    (void)interface;

    return 0;
}

int wpa_supplicant_start(struct debconfclient *client, const struct netcfg_interface *interface)
{
    (void)client;
    (void)interface;

    return 0;
}

#endif  /* WIRELESS */
