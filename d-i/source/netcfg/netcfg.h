#ifndef _NETCFG_H_
#define _NETCFG_H_

#define INTERFACES_FILE "/etc/network/interfaces"
#define HOSTS_FILE      "/etc/hosts"
#define HOSTNAME_FILE   "/etc/hostname"
#define NETWORKS_FILE   "/etc/networks"
#define RESOLV_FILE     "/etc/resolv.conf"
#define DHCLIENT_CONF	"/etc/dhclient.conf"
#define DOMAIN_FILE     "/tmp/domain_name"
#define NTP_SERVER_FILE "/tmp/dhcp-ntp-servers"

#define DEVNAMES	"/etc/network/devnames"
#define DEVHOTPLUG	"/etc/network/devhotplug"
#ifdef __linux__
#define STAB		"/var/run/stab"
#endif

#define _GNU_SOURCE

#include <sys/types.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <cdebconf/debconfclient.h>

#ifndef ARRAY_SIZE
# define ARRAY_SIZE(x) (sizeof(x) / sizeof(x[0]))
#endif

#define empty_str(s) (s != NULL && *s == '\0')

#define HELPFUL_COMMENT \
"# This file describes the network interfaces available on your system\n" \
"# and how to activate them. For more information, see interfaces(5).\n"

#define IPV6_HOSTS \
"# The following lines are desirable for IPv6 capable hosts\n" \
"::1     ip6-localhost ip6-loopback\n" \
"fe00::0 ip6-localnet\n" \
"ff00::0 ip6-mcastprefix\n" \
"ff02::1 ip6-allnodes\n" \
"ff02::2 ip6-allrouters\n"

/* The time, in seconds, that we will wait for a link to be established
 * via link autonegotiation.  Sometime in the future this may become a
 * preseed option.
 */
#define NETCFG_LINK_WAIT_TIME 3

#ifndef MAXHOSTNAMELEN
#define MAXHOSTNAMELEN 63
#endif

typedef enum { NOT_ASKED = 30, GO_BACK } response_t;
typedef enum { DHCP, STATIC, DUNNO } method_t;
typedef enum { ADHOC = 1, MANAGED = 2 } wifimode_t;

extern int netcfg_progress_displayed;
extern int wfd, skfd;
extern int input_result;
extern int have_domain;

/* network config */
extern char *interface;
extern char *hostname;
extern char *dhcp_hostname;
extern char *domain;
extern struct in_addr ipaddress;
extern struct in_addr nameserver_array[4];
extern struct in_addr network;
extern struct in_addr broadcast;
extern struct in_addr netmask;
extern struct in_addr gateway;
extern struct in_addr pointopoint;

/* wireless */
extern char *essid, *wepkey;
extern wifimode_t mode;

/* common functions */
extern int check_kill_switch (const char *iface);

extern int is_interface_up (char *inter);

extern void get_name (char *name, char *p);

extern int get_all_ifs (int all, char ***ptr);

extern char *get_ifdsc (struct debconfclient *client, const char *ifp);

extern FILE *file_open (char *path, const char *opentype);

extern void netcfg_die (struct debconfclient *client);

extern int netcfg_get_interface(struct debconfclient *client, char **interface, int *num_interfaces, char* defif);

extern short valid_hostname (const char *hname);
extern short valid_domain (const char *dname);

extern int netcfg_get_hostname(struct debconfclient *client, char *template, char **hostname, short hdset);

extern int netcfg_get_nameservers (struct debconfclient *client, char **nameservers);

extern int netcfg_get_domain(struct debconfclient *client,  char **domain, const char *priority);

extern int netcfg_get_static(struct debconfclient *client);

extern int netcfg_activate_dhcp(struct debconfclient *client);

extern int resolv_conf_entries (void);

extern int read_resolv_conf_nameservers (struct in_addr array[]);

extern int ask_dhcp_options (struct debconfclient *client);
extern int netcfg_activate_static(struct debconfclient *client);

extern void netcfg_write_loopback (void);
extern void netcfg_write_common (struct in_addr ipaddress, char *hostname,
				 char *domain);

void netcfg_nameservers_to_array(char *nameservers, struct in_addr array[]);

extern int is_wireless_iface (const char* iface);

extern int netcfg_wireless_set_essid (struct debconfclient *client, char* iface, char* priority);
extern int netcfg_wireless_set_wep (struct debconfclient *client, char* iface);

extern int iface_is_hotpluggable(const char *iface);
extern short find_in_stab (const char *iface);
extern void deconfigure_network(void);

extern void interface_up (char*);
extern void interface_down (char*);

extern void loop_setup(void);
extern void seed_hostname_from_dns(struct debconfclient *client, struct in_addr * ipaddress);

extern int inet_ptom (const char *src, int *dst, struct in_addr * addrp);
extern const char *inet_mtop (int src, char *dst, socklen_t cnt);

extern void parse_args (int argc, char** argv);
extern void open_sockets (void);
extern void reap_old_files (void);

extern void netcfg_update_entropy (void);

extern int netcfg_write_resolv (char*, struct in_addr *);

extern int ethtool_lite (const char *if_name);
extern int netcfg_detect_link(struct debconfclient *client, const char *if_name);

#endif /* _NETCFG_H_ */
