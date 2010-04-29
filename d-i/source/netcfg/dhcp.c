/*
 * DHCP module for netcfg/netcfg-dhcp.
 *
 * Licensed under the terms of the GNU General Public License
 */

#include "netcfg.h"
#include <errno.h>
#include <stdlib.h>
#include <unistd.h>
#include <debian-installer.h>
#include <stdio.h>
#include <assert.h>
#include <sys/param.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/utsname.h>
#include <arpa/inet.h>
#include <net/if.h>
#include <time.h>
#include <netdb.h>

#define DHCP_OPTION_LEN 1236 /* pump 0.8.24 defines a max option size of 57,
                                dhcp 2.0pl5 uses 1222, dhcp3 3.0.6 uses 1236 */

const char* dhclient_request_options_dhclient[] = { "subnet-mask",
                                                    "broadcast-address",
                                                    "time-offset",
                                                    "routers",
                                                    "domain-name",
                                                    "domain-name-servers",
                                                    "host-name",
                                                    "ntp-servers", /* extra */
                                                    NULL };

const char* dhclient_request_options_udhcpc[] = { "subnet",
                                                  "broadcast",
                                                  "router",
                                                  "domain",
                                                  "namesrv",
                                                  "hostname",
                                                  "ntpsrv", /* extra */
                                                  NULL };

static int dhcp_exit_status = 1;
static pid_t dhcp_pid = -1;


/*
 * Add DHCP-related lines to /etc/network/interfaces
 */
static void netcfg_write_dhcp (char *iface, char *dhostname)
{
    FILE *fp;
    
    if ((fp = file_open(INTERFACES_FILE, "a"))) {
        fprintf(fp, "\n# The primary network interface\n");
        fprintf(fp, "auto %s\n", iface);
        fprintf(fp, "iface %s inet dhcp\n", iface);
        if (dhostname) {
            fprintf(fp, "\thostname %s\n", dhostname);
        }
        if (is_wireless_iface(iface)) {
            fprintf(fp, "\t# wireless-* options are implemented by the wireless-tools package\n");
            fprintf(fp, "\twireless-mode %s\n",
                    (mode == MANAGED) ? "managed" : "ad-hoc");
            fprintf(fp, "\twireless-essid %s\n",
                    (essid && *essid) ? essid : "any");
            if (wepkey != NULL)
                fprintf(fp, "\twireless-key1 %s\n", wepkey);
        }
        fclose(fp);
    }
}

/* Returns 1 if no default route is available */
static short no_default_route (void)
{
    FILE* iproute = NULL;
    char buf[256] = { 0 };
    
    if ((iproute = popen("ip route", "r")) != NULL) {
        while (fgets (buf, 256, iproute) != NULL) {
            if (buf[0] == 'd' && strstr (buf, "default via ")) {
                pclose(iproute);
                return 0;
            }
        }
        pclose(iproute);
    }
    
    return 1;
}

/*
 * Signal handler for DHCP client child
 *
 * When the child exits (either because it failed to obtain a
 * lease or because it succeeded and daemonized itself), this
 * gets the child's exit status and sets dhcp_pid to -1
 */
static void dhcp_client_sigchld(int sig __attribute__ ((unused))) 
{
    if (dhcp_pid <= 0)
        return;
    /*
     * I hope it's OK to call waitpid() from the SIGCHLD signal handler
     */
    waitpid(dhcp_pid,&dhcp_exit_status,0);
    dhcp_pid = -1;
}


/* 
 * This function will start whichever DHCP client is available
 * using the provided DHCP hostname, if supplied
 *
 * The client's PID is stored in dhcp_pid.
 */
