
#ifndef _NM_CONF_H
#define _NM_CONF_H

#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <ctype.h>
#include <debian-installer.h>

#ifdef WIRELESS
#include <iwlib.h>
#endif

/* Global variables. */
#include "netcfg.h"

/* Constants for maximum size for Network Manager config fields. */
#define NM_MAX_LEN_BUF          1024 /* Max len for most buffers */
#define NM_MAX_LEN_ID           128
#define NM_MAX_LEN_SSID         128
#define NM_MAX_LEN_MAC_ADDR     20   /* AA:BB:CC:DD:EE:FF format */
#define NM_MAX_LEN_IPV4         20   /* x.x.x.x format */
#define NM_MAX_LEN_WPA_PSK      65   /* 64 standard + NULL char */
#define NM_MAX_LEN_WEP_KEY      30   /* Rough estimation (should be 26) */
#define NM_MAX_LEN_PATH         128  /* Assume a path won't be longer */
#define NM_MAX_LEN_UUID         37
#define NM_NO_BITS_IPV4         32


/* Some Network Manager default values for connection types. */
#define NM_DEFAULT_WIRED                "802-3-ethernet"
#define NM_DEFAULT_WIRED_NAME           "Wired connection 1"
#define NM_DEFAULT_WIRELESS             "802-11-wireless"
#define NM_DEFAULT_WIRELESS_SECURITY    "802-11-wireless-security"
#define NM_DEFAULT_PATH_FOR_MAC         "/sys/class/net/%s/address"
#define NM_CONFIG_FILE_PATH             "/etc/NetworkManager/system-connections"
#define NM_CONNECTION_FILE              "/tmp/connection_type"

#define NM_SETTINGS_CONNECTION          "[connection]"
#define NM_SETTINGS_WIRELESS            "["NM_DEFAULT_WIRELESS"]"
#define NM_SETTINGS_WIRED               "["NM_DEFAULT_WIRED"]"
#define NM_SETTINGS_WIRELESS_SECURITY   "["NM_DEFAULT_WIRELESS_SECURITY"]"
#define NM_SETTINGS_IPV4                "[ipv4]"
#define NM_SETTINGS_IPV6                "[ipv6]"


/* Minimalist structures for storing basic elements in order to write a Network
 * Manager format config file.
 *
 * See full specifications at:
 *
 * http://projects.gnome.org/NetworkManager/developers/settings-spec-08.html
 *
 */
typedef struct nm_connection
{
    char id[NM_MAX_LEN_ID];
    char uuid[NM_MAX_LEN_UUID];
    enum {WIRED, WIFI} type;
    int manual; /* 1 = true, 0 = false */
} nm_connection;

typedef struct nm_wired
{
    char                            mac_addr[NM_MAX_LEN_MAC_ADDR];
}   nm_wired;

typedef struct nm_wireless
{
    char                            ssid[NM_MAX_LEN_SSID];
    char                            mac_addr[NM_MAX_LEN_MAC_ADDR];
    enum {AD_HOC, INFRASTRUCTURE}   mode;
    enum {FALSE = 0, TRUE = 1}      is_secured; /* 1 = secure, 0 = unsecure */
}   nm_wireless;

typedef struct nm_wireless_security
{
    enum {WEP_KEY, WPA_PSK}         key_mgmt;

    union
    {
        char                psk[NM_MAX_LEN_WPA_PSK];
        struct
        {
            enum {HEX_ASCII = 1, PASSPHRASE = 2}  wep_key_type;
            enum {OPEN, SHARED}                   auth_alg;
            unsigned char                         wep_key0[NM_MAX_LEN_WEP_KEY];
        };
    };
}   nm_wireless_security;

typedef struct nm_ipvX
{
    int                             used;   /* 1 = true, 0 = false */
    enum {AUTO, MANUAL, IGNORE}     method;
    char *                          ip_address;
    char *                          gateway;
    char *                          nameservers[NETCFG_NAMESERVERS_MAX];
    unsigned int                    masklen;
}   nm_ipvX;


typedef struct nm_config_info
{
    nm_connection           connection;
    nm_wired                wired;
    nm_wireless             wireless;
    nm_wireless_security    wireless_security;
    nm_ipvX                 ipv4;
    nm_ipvX                 ipv6;
}   nm_config_info;

/* Here come functions: */

#ifdef WIRELESS
void nm_write_wireless_specific_options(FILE *config_file,
        struct nm_config_info *nmconf);
void nm_write_wireless_security(FILE *config_file, nm_wireless_security
        wireless_security);
#endif
void nm_write_connection(FILE *config_file, nm_connection connection);
void nm_write_wired_specific_options(FILE *config_file,
        struct nm_config_info *nmconf);
void nm_write_ipv4(FILE *config_file, nm_ipvX ipv4);
void nm_write_ipv6(FILE *config_file, nm_ipvX ipv6);

void nm_write_configuration(struct nm_config_info nmconf);

void nm_write_connection_type(struct nm_config_info nmconf);


#ifdef WIRELESS
void nm_get_wireless_connection(struct netcfg_interface *niface, nm_connection *connection);
void nm_get_wireless_specific_options(struct netcfg_interface *niface, nm_wireless *wireless);
void nm_get_wireless_security(struct netcfg_interface *niface, nm_wireless_security *wireless_security);
#endif
void nm_get_wired_connection(nm_connection *connection);
void nm_get_mac_address(char *interface, char *mac_addr);
void nm_get_wired_specific_options(struct netcfg_interface *niface, nm_wired *wired);
void nm_get_ipv4(struct netcfg_interface *niface, nm_ipvX *ipv4);
void nm_get_ipv6(struct netcfg_interface *niface, nm_ipvX *ipv6);

#ifdef WIRELESS
void nm_get_wireless_config(struct netcfg_interface *niface, struct nm_config_info *nmconf);
#endif
void nm_get_wired_config(struct netcfg_interface *niface, struct nm_config_info *nmconf);

void nm_get_configuration(struct netcfg_interface *niface, struct nm_config_info *nmconf);

#endif

