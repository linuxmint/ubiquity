/* 
   netcfg-common.c - Shared functions used to configure the network for 
   the debian-installer.

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

#include "netcfg.h"
#if defined(WIRELESS)
#include <iwlib.h>
#endif
#include <net/if_arp.h>
#include <net/if.h>
#include <errno.h>
#include <assert.h>
#include <ctype.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <cdebconf/debconfclient.h>
#include <debian-installer.h>
#include <time.h>
#include <netdb.h>

#include <ifaddrs.h>

/* Set if there is currently a progress bar displayed. */
int netcfg_progress_displayed = 0;

/* IP address vars */
struct in_addr ipaddress = { 0 };
struct in_addr gateway = { 0 };
struct in_addr nameserver_array[4] = { { 0 }, };

/* network config */
char *interface = NULL;
char *hostname = NULL;
char *domain = NULL;
int have_domain = 0;

/* File descriptors for ioctls and such */
int skfd = 0;
#ifdef WIRELESS
int wfd = 0;
#endif

/* convert a netmask (255.255.255.0) into the length (24) */
int inet_ptom (const char *src, int *dst, struct in_addr *addrp)
{
    struct in_addr newaddr, *addr;
    in_addr_t mask, num;
    
    if (src && !addrp) {
        if (inet_pton (AF_INET, src, &newaddr) < 0)
            return 0;
        addr = &newaddr;
    }
    else
        addr = addrp;
    
    mask = ntohl(addr->s_addr);

    for (num = mask; num & 1; num >>= 1);
    
    if (num != 0 && mask != 0) {
        for (num = ~mask; num & 1; num >>= 1);
        if (num)
            return 0;
    }
    
    for (num = 0; mask; mask <<= 1)
        num++;
    
    *dst = num;
    
    return 1;
}

/* convert a length (24) into the netmask (255.255.255.0) */
const char *inet_mtop (int src, char *dst, socklen_t cnt)
{
    struct in_addr addr;
    in_addr_t mask = 0;
    
    for(; src; src--)
        mask |= 1 << (32 - src);
    
    addr.s_addr = htonl(mask);
    
    return inet_ntop (AF_INET, &addr, dst, cnt);
}

void open_sockets (void)
{
#ifdef WIRELESS
    wfd = iw_sockets_open();
#endif
    skfd = socket (AF_INET, SOCK_DGRAM, 0);
}

#ifdef __linux__

#define SYSCLASSNET "/sys/class/net/"

/* Returns non-zero if this interface has an enabled kill switch, otherwise
 * zero.
 */
int check_kill_switch(const char *iface)
{
    char *temp, *linkbuf;
    const char *killname;
    char killstate;
    size_t len;
    int linklen, killlen;
    int fd = -1;
    int ret = 0;
    
    /* longest string we need */
    len = strlen(SYSCLASSNET) + strlen(iface) + strlen("/device/rf_kill") + 1;
    
    temp = malloc(len);
    snprintf(temp, len, SYSCLASSNET "%s/driver", iface);
    linkbuf = malloc(1024); /* probably OK ... I hate readlink() */
    linklen = readlink(temp, linkbuf, 1024);
    if (linklen < 0)
        goto out;
    
    if (strncmp(linkbuf + linklen - 8, "/ipw2100", 8) == 0)
        killname = "rf_kill";
    else if (strncmp(linkbuf + linklen - 8, "/ipw2200", 8) == 0)
        killname = "rf_kill";
    else
        goto out;
    
    snprintf(temp, len, SYSCLASSNET "%s/device/%s", iface, killname);
    di_info("Checking RF kill switch: %s", temp);
    fd = open(temp, O_RDONLY);
    if (fd == -1)
        goto out;
    killlen = read(fd, &killstate, 1);
    if (killlen < 0) {
        di_error("Failed to read RF kill state: %s", strerror(errno));
        goto out;
    } else if (killlen == 0) {
        di_warning("RF kill state file empty");
        goto out;
    }
    
    if (killstate == '2') {
        di_info("RF kill switch enabled");
        ret = 1;
    }
    
 out:
    free(temp);
    free(linkbuf);
    if (fd != -1)
        close(fd);
    return ret;
}