int start_dhcp_client (struct debconfclient *client, char* dhostname)
{
    FILE *dc = NULL;
    const char **ptr;
    char **arguments;
    int options_count;
    enum { DHCLIENT, DHCLIENT3, PUMP, UDHCPC } dhcp_client;
    
    if (access("/var/lib/dhcp3", F_OK) == 0)
        dhcp_client = DHCLIENT3;
    else if (access("/sbin/dhclient", F_OK) == 0)
        dhcp_client = DHCLIENT;
    else if (access("/sbin/pump", F_OK) == 0)
        dhcp_client = PUMP;
    else if (access("/sbin/udhcpc", F_OK) == 0)
        dhcp_client = UDHCPC;
    else {
        debconf_input(client, "critical", "netcfg/no_dhcp_client");
        debconf_go(client);
        exit(1);
    }
    
    if ((dhcp_pid = fork()) == 0) { /* child */
        /* disassociate from debconf */
        fclose(client->out);
        
        /* get dhcp lease */
        switch (dhcp_client) {
        case PUMP:
            if (dhostname)
                execlp("pump", "pump", "-i", interface, "-h", dhostname, NULL);
            else
                execlp("pump", "pump", "-i", interface, NULL);
            
            break;
            
        case DHCLIENT:
            /* First, set up dhclient.conf */
            if ((dc = file_open(DHCLIENT_CONF, "w"))) {
                fprintf(dc, "send dhcp-class-identifier \"d-i\";\n");
                fprintf(dc, "request ");

                for (ptr = dhclient_request_options_dhclient; *ptr; ptr++) {
                    fprintf(dc, *ptr);

                    /* look ahead to see if it is the last entry */
                    if (*(ptr + 1))
                        fprintf(dc, ", ");
                    else
                        fprintf(dc, ";\n");
                }

                if (dhostname) {
                    fprintf(dc, "send host-name \"%s\";\n", dhostname);
                }
                fclose(dc);
            }
            
            execlp("dhclient", "dhclient", "-e", interface, NULL);
            break;
            
        case DHCLIENT3:
            /* Different place.. */
            
            if ((dc = file_open(DHCLIENT3_CONF, "w"))) {
                fprintf(dc, "send vendor-class-identifier \"d-i\";\n" );
                fprintf(dc, "request ");

                for (ptr = dhclient_request_options_dhclient; *ptr; ptr++) {
                    fprintf(dc, *ptr);

                    /* look ahead to see if it is the last entry */
                    if (*(ptr + 1))
                        fprintf(dc, ", ");
                    else
                        fprintf(dc, ";\n");
                }

                if (dhostname) {
                    fprintf(dc, "send host-name \"%s\";\n", dhostname);
                }
                fclose(dc);
            }
            
            execlp("dhclient", "dhclient", "-1", interface, NULL);
            break;

        case UDHCPC:
            /* figure how many options we have */
            options_count = 0;
            for (ptr = dhclient_request_options_udhcpc; *ptr; ptr++)
                options_count++;

            /* alloc the required memory for arguments:
               double of number of options since we need -O for each
               one plus 5 fixed ones plus 2 that are optional
               depending on hostname being set or not. */
            arguments = malloc((options_count * 2 + 8) * sizeof(char **));

            /* set the command options */
            options_count = 0;
            arguments[options_count++] = "udhcpc";
            arguments[options_count++] = "-i";
            arguments[options_count++] = interface;
            arguments[options_count++] = "-V";
            arguments[options_count++] = "d-i";
            for (ptr = dhclient_request_options_udhcpc; *ptr; ptr++) {
                arguments[options_count++] = "-O";
                arguments[options_count++] = *ptr;
            }

            if (dhostname) {
                arguments[options_count++] = "-H";
                arguments[options_count++] = dhostname;
            }

            arguments[options_count] = NULL;

            execvp("udhcpc", arguments);
            free(arguments);
            break;
        }
        if (errno != 0)
            di_error("Could not exec dhcp client: %s", strerror(errno));
        
        return 1; /* should NEVER EVER get here */
    }
    else if (dhcp_pid == -1)
        return 1;
    else {
        /* dhcp_pid contains the child's PID */
        signal(SIGCHLD, &dhcp_client_sigchld);
        return 0;
    }
}


static int kill_dhcp_client(void)
{
    system("killall.sh"); 
    return 0;
}


/*
 * Poll the started DHCP client for netcfg/dhcp_timeout seconds (def. 30)
 * and return 0 if a lease is known to have been acquired,
 * 1 otherwise.
 *
 * The client should be run such that it exits once a lease is acquired
 * (although its child continues to run as a daemon)
 *
 * This function will NOT kill the child if time runs out.  This allows
 * the user to choose to wait longer for the lease to be acquired.
 */
