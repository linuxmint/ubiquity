
#include "nm-conf.h"
#include <sys/stat.h>
#include <errno.h>

/* Linux provides a lightweight facility that can generate UUIDs for us. */
static void get_uuid(char* target)
{
    FILE* fp = fopen("/proc/sys/kernel/random/uuid", "r");
    if (fgets(target, NM_MAX_LEN_UUID, fp) == NULL)
    {
        di_error("get_uuid() failed: %s", strerror(errno));
        exit(1);
    }
    target[NM_MAX_LEN_UUID-1] = '\0'; // clear the newline
    fclose(fp);
}

/* Functions for printing informations in Network Manager format. */

void nm_write_connection(FILE *config_file, nm_connection connection)
{
    fprintf(config_file, "\n%s\n", NM_SETTINGS_CONNECTION);
    fprintf(config_file, "id=%s\n", connection.id);
    fprintf(config_file, "uuid=%s\n", connection.uuid);
    fprintf(config_file, "type=%s\n", (connection.type == WIFI) ?
            NM_DEFAULT_WIRELESS : NM_DEFAULT_WIRED);
}

#ifdef WIRELESS
void nm_write_wireless_specific_options(FILE *config_file,
        struct nm_config_info *nmconf)
{
    nm_wireless wireless = nmconf->wireless;

    fprintf(config_file, "\n%s\n", NM_SETTINGS_WIRELESS);
    fprintf(config_file, "ssid=%s\n", wireless.ssid);
    fprintf(config_file, "mode=%s\n", (wireless.mode == AD_HOC) ?
            "adhoc" : "infrastructure");

    if (strcmp(wireless.mac_addr, "") && nmconf->connection.manual == 1) {
        fprintf(config_file, "mac=%s\n", wireless.mac_addr);
    }
    if (wireless.is_secured == TRUE) {
        fprintf(config_file, "security=%s\n", NM_DEFAULT_WIRELESS_SECURITY);
    }
}
#endif

void nm_write_wired_specific_options(FILE *config_file,
        struct nm_config_info *nmconf)
{
    nm_wired wired = nmconf->wired;

    fprintf(config_file, "\n%s\n", NM_SETTINGS_WIRED);

    if (strcmp(wired.mac_addr, "") && nmconf->connection.manual == 1) {
        fprintf(config_file, "mac=%s\n", wired.mac_addr);
    }
}

#ifdef WIRELESS
void nm_write_wireless_security(FILE *config_file, nm_wireless_security
        wireless_security)
{
    fprintf(config_file, "\n%s\n", NM_SETTINGS_WIRELESS_SECURITY);

    if (wireless_security.key_mgmt == WPA_PSK) {
        fprintf(config_file, "key-mgmt=%s\n", "wpa-psk");
        fprintf(config_file, "psk=%s\n", wireless_security.psk);
    }
    else {
        fprintf(config_file, "key-mgmt=%s\n", "none");
        fprintf(config_file, "auth-alg=%s\n",
                (wireless_security.auth_alg == OPEN) ? "open" : "shared");
        fprintf(config_file, "wep-key0=%s\n", wireless_security.wep_key0);
        fprintf(config_file, "wep-key-type=%d\n",
                wireless_security.wep_key_type);
    }
}
#endif

void nm_write_static_ipvX(FILE *config_file, nm_ipvX ipvx)
{
    char    buffer[NM_MAX_LEN_BUF], addr[NM_MAX_LEN_IPV4];
    int     i;

    /* Get DNS in printable format. */
    memset(buffer, 0, NM_MAX_LEN_BUF);

    for (i = 0; !empty_str(ipvx.nameservers[i]); i++) {
        strcat(buffer, ipvx.nameservers[i]);
        strcat(buffer, ";");
    }

    if (strcmp(buffer, "")) {
        fprintf(config_file, "dns=%s\n", buffer);
    }

    /* Get addresses in printable format. */
    memset(buffer, 0, NM_MAX_LEN_BUF);

    /* Write IP address to the buffer. */
    strcat(buffer, ipvx.ip_address);
    strcat(buffer, "/");

    /* Write netmask to the buffer. */
    sprintf(addr, "%d", ipvx.masklen);
    strcat(buffer, addr);

    /* Write gateway address to the buffer. */
    if (!empty_str(ipvx.gateway)) {
        strcat(buffer, ",");
        strcat(buffer, ipvx.gateway);
    }

    /* Write config to the configuration file. */
    fprintf(config_file, "address1=%s\n", buffer);
}

void nm_write_ipv4(FILE *config_file, nm_ipvX ipv4)
{
    fprintf(config_file, "\n%s\n", NM_SETTINGS_IPV4);

    if (ipv4.method == AUTO) {
        fprintf(config_file, "method=%s\n", "auto");
    }
    else {
        fprintf(config_file, "method=%s\n", "manual");
        nm_write_static_ipvX(config_file, ipv4);
    }
}