#undef SYSCLASSNET

#else /* !__linux__ */
int check_kill_switch(const char *iface)
{
    return 0;
}
#endif /* __linux__ */

#if defined(WIRELESS)
int is_raw_80211(const char *iface)
{
    struct ifreq ifr;
    struct sockaddr sa;
    
    strncpy(ifr.ifr_name, iface, IFNAMSIZ);
    
    if (skfd && ioctl(skfd, SIOCGIFHWADDR, &ifr) < 0) {
        di_warning("Unable to retrieve interface type.");
        return 0;
    }

    sa = * (struct sockaddr *) &ifr.ifr_hwaddr;
    switch (sa.sa_family) {
    case ARPHRD_IEEE80211:
    case ARPHRD_IEEE80211_PRISM:
    case ARPHRD_IEEE80211_RADIOTAP:
        return 1;

    default:
        return 0;
    }
}
#endif

int qsort_strcmp(const void *a, const void *b)
{
    const char **ia = (const char **)a;
    const char **ib = (const char **)b;
    return strcmp(*ia, *ib);
}

int get_all_ifs (int all, char*** ptr)
{
    struct ifaddrs *ifap, *ifa;
    char ibuf[512];
    char** list = NULL;
    size_t len = 0;
    
    if (getifaddrs(&ifap) == -1)
        return 0;

    for (ifa = ifap; ifa; ifa = ifa->ifa_next) {
        strncpy(ibuf, ifa->ifa_name, sizeof(ibuf));
        if (ifa->ifa_flags & IFF_LOOPBACK)   /* ignore loopback devices */
            continue;
#if defined(__linux__)
        if (!strncmp(ibuf, "sit", 3))        /* ignore tunnel devices */
            continue;
#endif
#if defined(WIRELESS)
        if (is_raw_80211(ibuf))
            continue;
#endif
        if (all || ifa->ifa_flags & IFF_UP) {
            int found = 0;
            size_t i;

            for (i = 0 ; i < len ; i++) {
                if (!strcmp(ibuf, list[i])) {
                    found = 1;
                }
            }
            if (!found) {
                list = realloc(list, sizeof(char*) * (len + 2));
                list[len] = strdup(ibuf);
                len++;
            }
        }
    }
    
    /* OK, now sort the list and terminate it if necessary */
    if (list != NULL) {
        qsort(list, len, sizeof(char *), qsort_strcmp);
        list[len] = NULL;
    }
    freeifaddrs(ifap);
    
    *ptr = list;
    
    return len;
}

#ifdef __linux__
short find_in_stab(const char* iface)
{
    FILE *dn = NULL;
    char buf[128];
    size_t len = strlen(iface);
    
    if (access(STAB, F_OK) == -1)
        return 0;
    
    if (!(dn = popen("grep -v '^Socket' " STAB " | cut -f5", "r")))
        return 0;
    
    while (fgets (buf, 128, dn) != NULL) {
        if (!strncmp(buf, iface, len)) {
            pclose(dn);
            return 1;
        }
    }
    pclose(dn);
    return 0;
}
#else /* !__linux__ */
/* Stub function for platforms not supporting /var/run/stab. */
short find_in_stab(const char* iface)
{
    return 0;
}
#endif /* __linux__ */

char *find_in_devnames(const char* iface)
{
    FILE* dn = NULL;
    char buf[512], *result = NULL;
    size_t len = strlen(iface);
    
    if (!(dn = fopen(DEVNAMES, "r")))
        return NULL;
    
    while (fgets(buf, 512, dn) != NULL) {
        char *ptr = strchr(buf, ':'), *desc = ptr + 1;
        
        if (!ptr) {
            result = NULL; /* corrupt */
            break;
        }
        else if (!strncmp(buf, iface, len)) {
            result = strdup(desc);
            break;
        }
    }
    
    fclose(dn);
    
    if (result) {
        len = strlen(result);
        
        if (result[len - 1] == '\n')
            result[len - 1] = '\0';
    }
    
    return result;
}