int poll_dhcp_client (struct debconfclient *client)
{
    int seconds_slept = 0;
    int ret = 1;
    int dhcp_seconds;
    
    debconf_get(client, "netcfg/dhcp_timeout");
    
    dhcp_seconds = atoi(client->value);
    
    /* show progress bar */
    debconf_capb(client, "backup progresscancel");
    debconf_progress_start(client, 0, dhcp_seconds, "netcfg/dhcp_progress");
    if (debconf_progress_info(client, "netcfg/dhcp_progress_note") == 30)
        goto stop;
    netcfg_progress_displayed = 1;
    
    /* wait between 2 and dhcp_seconds seconds for a DHCP lease */
    while ( ((dhcp_pid > 0) || (seconds_slept < 2))
            && (seconds_slept < dhcp_seconds) ) {
        sleep(1);
        seconds_slept++; /* Not exact but close enough */
        if (debconf_progress_step(client, 1) == 30)
            goto stop;
    }
    /* Either the client exited or time ran out */
    
    /* got a lease? display a success message */
    if (!(dhcp_pid > 0) && (dhcp_exit_status == 0)) {
        ret = 0;
        
        debconf_capb(client, "backup"); /* stop displaying cancel button */
        if (debconf_progress_set(client, dhcp_seconds) == 30)
            goto stop;
        if (debconf_progress_info(client, "netcfg/dhcp_success_note") == 30)
            goto stop;
        sleep(2);
    }
    
 stop:
    /* stop progress bar */
    debconf_progress_stop(client);
    debconf_capb(client, "backup");
    netcfg_progress_displayed = 0;
    
    return ret;
}


#define REPLY_RETRY_AUTOCONFIG       0
#define REPLY_RETRY_WITH_HOSTNAME    1
#define REPLY_CONFIGURE_MANUALLY     2
#define REPLY_DONT_CONFIGURE         3
#define REPLY_RECONFIGURE_WIFI       4
#define REPLY_LOOP_BACK              5
#define REPLY_CHECK_DHCP             6
#define REPLY_ASK_OPTIONS            7

int ask_dhcp_options (struct debconfclient *client)
{
    int ret;
    
    if (is_wireless_iface(interface)) {
        debconf_metaget(client, "netcfg/internal-wifireconf", "description");
        debconf_subst(client, "netcfg/dhcp_options", "wifireconf", client->value);
    }
    else /* blank from last time */
        debconf_subst(client, "netcfg/dhcp_options", "wifireconf", "");
    
    /* critical, we don't want to enter a loop */
    debconf_input(client, "critical", "netcfg/dhcp_options");
    ret = debconf_go(client);
    
    if (ret == 30)
        return GO_BACK;
    
    debconf_get(client, "netcfg/dhcp_options");
    
    /* strcmp sucks */
    if (client->value[0] == 'R') {	/* _R_etry ... or _R_econfigure ... */
        size_t len = strlen(client->value);
        if (client->value[len - 1] == 'e') /* ... with DHCP hostnam_e_ */
            return REPLY_RETRY_WITH_HOSTNAME;
        else if (client->value[len - 1] == 'k') /* ... wireless networ_k_ */
            return REPLY_RECONFIGURE_WIFI;
        else
            return REPLY_RETRY_AUTOCONFIG;
    }
    else if (client->value[0] == 'C') /* _C_onfigure ... */
        return REPLY_CONFIGURE_MANUALLY;
    else if (empty_str(client->value))
        return REPLY_LOOP_BACK;
    else
        return REPLY_DONT_CONFIGURE;
}

int ask_wifi_configuration (struct debconfclient *client)
{
    enum { ABORT, DONE, ESSID, WEP } wifistate = ESSID;
    for (;;) {
        switch (wifistate) {
        case ESSID:
            wifistate = (netcfg_wireless_set_essid(client, interface, "high") == GO_BACK) ?
                ABORT : WEP;
            break;
        case WEP:
            wifistate = (netcfg_wireless_set_wep(client, interface) == GO_BACK) ?
                ESSID : DONE;
            break;
        case ABORT:
            return REPLY_ASK_OPTIONS;
            break;
        case DONE:
            return REPLY_CHECK_DHCP;
            break;
        }
    }
}