void nm_write_ipv6(FILE *config_file, nm_ipvX ipv6)
{
    fprintf(config_file, "\n%s\n", NM_SETTINGS_IPV6);

    if (ipv6.method == AUTO) {
        fprintf(config_file, "method=%s\n", "auto");
        fprintf(config_file, "ip6-privacy=2\n");
    }
    else if (ipv6.method == MANUAL) {
        fprintf(config_file, "method=%s\n", "manual");
        nm_write_static_ipvX(config_file, ipv6);
    }
    else if (ipv6.method == IGNORE) {
        fprintf(config_file, "method=%s\n", "ignore");
    }
}

/* Write Network Manager config file. */
void nm_write_configuration(struct nm_config_info nmconf)
{
    FILE    *config_file;
    char    buffer[NM_MAX_LEN_BUF];

    /* Create the directory for the config file and clear any possible
     * previous files found there. */
    sprintf(buffer, "mkdir -p %s", NM_CONFIG_FILE_PATH);
    di_exec_shell(buffer);

    /* If the directory exist mkdir will do nothing, so just remove every file
     * there. Rely on the fact that for now netcfg only does config for one
     * interface. */
    sprintf(buffer, "rm %s/*", NM_CONFIG_FILE_PATH);
    di_exec_shell(buffer);

    /* Open file using its full path. */
    sprintf(buffer, "%s/%s", NM_CONFIG_FILE_PATH, nmconf.connection.id);
    config_file = fopen(buffer, "w");

    if (config_file == NULL) {
        di_info("Unable to open file for writing network-manager "
                "configuration. The connection id (%s) might not be "
                "set to a proper value.", nmconf.connection.id);
        return;
    }

    if (fchmod(fileno(config_file), 0600) != 0) {
        di_error("network-manager connection file cannot be protected "
                 "from reading: %s", strerror(errno));
        exit(1);
    }

    nm_write_connection(config_file, nmconf.connection);

    if (nmconf.connection.type == WIRED) {
        nm_write_wired_specific_options(config_file, &nmconf);
    }
#ifdef WIRELESS
    else {
        nm_write_wireless_specific_options(config_file, &nmconf);
        if (nmconf.wireless.is_secured) {
            nm_write_wireless_security(config_file, nmconf.wireless_security);
        }
    }
#endif

    nm_write_ipv4(config_file, nmconf.ipv4);
    nm_write_ipv6(config_file, nmconf.ipv6);

    fclose(config_file);

    nm_write_connection_type(nmconf);
}

/* Write info about how the network was configured to a specific file, in
 * order to be used in the finish install script. */
void nm_write_connection_type(struct nm_config_info nmconf)
{
    FILE *f = fopen(NM_CONNECTION_FILE, "w");

    if (nmconf.connection.type == WIFI) {
        fprintf(f, "connection type: wireless\n");
    }
    else {
        fprintf(f, "connection type: wired\n");
    }

    if (nmconf.connection.type == WIFI && nmconf.wireless.is_secured) {
        fprintf(f, "security: secured\n");
    }
    else {
        fprintf(f, "security: unsecured\n");
    }

    fclose(f);
}

/* Functions for extracting information from netcfg variables. */

/* Get info for the connection setting for wireless networks. */

#ifdef WIRELESS
void nm_get_wireless_connection(struct netcfg_interface *niface, nm_connection *connection)
{
    /* Use the wireless network name for connection id. */
    snprintf(connection->id, NM_MAX_LEN_ID, "%s", niface->essid);

    /* Generate uuid. */
    get_uuid(connection->uuid);

    connection->type = WIFI;
}
#endif

/* Get info for the connection setting for wired networks. */
void nm_get_wired_connection(nm_connection *connection)
{
    /* This is the first wired connection. */
    snprintf(connection->id, NM_MAX_LEN_ID, NM_DEFAULT_WIRED_NAME);

    /* Generate uuid. */
    get_uuid(connection->uuid);

    connection->type = WIRED;
}

/* Get MAC address from default file. */
void nm_get_mac_address(char *interface, char *mac_addr)
{
    char    file_name[NM_MAX_LEN_PATH];
    FILE    *file;

    snprintf(file_name, NM_MAX_LEN_PATH, NM_DEFAULT_PATH_FOR_MAC, interface);
    file = fopen(file_name, "r");

    if (file == NULL) {
        mac_addr[0] = '\0';   /* Empty string means don't write MAC. */
    }
    else {
        int i;

        if (fscanf(file, "%s\n", mac_addr) > 0) {
            /* Should be upper case. */
            for (i = 0; mac_addr[i]; i++) {
                mac_addr[i] = toupper(mac_addr[i]);
            }
        }
    }
}

#ifdef WIRELESS
void nm_get_wireless_specific_options(struct netcfg_interface *niface, nm_wireless *wireless)
{
    strncpy(wireless->ssid, niface->essid, NM_MAX_LEN_SSID);

    nm_get_mac_address(niface->name, wireless->mac_addr);

    /* Decide mode. */
    if (niface->mode == ADHOC) {
        wireless->mode = AD_HOC;
    }
    else {
        wireless->mode = INFRASTRUCTURE;
    }

    /* In netcfg, you have to chose WEP and leave the key empty for an
     * unsecure connection. */
    if (niface->wifi_security == REPLY_WEP && niface->wepkey == NULL) {
        wireless->is_secured = FALSE;
    }
    else {
        wireless->is_secured = TRUE;
    }
}
#endif