char *get_ifdsc(struct debconfclient *client, const char *ifp)
{
    char template[256], *ptr = NULL;
    
    if ((ptr = find_in_devnames(ifp)) != NULL) {
        debconf_metaget(client, "netcfg/internal-wireless", "description");
        
        if (is_wireless_iface(ifp)) {
            size_t len = strlen(ptr) + strlen(client->value) + 4;
            ptr = realloc(ptr, len);
            
            di_snprintfcat(ptr, len, " (%s)", client->value);
        }
        return ptr; /* already strdup'd */
    }
    
    if (strlen(ifp) < 100) {
        if (!is_wireless_iface(ifp)) {
            /* strip away the number from the interface (eth0 -> eth) */
            char *new_ifp = strdup(ifp), *ptr = new_ifp;
            while ((*ptr < '0' || *ptr > '9') && *ptr != '\0')
                ptr++;
            *ptr = '\0';
            
            sprintf(template, "netcfg/internal-%s", new_ifp);
            free(new_ifp);
            
            if (debconf_metaget(client, template, "description") == 0 &&
                client->value != NULL) {
                return strdup(client->value);
            }
        } else {
            strcpy(template, "netcfg/internal-wifi");
            debconf_metaget(client, template, "description");
            return strdup(client->value);
        }
    }
    debconf_metaget(client, "netcfg/internal-unknown-iface", "description");
    if (client->value != NULL)
        return strdup(client->value);
    else
        return strdup("Unknown interface");
}

int iface_is_hotpluggable(const char *iface)
{
    FILE* f = NULL;
    char buf[256];
    size_t len = strlen(iface);
    
    if (!(f = fopen(DEVHOTPLUG, "r"))) {
        di_info("No hotpluggable devices are present in the system.");
        return 0;
    }
    
    while (fgets(buf, 256, f) != NULL) {
        if (!strncmp(buf, iface, len)) {
            di_info("Detected %s as a hotpluggable device", iface);
            fclose(f);
            return 1;
        }
    }
    
    fclose(f);
    
    di_info("Hotpluggable devices available, but %s is not one of them", iface);
    return 0;
}

FILE *file_open(char *path, const char *opentype)
{
    FILE *fp;
    if ((fp = fopen(path, opentype)))
        return fp;
    else {
        fprintf(stderr, "%s\n", path);
        perror("fopen");
        return NULL;
    }
}

void netcfg_die(struct debconfclient *client)
{
    if (netcfg_progress_displayed)
        debconf_progress_stop(client);
    debconf_capb(client);
    debconf_input(client, "high", "netcfg/error");
    debconf_go(client);
    exit(1);
}

/**
 * @brief Ask which interface to configure
 * @param client - client 
 * @param interface      - set to the answer
 * @param numif - number of interfaces found.
 */