int netcfg_activate_dhcp (struct debconfclient *client)
{
    char* dhostname = NULL;
    enum { START, POLL, ASK_OPTIONS, DHCP_HOSTNAME, HOSTNAME, DOMAIN, HOSTNAME_SANS_NETWORK } state = START;
    
    kill_dhcp_client();
    loop_setup();
    
    for (;;) {
        switch (state) {
        case START:
            if (start_dhcp_client(client, dhostname))
                netcfg_die(client); /* change later */
            else
                state = POLL;
            break;

        case POLL:
            if (poll_dhcp_client(client)) {
                /* could not get a lease, show the error, present options */
                debconf_capb(client, "");
                debconf_input(client, "critical", "netcfg/dhcp_failed");
                debconf_go(client);
                debconf_capb(client, "backup");
                state = ASK_OPTIONS;
            } else {
                /* got a lease */
                /*
                 * That means that the DHCP client has exited, although its
                 * child is still running as a daemon
                 */

                /* Before doing anything else, check for a default route */
                
                if (no_default_route()) {
                    debconf_input(client, "critical", "netcfg/no_default_route");
                    debconf_go(client);
                    debconf_get(client, "netcfg/no_default_route");
                    
                    if (!strcmp(client->value, "false")) {
                        state = ASK_OPTIONS;
                        break;
                    }
                }
                
                /*
                 * Set defaults for domain name and hostname
                 */
                
                char buf[MAXHOSTNAMELEN + 1] = { 0 };
                char *ptr = NULL;
                FILE *d = NULL;
                
                have_domain = 0;
                
                /*
                 * Default to the domain name returned via DHCP, if any
                 */
                if ((d = fopen(DOMAIN_FILE, "r")) != NULL) {
                    char domain[_UTSNAME_LENGTH + 1] = { 0 };
                    fgets(domain, _UTSNAME_LENGTH, d);
                    fclose(d);
                    unlink(DOMAIN_FILE);
                    
                    if (!empty_str(domain) && verify_hostname(domain) == 0) {
                        debconf_set(client, "netcfg/get_domain", domain);
                        have_domain = 1;
                    }
                }

                /*
                 * Record any ntp server information from DHCP for later
                 * verification and use by clock-setup
                 */
                if ((d = fopen(NTP_SERVER_FILE, "r")) != NULL) {
                    char ntpservers[DHCP_OPTION_LEN + 1] = { 0 };
                    fgets(ntpservers, DHCP_OPTION_LEN, d);
                    fclose(d);
                    unlink(NTP_SERVER_FILE);
                    
                    if (!empty_str(ntpservers)) {
                        debconf_set(client, "netcfg/dhcp_ntp_servers", 
                                    ntpservers);
                    }
                }

                /*
                 * Default to the hostname returned via DHCP, if any,
                 * otherwise to the requested DHCP hostname
                 * otherwise to the hostname found in DNS for the IP address
                 * of the interface
                 */
                if (gethostname(buf, sizeof(buf)) == 0
                    && !empty_str(buf)
                    && strcmp(buf, "(none)")
                    && verify_hostname(buf) == 0
                    ) {
                    di_info("DHCP hostname: \"%s\"", buf);
                    debconf_set(client, "netcfg/get_hostname", buf);
                }
                else if (dhostname) {
                    debconf_set(client, "netcfg/get_hostname", dhostname);
                } else {
                    struct ifreq ifr;
                    struct in_addr d_ipaddr = { 0 };
                    
                    ifr.ifr_addr.sa_family = AF_INET;
                    strncpy(ifr.ifr_name, interface, IFNAMSIZ);
                    if (ioctl(skfd, SIOCGIFADDR, &ifr) == 0) {
                        d_ipaddr = ((struct sockaddr_in *)&ifr.ifr_addr)->sin_addr;
                        seed_hostname_from_dns(client, &d_ipaddr);
                    }
                    else
                        di_warning("ioctl failed (%s)", strerror(errno));
                }
                
                /*
                 * Default to the domain name that is the domain part
                 * of the hostname, if any
                 */
                if (have_domain == 0 && (ptr = strchr(buf, '.')) != NULL) {
                    debconf_set(client, "netcfg/get_domain", ptr + 1);
                    have_domain = 1;
                }
                
                /* Make sure we have NS going if the DHCP server didn't serve it up */
                if (resolv_conf_entries() <= 0) {
                    char *nameservers = NULL;
                    
                    if (netcfg_get_nameservers (client, &nameservers) == GO_BACK) {
                        state = ASK_OPTIONS;
                        break;
                    }
                    
                    netcfg_nameservers_to_array (nameservers, nameserver_array);
                }
                
                state = HOSTNAME;
            }
            break;
            
        case ASK_OPTIONS:
            /* DHCP client may still be running */
            switch (ask_dhcp_options (client)) {
            case GO_BACK:
                kill_dhcp_client();
                return 10;
            case REPLY_RETRY_WITH_HOSTNAME:
                state = DHCP_HOSTNAME;
                break;
            case REPLY_CONFIGURE_MANUALLY:
                kill_dhcp_client();
                return 15;
                break;
            case REPLY_DONT_CONFIGURE:
                kill_dhcp_client();
                netcfg_write_loopback();
                state = HOSTNAME_SANS_NETWORK;
                break;
            case REPLY_RETRY_AUTOCONFIG:
                if (dhcp_pid > 0)
                    state = POLL;
                else {
                    kill_dhcp_client();
                    state = START;
                }
                break;
            case REPLY_RECONFIGURE_WIFI:
                if (ask_wifi_configuration(client) == REPLY_CHECK_DHCP) {
                    if (dhcp_pid > 0)
                        state = POLL;
                    else {
                        kill_dhcp_client();
                        state = START;
                    }
                }
                else
                    state = ASK_OPTIONS;
                break;
            }
            break;

        case DHCP_HOSTNAME:
            /* DHCP client may still be running */
            if (netcfg_get_hostname(client, "netcfg/dhcp_hostname", &dhostname, 0))
                state = ASK_OPTIONS;
            else {
                if (empty_str(dhostname)) {
                    free(dhostname);
                    dhostname = NULL;
                }
                kill_dhcp_client();
                state = START;
            }
            break;
            
        case HOSTNAME:
            if (netcfg_get_hostname (client, "netcfg/get_hostname", &hostname, 1)) {
                /*
                 * Going back to POLL wouldn't make much sense.
                 * However, it does make sense to go to the retry
                 * screen where the user can elect to retry DHCP with
                 * a requested DHCP hostname, etc.
                 */
                state = ASK_OPTIONS;
            }
            else
                state = DOMAIN;
            break;
            
        case DOMAIN:
            if (!have_domain && netcfg_get_domain (client, &domain, "medium"))
                state = HOSTNAME;
            else {
                netcfg_write_common(ipaddress, hostname, domain);
                netcfg_write_dhcp(interface, dhostname);
                return 0;
            }
            break;
            
        case HOSTNAME_SANS_NETWORK:
            if (netcfg_get_hostname (client, "netcfg/get_hostname", &hostname, 0))
                state = ASK_OPTIONS;
            else {
                struct in_addr null_ipaddress;
                null_ipaddress.s_addr = 0;
                netcfg_write_common(null_ipaddress, hostname, NULL);
                return 0;
            }
            break;
        }
    }
} 

/* returns number of 'nameserver' entries in resolv.conf */
int resolv_conf_entries (void)
{
    FILE *f;
    int count = 0;
    
    if ((f = fopen(RESOLV_FILE, "r")) != NULL) {
        char buf[256];
        
        while (fgets(buf, 256, f) != NULL) {
            char *ptr;
            
            if ((ptr = strchr(buf, ' ')) != NULL) {
                *ptr = '\0';
                if (strcmp(buf, "nameserver") == 0)
                    count++;
            }
        }
        
        fclose(f);
    }
    else
        count = -1;
    
    return count;
}
