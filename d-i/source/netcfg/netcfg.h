#ifndef _NETCFG_H_
#define _NETCFG_H_

#define INTERFACES_FILE "/etc/network/interfaces"
#define HOSTS_FILE      "/etc/hosts"
#define HOSTNAME_FILE   "/etc/hostname"
#define NETWORKS_FILE   "/etc/networks"
#define RESOLV_FILE     "/etc/resolv.conf"
#define DHCLIENT_CONF   "/etc/dhclient.conf"
#define DOMAIN_FILE     "/tmp/domain_name"
#define NTP_SERVER_FILE "/tmp/dhcp-ntp-servers"
#define WPASUPP_CTRL    "/var/run/wpa_supplicant"
#define WPAPID          "/var/run/wpa_supplicant.pid"

#define DHCLIENT6_FILE  "/var/lib/netcfg/dhclient6.conf"
#define DHCP6C_FILE     "/var/lib/netcfg/dhcp6c.conf"

#define DEVNAMES	"/etc/network/devnames"
#define DEVHOTPLUG	"/etc/network/devhotplug"
#ifdef __linux__
#define STAB		"/var/run/stab"
#endif

#define WPA_MIN         8    /* minimum passphrase length */
#define WPA_MAX         64   /* maximum passphrase length */

#define _GNU_SOURCE

#include <sys/types.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <cdebconf/debconfclient.h>

#ifndef ARRAY_SIZE
# define ARRAY_SIZE(x) (sizeof(x) / sizeof(x[0]))
#endif

#define empty_str(s) (s != NULL && *s == '\0')

#define IPV6_HOSTS \
"# The following lines are desirable for IPv6 capable hosts\n" \
"::1     localhost ip6-localhost ip6-loopback\n" \
"ff02::1 ip6-allnodes\n" \
"ff02::2 ip6-allrouters\n"

/* The number of times to attempt to verify gateway reachability.
 * Each try invokes arping with a one second timeout.
 */
#define NETCFG_GATEWAY_REACHABILITY_TRIES 50

#ifndef MAXHOSTNAMELEN
#define MAXHOSTNAMELEN 63
#endif

#define RETURN_TO_MAIN 10
#define CONFIGURE_MANUALLY 15

typedef enum { NOT_ASKED = 30, GO_BACK, REPLY_WEP, REPLY_WPA } response_t;
typedef enum { DHCP, STATIC, DUNNO } method_t;
typedef enum { ADHOC = 1, MANAGED = 2 } wifimode_t;
typedef enum { WPA_OK, WPA_QUEUED, WPA_UNAVAIL } wpa_t;

extern int wfd, skfd;
extern int input_result;
extern int have_domain;

/* network config */
extern char hostname[MAXHOSTNAMELEN + 1];
extern char domain[MAXHOSTNAMELEN + 1];

/* wireless */
extern char *essid, *wepkey, *passphrase;
extern wifimode_t mode;

/* Determine which of INET_ADDRSTRLEN or INET6_ADDRSTRLEN is longer
 * (yeah, take a wild guess who'll win *that* one) and make that
 * the string length.  This makes sure that any string defined to
 * be NETCFG_ADDRSTRLEN bytes long is guaranteed to be able to
 * accomodate either an IPv4 or IPv6 address.
 */
#define NETCFG_ADDRSTRLEN ((INET_ADDRSTRLEN < INET6_ADDRSTRLEN) ? INET6_ADDRSTRLEN : INET_ADDRSTRLEN)

/* The maximum number of nameservers and NTP servers we'll store in the
 * interface.
 */
#define NETCFG_NAMESERVERS_MAX	4
#define NETCFG_NTPSERVERS_MAX	4

/* The information required to configure a network interface. */
struct netcfg_interface {
	char *name;
	
	/* Is this a loopback interface?
	 * -1 if unknown, 0 if no, 1 if yes */
	int loopback;

	/* Was this interface configured with DHCP?
	 * -1 if unknown, 0 if no, 1 if yes */
	int dhcp;
	
	/* Was this interface configured using stateful DHCPv6?
	 */
	int dhcpv6;

	/* Address family of the address we're configuring; AF_INET or AF_INET6 */
	int address_family;

	/* Did the interface get an IPv6 address/gateway via SLAAC?
	 * T (1) / F (0) / unknown (-1) */
	int slaac;
	
	/* Did the RA indicate that we should use stateful address
	 * configuration?  T/F/?
	 */
	int v6_stateful_config;
	
	/* Did the RA indicate that we should use stateless auxiliary
	 * config (DNS, NTP, etc)?  T/F/?
	 */
	int v6_stateless_config;
	
	/* The list of nameservers this interface has asked us to
	 * use.
	 */
	char nameservers[NETCFG_NAMESERVERS_MAX][NETCFG_ADDRSTRLEN];

	/* The list of NTP servers this interface has asked us to
	 * use.  Interestingly, the DHCP specs only allow NTP servers by
	 * IP address, not hostname, hence the use of NETCFG_ADDRSTRLEN.
	 */
	char ntp_servers[NETCFG_NTPSERVERS_MAX][NETCFG_ADDRSTRLEN];

	/* The 'hostname' we want to send to the DHCP server so it'll give
	 * us a/the right lease.
	 */
	char dhcp_hostname[MAXHOSTNAMELEN];
	