int netcfg_get_interface(struct debconfclient *client, char **interface,
                         int *numif, char* defif)
{
    char *inter = NULL, **ifs;
    size_t len;
    int ret, i, asked;
    int num_interfaces = 0;
    char *ptr = NULL;
    char *ifdsc = NULL;
    char *old_selection = NULL;
    
    if (*interface) {
        free(*interface);
        *interface = NULL;
    }
    
    if (!(ptr = malloc(128)))
        goto error;
    
    len = 128;
    *ptr = '\0';
    
    num_interfaces = get_all_ifs(1, &ifs);
    
    /* If no default was provided, use the first in the list of interfaces. */
    if (! defif && num_interfaces > 0) {
        defif=ifs[0];
    }
    
    /* Remember old interface selection, in case it's preseeded. */
    debconf_get(client, "netcfg/choose_interface");
    old_selection = strdup(client->value);
    
    for (i = 0; i < num_interfaces; i++) {
        size_t newchars;
        char *temp = NULL;
        
        inter = ifs[i];
        
        interface_down(inter);
        ifdsc = get_ifdsc(client, inter);
        newchars = strlen(inter) + strlen(ifdsc) + 5; /* ": , " + NUL */
        if (len < (strlen(ptr) + newchars)) {
            if (!(ptr = realloc(ptr, len + newchars + 128)))
                goto error;
            len += newchars + 128;
        }
        
        temp = malloc(newchars);
        
        snprintf(temp, newchars, "%s: %s", inter, ifdsc);
        
        if (num_interfaces > 1 &&
            ((strcmp(defif, inter) == 0) || (strcmp(defif, temp) == 0)))
            debconf_set(client, "netcfg/choose_interface", temp);
        
        di_snprintfcat(ptr, len, "%s, ", temp);
        
        free(temp);
        free(ifdsc);
    }
    
    if (num_interfaces == 0) {
        debconf_input(client, "high", "netcfg/no_interfaces");
        ret = debconf_go(client);
        free(ptr);
        free(old_selection);
        *numif = 0;
        return ret;
    }
    else if (num_interfaces == 1) {
        inter = ptr;
        *numif = 1;
        free(old_selection);
    }
    else if (num_interfaces > 1) {
        *numif = num_interfaces;
        /* remove the trailing ", ", which confuses cdebconf */
        ptr[strlen(ptr) - 2] = '\0';
        
        debconf_subst(client, "netcfg/choose_interface", "ifchoices", ptr);
        free(ptr);
        
        asked = (debconf_input(client, "critical", "netcfg/choose_interface") == 0);
        ret = debconf_go(client);
        
        /* If the question is not asked, honor preseeded interface name.
         * However, if it was preseeded to "auto", or there was no old value,
         * leave it set to defif. */
        if (!asked && strlen(old_selection) && strcmp(old_selection, "auto") != 0) {
            debconf_set(client, "netcfg/choose_interface", old_selection);
        }
        
        free(old_selection);
        
        if (ret)
            return ret;
        
        debconf_get(client, "netcfg/choose_interface");
        inter = client->value;
        
        if (!inter)
            netcfg_die(client);
    }
    
    /* grab just the interface name, not the description too */
    *interface = inter;
    /* Note that the question may be preseeded to just the interface name,
     * with no colon after it. Allow for this case. */
    ptr = strchr(inter, ':');
    if (ptr != NULL) {
        *ptr = '\0';
    }
    *interface = strdup(*interface);
    
    /* Free allocated memory */
    while (ifs && *ifs)
        free(*ifs++);
    
    return 0;

 error:
    if (ptr)
        free(ptr);
    
    netcfg_die(client);
    return 10; /* unreachable */
}

/*
 * Verify that the hostname conforms to RFC 1123.
 * @return 0 on success, 1 on failure.
 */
short verify_hostname (char *hname)
{
    static const char *valid_chars =
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.";
    size_t len;
    assert(hname != NULL);
    
    len = strlen(hname);
    
    /* Check the hostname for RFC 1123 compliance.  */
    if ((len < 1) ||
        (len > 63) ||
        (strspn(hname, valid_chars) != len) ||
        (hname[len - 1] == '-') ||
        (hname[0] == '-')) {
        return 1;
    }
    else
        return 0;
}

/*
 * Set the hostname. 
 * @return 0 on success, 30 on BACKUP being selected.
 */
int netcfg_get_hostname(struct debconfclient *client, char *template, char **hostname, short hdset)
{
    int ret;
    char *s;
    
    for(;;) {
        if (hdset)
            have_domain = 0;
        debconf_input(client, "high", template);
        ret = debconf_go(client);
        
        if (ret == 30) /* backup */
            return ret;
        
        debconf_get(client, template);
        
        if (verify_hostname(client->value) != 0) {
            debconf_subst(client, "netcfg/invalid_hostname",
                          "hostname", client->value);
            debconf_input(client, "high", "netcfg/invalid_hostname");
            debconf_go(client);
            debconf_set(client, template, "ubuntu");
        } else {
            /* I've considered the fact that client->value could be mangled by
             * showing the error message. But if it goes through the error was not
             * shown. </careful-thinking> */
            *hostname = strdup(client->value);
            break;
        }
    }
    
    /* don't strip DHCP hostnames */
    if (hdset && (s = strchr(*hostname, '.'))) {
        if (s[1] == '\0') { /* "somehostname." <- . should be ignored */
            *s = '\0';
        } else { /* assume we have a valid domain name here */
            if (domain)
                free(domain);
            domain = strdup(s + 1);
            debconf_set(client, "netcfg/get_domain", domain);
            have_domain = 1;
            *s = '\0';
        }
    }
    return 0;
}