/* Only set MAC address, the others have good defaults in NM. */
void nm_get_wired_specific_options(struct netcfg_interface *niface, nm_wired *wired)
{
    nm_get_mac_address(niface->name, wired->mac_addr);
}

/* Security type for wireless networks. */
#ifdef WIRELESS
void nm_get_wireless_security(struct netcfg_interface *niface, nm_wireless_security *wireless_security)
{
    if (niface->wifi_security == REPLY_WPA) {
        wireless_security->key_mgmt = WPA_PSK;
        memset(wireless_security->psk, 0, NM_MAX_LEN_WPA_PSK);
        strncpy(wireless_security->psk, niface->passphrase, NM_MAX_LEN_WPA_PSK - 1);
    }
    else {
        wireless_security->key_mgmt = WEP_KEY;
        memset(wireless_security->wep_key0, 0, NM_MAX_LEN_WEP_KEY);
        iw_in_key(niface->wepkey, wireless_security->wep_key0);

        /* Only options supported by netcfg for now. */
        wireless_security->wep_key_type = HEX_ASCII;
        wireless_security->auth_alg = OPEN;
    }
}
#endif

/* Save IPv4 settings. */
void nm_get_ipv4(struct netcfg_interface *niface, nm_ipvX *ipv4)
{
    /* DHCP wasn't used and there is no IPv4 address saved => didn't use ipv4
     * so won't use it in the future. */
    if (niface->dhcp == 0 && niface->address_family != AF_INET) {
        ipv4->used = 0;
    }
    else {
        ipv4->used = 1;
    }

    if (niface->dhcp == 1) {
        ipv4->method = AUTO;
    }
    else if (niface->address_family == AF_INET) {
        int i;

        ipv4->method = MANUAL;
        ipv4->ip_address = niface->ipaddress;
        ipv4->gateway = niface->gateway;
        ipv4->masklen = niface->masklen;

        for (i = 0; i < NETCFG_NAMESERVERS_MAX; i++) {
            ipv4->nameservers[i] = niface->nameservers[i];
        }
    }
    else {
        /* IPv4 might always be activated in the future. */
        ipv4->method = AUTO;
    }
}

/* For the moment, just set it to ignore. */
void nm_get_ipv6(struct netcfg_interface *niface, nm_ipvX *ipv6)
{
    /* No IPv6 address, no dhcpv6, nor slaac, so wasn't used. */
    if (niface->address_family != AF_INET6 && niface->dhcpv6 == 0 &&
            niface->slaac == 0) {
        ipv6->used = 0;
    }
    else {
        ipv6->used = 1;
    }

    if (niface->dhcpv6 == 1 || niface->slaac == 1) {
        ipv6->method = AUTO;
    }
    else if (niface->address_family == AF_INET6) {
        int i;

        ipv6->method = MANUAL;

        ipv6->ip_address = niface->ipaddress;
        ipv6->gateway = niface->gateway;
        ipv6->masklen = niface->masklen;

        for (i = 0; i < NETCFG_NAMESERVERS_MAX; i++) {
            ipv6->nameservers[i] = niface->nameservers[i];
        }
    }
    else {
        /* IPv6 might always be activated in the future. */
        ipv6->method = AUTO;
    }

}

/* Extract all configs for a wireless interface, from both global netcfg
 * values and other resources. */
#ifdef WIRELESS
void nm_get_wireless_config(struct netcfg_interface *niface, struct nm_config_info *nmconf)
{
    nm_get_wireless_connection(niface, &(nmconf->connection));
    nm_get_wireless_specific_options(niface, &(nmconf->wireless));

    if (nmconf->wireless.is_secured == TRUE) {
        nm_get_wireless_security(niface, &(nmconf->wireless_security));
    }

    nm_get_ipv4(niface, &(nmconf->ipv4));
    nm_get_ipv6(niface, &(nmconf->ipv6));
}
#endif

/* Extract all configs for a wired interface. */
void nm_get_wired_config(struct netcfg_interface *niface, struct nm_config_info *nmconf)
{
    nm_get_wired_connection(&(nmconf->connection));
    nm_get_wired_specific_options(niface, &(nmconf->wired));
    nm_get_ipv4(niface, &(nmconf->ipv4));
    nm_get_ipv6(niface, &(nmconf->ipv6));
}

/* Getting configurations for NM relies on netcfrg global variables. */
void nm_get_configuration(struct netcfg_interface *niface, struct nm_config_info *nmconf)
{
    /* Decide if wireless configuration is needed. */
    if (!is_wireless_iface(niface->name)) {
        nm_get_wired_config(niface, nmconf);
    }
#ifdef WIRELESS
    else {
        nm_get_wireless_config(niface, nmconf);
    }
#endif
    if (nmconf->ipv4.method == MANUAL || nmconf->ipv6.method == MANUAL) {
        /* Manual address family configuration should be bound to a MAC
         * address. Hence record this fact globally for the connection. */
        nmconf->connection.manual = 1;
    }
    else {
        nmconf->connection.manual = 0;
    }
}