	char ipaddress[NETCFG_ADDRSTRLEN];
	unsigned int masklen;
	char gateway[NETCFG_ADDRSTRLEN];
	char pointopoint[INET_ADDRSTRLEN];

	/* Wireless mode */
	wifimode_t mode;

	/* Wireless configuration */
        response_t wifi_security;
	char *wepkey;
	char *essid;

	/* WPA */
	wpa_t wpa_supplicant_status;
	char *passphrase;
};

/* Somewhere we can store both in_addr and in6_addr; convenient for all those
 * places you couldn't be bothered to deal with it yourself manually.
 */
union inX_addr {
	struct in_addr in4;
	struct in6_addr in6;
};

/* Set default values for all netcfg_interface parameters */
extern void netcfg_interface_init(struct netcfg_interface *iface);

/* common functions */
extern int check_kill_switch (const char *if_name);

extern int is_interface_up (const char *if_name);

extern int get_all_ifs (int all, char ***ptr);

extern char *get_ifdsc (struct debconfclient *client, const char *if_name);

extern FILE *file_open (char *path, const char *opentype);

extern void netcfg_die (struct debconfclient *client);

extern int netcfg_get_interface(struct debconfclient *client, char **if_name, int *num_interfaces, const char *defif);

extern short valid_hostname (const char *hname);
extern short valid_domain (const char *dname);

extern int netcfg_get_hostname(struct debconfclient *client, char *template, char *hostname, short hdset);

extern int netcfg_get_nameservers (struct debconfclient *client, char **nameservers, char *default_nameservers);

extern int netcfg_get_domain(struct debconfclient *client,  char domain[], const char *priority);

extern int netcfg_get_static(struct debconfclient *client, struct netcfg_interface *interface);

extern int netcfg_activate_dhcp(struct debconfclient *client, struct netcfg_interface *interface);

extern int nameserver_count (const struct netcfg_interface *interface);

extern int read_resolv_conf_nameservers (char *resolv_conf_file, struct netcfg_interface *interface);

extern void sigchld_handler (int sig __attribute__ ((unused)));

extern int ask_dhcp_options (struct debconfclient *client, const char *if_name);

extern void netcfg_write_loopback (void);
extern void netcfg_write_common (const char *ipaddress, const char *hostname, const char *domain);

void netcfg_nameservers_to_array(const char *nameservers, struct netcfg_interface *interface);

extern int is_wireless_iface (const char *if_name);
extern int netcfg_wireless_set_essid (struct debconfclient *client, struct netcfg_interface *interface);
extern int netcfg_wireless_set_wep (struct debconfclient *client, struct netcfg_interface *interface);
extern int wireless_security_type (struct debconfclient *client, const char *if_name);
extern int netcfg_set_passphrase (struct debconfclient *client, struct netcfg_interface *interface);
extern int init_wpa_supplicant_support (struct netcfg_interface *interface);
extern int kill_wpa_supplicant (void);

extern int wpa_supplicant_start (struct debconfclient *client, const struct netcfg_interface *interface);
extern int iface_is_hotpluggable(const char *if_name);
extern short find_in_stab (const char *if_name);
extern void deconfigure_network(struct netcfg_interface *iface);

extern void interface_up (const char *if_name);
extern void interface_down (const char *if_name);

extern void loop_setup(void);
extern int get_hostname_from_dns(const struct netcfg_interface *interface, char *hostname, const size_t max_hostname_len);

extern int inet_ptom (int af, const char *src, unsigned int *dst);
extern const char *inet_mtop (int af, unsigned int src, char *dst, socklen_t dst_len);
extern void inet_mton (int af, unsigned int src, void *dst);

extern void parse_args (int argc, char** argv);
extern void open_sockets (void);
extern void reap_old_files (void);

extern void netcfg_update_entropy (void);

extern int netcfg_write_resolv (const char *domain, const struct netcfg_interface *interface);

extern int ethtool_lite (const char *if_name);
extern int netcfg_detect_link(struct debconfclient *client, const struct netcfg_interface *interface);

extern int netcfg_parse_cidr_address(const char *address, struct netcfg_interface *interface);
extern void netcfg_network_address(const struct netcfg_interface *interface, char *network);
extern void netcfg_broadcast_address(const struct netcfg_interface *interface, char *broadcast);
extern int netcfg_gateway_reachable(const struct netcfg_interface *interface);

extern void preseed_hostname_from_fqdn(struct debconfclient *client, char *fqdn);

extern int netcfg_dhcp(struct debconfclient *client, struct netcfg_interface *interface);

extern void rtrim(char *);

/* ipv6.c */
extern void nc_v6_wait_for_complete_configuration(const struct netcfg_interface *interface);
extern int nc_v6_interface_configured(const struct netcfg_interface *interface, const int link_local);
extern int nc_v6_get_config_flags(struct debconfclient *client, struct netcfg_interface *interface);

/* write_interfaces.c */
extern int netcfg_write_interface(const struct netcfg_interface *interface);

/* rdnssd.c */
extern int start_rdnssd(struct debconfclient *client);
extern void cleanup_rdnssd(void);
extern void stop_rdnssd(void);
extern void read_rdnssd_nameservers(struct netcfg_interface *interface);

/* autoconfig.c */
extern void cleanup_dhcpv6_client(void);
extern int start_dhcpv6_client(struct debconfclient *client, const struct netcfg_interface *interface);
extern int netcfg_autoconfig(struct debconfclient *client, struct netcfg_interface *interface);

#endif /* _NETCFG_H_ */