/* @brief Get the domainname.
 * @return 0 for success, with *domain = domain, 30 for 'goback',
 */
int netcfg_get_domain(struct debconfclient *client,  char **domain, const char *priority)
{
    int ret;
    
    if (have_domain == 1)
    {
        debconf_get(client, "netcfg/get_domain");
        assert (!empty_str(client->value));
        if (*domain)
            free(*domain);
        *domain = strdup(client->value);
        return 0;
    }

    debconf_input (client, priority, "netcfg/get_domain");
    ret = debconf_go(client);
    
    if (ret)
        return ret;
    
    debconf_get (client, "netcfg/get_domain");
    
    if (*domain)
        free(*domain);
    *domain = NULL;
    if (!empty_str(client->value)) {
        const char *start = client->value;
        while (*start == '.')
            ++start; /* trim leading dots */
        *domain = strdup(start);
    }
    return 0;
}

void netcfg_write_loopback (void)
{
    FILE *fp;
    
    if ((fp = file_open(INTERFACES_FILE, "w"))) {
        fprintf(fp, HELPFUL_COMMENT);
        fprintf(fp, "\n# The loopback network interface\n");
        fprintf(fp, "auto lo\n");
        fprintf(fp, "iface lo inet loopback\n");
        fclose(fp);
    }
}

/*
 * ipaddress.s_addr may be 0
 * domain may be null
 * interface may be null
 * hostname may _not_ be null
 */
void netcfg_write_common(struct in_addr ipaddress, char *hostname, char *domain)
{
    FILE *fp;
    
    if (!hostname)
        return;
    
    if ((fp = file_open(INTERFACES_FILE, "w"))) {
        fprintf(fp, HELPFUL_COMMENT);
        fprintf(fp, "\n# The loopback network interface\n");
        fprintf(fp, "auto lo\n");
        fprintf(fp, "iface lo inet loopback\n");
        fclose(fp);
    }
    
    /* Currently busybox, hostname is not available. */
    sethostname (hostname, strlen(hostname) + 1);
    
    if ((fp = file_open(HOSTNAME_FILE, "w"))) {
        fprintf(fp, "%s\n", hostname);
        fclose(fp);
    }
    
    if ((fp = file_open(HOSTS_FILE, "w"))) {
        char ptr1[INET_ADDRSTRLEN];
        
        fprintf(fp, "127.0.0.1\tlocalhost\n");
        
        if (ipaddress.s_addr) {
            inet_ntop (AF_INET, &ipaddress, ptr1, sizeof(ptr1));
            if (domain && !empty_str(domain))
                fprintf(fp, "%s\t%s.%s\t%s\n", ptr1, hostname, domain, hostname);
            else
                fprintf(fp, "%s\t%s\n", ptr1, hostname);
        } else {
            if (domain && !empty_str(domain))
                fprintf(fp, "127.0.1.1\t%s.%s\t%s\n", hostname, domain, hostname);
            else
                fprintf(fp, "127.0.1.1\t%s\n", hostname);
        }
        
        fprintf(fp, "\n" IPV6_HOSTS);
        
        fclose(fp);
    }
}


void deconfigure_network(void)
{
    /* deconfiguring network interfaces */
    interface_down("lo");
    interface_down(interface);
}

void loop_setup(void)
{
    static int afpacket_notloaded = 1;
    
    deconfigure_network();
    
    if (afpacket_notloaded)
        afpacket_notloaded = di_exec_shell("modprobe af_packet"); /* should become 0 */
    
    di_exec_shell_log("ip link set lo up");
    di_exec_shell_log("ip addr flush dev lo");
    di_exec_shell_log("ip addr add 127.0.0.1/8 dev lo");
}

void seed_hostname_from_dns (struct debconfclient * client, struct in_addr *ipaddr)
{
    struct sockaddr_in sin;
    char *host;
    int err;
    
    host = malloc(NI_MAXHOST);
    if (!host)
        netcfg_die(client);
    
    /* copy IP address into required format */
    sin.sin_family = AF_INET;
    sin.sin_port = 0;
    memcpy(&sin.sin_addr, ipaddr, sizeof(*ipaddr));
    
    /* attempt resolution */
    err = getnameinfo((struct sockaddr *) &sin, sizeof(sin),
                      host, NI_MAXHOST, NULL, 0, NI_NAMEREQD);
    
    /* got it? */
    if (err == 0 && !empty_str(host)) {
        /* remove domain part */
        char* ptr = strchr(host, '.');
        
        if (ptr)
            *ptr = '\0';
        
        debconf_set(client, "netcfg/get_hostname", host);
        
        if (!have_domain && (ptr && ptr[1] != '\0'))
            debconf_set(client, "netcfg/get_domain", ptr + 1);
    }
    
    free(host);
}

void interface_up (char* iface)
{
    struct ifreq ifr;
    
    strncpy(ifr.ifr_name, iface, IFNAMSIZ);
    
    if (skfd && ioctl(skfd, SIOCGIFFLAGS, &ifr) >= 0) {
        strncpy(ifr.ifr_name, iface, IFNAMSIZ);
        ifr.ifr_flags |= (IFF_UP | IFF_RUNNING);
        ioctl(skfd, SIOCSIFFLAGS, &ifr);
    }
}

void interface_down (char* iface)
{
    struct ifreq ifr;
    
    strncpy(ifr.ifr_name, iface, IFNAMSIZ);
    
    if (skfd && ioctl(skfd, SIOCGIFFLAGS, &ifr) >= 0) {
        strncpy(ifr.ifr_name, iface, IFNAMSIZ);
        ifr.ifr_flags &= ~IFF_UP;
        ioctl(skfd, SIOCSIFFLAGS, &ifr);
    }
}

void parse_args (int argc, char ** argv)
{
    if (argc == 2) {
        if (!strcmp(basename(argv[0]), "ptom")) {
            int ret;
            if (inet_ptom(argv[1], &ret, NULL) > 0) {
                printf("%d\n", ret);
                exit(EXIT_SUCCESS);
            }
        }

        if (!strcmp(argv[1], "write_loopback")) {
            netcfg_write_loopback();
            exit(EXIT_SUCCESS);
        }
        
        exit(EXIT_FAILURE);
    }
}

void reap_old_files (void)
{
    static char* remove[] =
        { INTERFACES_FILE, HOSTS_FILE, HOSTNAME_FILE, NETWORKS_FILE,
          RESOLV_FILE, DHCLIENT_CONF, DHCLIENT3_CONF, DOMAIN_FILE, 0 };
    char **ptr = remove;
    
    while (*ptr)
        unlink(*ptr++);
}

void netcfg_nameservers_to_array(char *nameservers, struct in_addr array[])
{
    char *save, *ptr, *ns;
    int i;
    
    if (nameservers) {
        save = ptr = strdup(nameservers);
        
        for (i = 0; i < 3; i++) {
            ns = strtok_r(ptr, " \n\t", &ptr);
            if (ns)
                inet_pton (AF_INET, ns, &array[i]);
            else
                array[i].s_addr = 0;
        }
        
        array[3].s_addr = 0;
        free(save);
    } else
        array[0].s_addr = 0;
}

int netcfg_get_nameservers (struct debconfclient *client, char **nameservers)
{
    char *ptr, ptr1[INET_ADDRSTRLEN];
    int ret;
    
    debconf_get(client,"netcfg/get_nameservers");
    if (*nameservers)
        ptr = *nameservers;
    else if (strlen(client->value))
        ptr = client->value;
    else if (gateway.s_addr) {
        inet_ntop (AF_INET, &gateway, ptr1, sizeof (ptr1));
        ptr = ptr1;
    }
    else
        ptr = "";
    debconf_set(client, "netcfg/get_nameservers", ptr);
    
    debconf_input(client, "critical", "netcfg/get_nameservers");
    ret = debconf_go(client);
    
    if (ret)
        return ret;
    
    debconf_get(client, "netcfg/get_nameservers");
    ptr = client->value;
    
    if (*nameservers)
        free(*nameservers);
    *nameservers = NULL;
    if (ptr)
        *nameservers = strdup(ptr);
    return ret;
}
