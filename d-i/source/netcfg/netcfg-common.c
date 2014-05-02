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
#include <net/ethernet.h>
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

#ifdef __linux__
#include <netpacket/packet.h>
#define SYSCLASSNET "/sys/class/net/"
#endif /* __linux__ */

#ifdef __FreeBSD_kernel__
#include <net/if_dl.h>
#define LO_IF	"lo0"
#else
#define LO_IF	"lo"
#endif

/* network config */
char hostname[MAXHOSTNAMELEN + 1];
char domain[MAXHOSTNAMELEN + 1];
int have_domain = 0;

/* File descriptors for ioctls and such */
int skfd = 0;
#ifdef WIRELESS
int wfd = 0;
#endif

/* Count the number of contiguous 1 bits in a 32-bit integer, starting from
 * the MSB. */
static unsigned int count_bits(uint32_t num)
{
    int count = 0;

    while (num & 0x80000000) {
        count++;
        num <<= 1;
    }

    return count;
}

/* convert a netmask string (eg 255.255.255.0 or ffff:ff::) in +src+ into
 * the length (24) in +dst+.  Return 0 if some sort of failure, or 1 on
 * success.
 */
int inet_ptom (int af, const char *src, unsigned int *dst)
{
    union inX_addr addr;

    if (!empty_str(src)) {
        if (inet_pton (af, src, &addr) < 0) {
            *dst = 0;
            return 0;
        }
    }

    if (af == AF_INET) {
        *dst = count_bits(ntohl(addr.in4.s_addr));
        return 1;
    } else if (af == AF_INET6) {
        int i, count;
        for (i = 0, *dst = 0; i < 4; i++) {
            count = count_bits(htonl(addr.in6.s6_addr32[i]));
            *dst += count;
            if (count != 32) break;  /* Don't go any further if the mask has finished */
        }
        return 1;
    } else {
        *dst = 0;
        return 0;
    }
}

/* convert a length (24) in +src+ into the string netmask (255.255.255.0) in
 * +dst+.  The length of +dst+ is given in +len+, to ensure we don't
 * overrun the buffer +dst+.  +dst+ should always be at least NETCFG_ADDRSTRLEN
 * bytes long.
 *
 * Returns the address of +dst+ on success, and NULL on failure.
 */
const char *inet_mtop (int af, unsigned int src, char *dst, socklen_t len)
{
    struct in_addr addr;
    
    inet_mton(AF_INET, src, &addr);
    
    return inet_ntop (af, &addr, dst, len);
}

/* convert a mask length (eg 24) in +src+ into the struct in_addr it corresponds
 * to.
 */
void inet_mton (int af, unsigned int src, void *dst)
{
    in_addr_t mask = 0;
    struct in_addr *addr;
    struct in6_addr *addr6;
    
    if (af == AF_INET) {
        addr = (struct in_addr *)dst;
        for(; src; src--)
            mask |= 1 << (32 - src);

        addr->s_addr = htonl(mask);
    } else if (af == AF_INET6) {
        unsigned int byte = 0;
        addr6 = (struct in6_addr *)dst;
        /* Clear out the address */
        memset(addr6->s6_addr, 0, 16);
        
        while (src > 7) {
            addr6->s6_addr[byte++] = 0xff;
            src -= 8;
        }
        for (; src; src--)
            addr6->s6_addr[byte] |= 1 << (8 - src);
    }
}

void open_sockets (void)
{
#ifdef WIRELESS
    wfd = iw_sockets_open();
#endif
    skfd = socket (AF_INET, SOCK_DGRAM, 0);
}

#ifdef __linux__

/* Returns non-zero if this interface has an enabled kill switch, otherwise
 * zero.
 */
int check_kill_switch(const char *if_name)
{
    char *temp, *linkbuf;
    const char *killname;
    char killstate;
    size_t len;
    int linklen, killlen;
    int fd = -1;
    int ret = 0;

    /* longest string we need */
    len = strlen(SYSCLASSNET) + strlen(if_name) + strlen("/device/rf_kill") + 1;

    temp = malloc(len);
    snprintf(temp, len, SYSCLASSNET "%s/driver", if_name);
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

    snprintf(temp, len, SYSCLASSNET "%s/device/%s", if_name, killname);
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

#else /* !__linux__ */
int check_kill_switch(const char *if_name)
{
    (void)if_name;
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

#if defined(__s390__)
// Layer 3 qeth on s390(x) cannot do arping to test gateway reachability.
int is_layer3_qeth(const char *iface)
{
    const int bufsize = 1024;
    int retval = 0;
    char* path;
    char* buf;
    size_t len;
    ssize_t slen;
    char* driver;
    int fd;

    // This is sufficient for both /driver and /layer2.
    len = strlen(SYSCLASSNET) + strlen(iface) + strlen("/device/driver") + 1;

    path = malloc(len);
    snprintf(path, len, SYSCLASSNET "%s/device/driver", iface);

    // lstat() on sysfs symlinks does not provide size information.
    buf = malloc(bufsize);
    slen = readlink(path, buf, bufsize - 1);

    if (slen < 0) {
        di_error("Symlink %s cannot be resolved: %s", path, strerror(errno));
        goto out;
    }

    buf[slen + 1] = '\0';

    driver = strrchr(buf, '/') + 1;
    if (strcmp(driver, "qeth") != 0) {
        di_error("no qeth found: %s", driver);
        goto out;
    }

    snprintf(path, len, SYSCLASSNET "%s/device/layer2", iface);

    fd = open(path, O_RDONLY);
    if (fd == -1) {
        di_error("%s cannot be opened: %s", path, strerror(errno));
        goto out;
    }

    slen = read(fd, buf, 1);
    if (slen == -1) {
        di_error("Read from %s failed: %s", path, strerror(errno));
        close(fd);
        goto out;
    }

    if (buf[0] == '0') {
        // driver == 'qeth' && layer2 == 0
        retval = 1;
    }

    close(fd);

out:
    free(buf);
    free(path);
    return retval;
}
#else
int is_layer3_qeth(const char *iface __attribute__((unused)))
{
    return 0;
}
#endif

int qsort_strcmp(const void *a, const void *b)
{
    const char **ia = (const char **)a;
    const char **ib = (const char **)b;
    return strcmp(*ia, *ib);
}

#ifdef __GNU__
#include <mach.h>
#include <device/device.h>
#include <hurd.h>
/* On Hurd, the IP stack (pfinet) does not know the list of network interfaces
 * before we configure them, so we cannot use getifaddrs(). Instead we try
 * possible names for network interfaces and check whether they exists by
 * attempting to open the kernel device. */
int get_all_ifs (int all __attribute__ ((unused)), char*** ptr)
{
    static const char *const fmt[] = { "eth%d", "wl%d", NULL };

    mach_port_t device_master, file_master;
    device_t device;
    int err;
    char **list;
    int num, i, j;
    char name[3 + 3 * sizeof (int) + 1];
    char devname[5 + sizeof(name)];

    err = get_privileged_ports (0, &device_master);
    if (err)
        return 0;

    num = 0;
    list = malloc(sizeof *list);
    for (i = 0; fmt[i]; i++)
        for (j = 0;; j++) {
            char *thename;
            sprintf (name, fmt[i], j);
            sprintf (devname, "/dev/%s", name);
            err = device_open (device_master, D_READ, name, &device);
            if (err == 0)
                thename = name;
            else
                {
                    file_master = file_name_lookup (devname, O_READ | O_WRITE, 0);
                    if (file_master == MACH_PORT_NULL)
                        break;

                    err = device_open (file_master, D_READ, name, &device);
                    mach_port_deallocate (mach_task_self (), file_master);
                    if (err != 0)
                        break;
                    thename = devname;
                }

            device_close (device);
            mach_port_deallocate (mach_task_self (), device);

            list = realloc (list, (num + 2) * sizeof *list);
            list[num++] = strdup(thename);
        }
    list[num] = NULL;

    mach_port_deallocate (mach_task_self (), device_master);
    *ptr = list;
    return num;
}
#else
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
#if defined(__FreeBSD_kernel__)
        if (!strncmp(ibuf, "pfsync", 6))     /* ignore pfsync devices */
            continue;
        if (!strncmp(ibuf, "pflog", 5))      /* ignore pflog devices */
            continue;
        if (!strncmp(ibuf, "usbus", 5))      /* ignore usbus devices */
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
#endif

#ifdef __linux__
short find_in_stab(const char *if_name)
{
    FILE *dn = NULL;
    char buf[128];
    size_t len = strlen(if_name);

    if (access(STAB, F_OK) == -1)
        return 0;

    if (!(dn = popen("grep -v '^Socket' " STAB " | cut -f5", "r")))
        return 0;

    while (fgets (buf, 128, dn) != NULL) {
        if (!strncmp(buf, if_name, len)) {
            pclose(dn);
            return 1;
        }
    }
    pclose(dn);
    return 0;
}
#else /* !__linux__ */
/* Stub function for platforms not supporting /var/run/stab. */
short find_in_stab(const char *if_name)
{
    (void)if_name;
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

char *get_ifdsc(struct debconfclient *client, const char *if_name)
{
    char template[256], *ptr = NULL;

    if ((ptr = find_in_devnames(if_name)) != NULL) {
        debconf_metaget(client, "netcfg/internal-wireless", "description");

        if (is_wireless_iface(if_name)) {
            size_t len = strlen(ptr) + strlen(client->value) + 4;
            ptr = realloc(ptr, len);

            di_snprintfcat(ptr, len, " (%s)", client->value);
        }
        return ptr; /* already strdup'd */
    }

    if (strlen(if_name) < 100) {
        if (!is_wireless_iface(if_name)) {
            /* strip away the number from the interface (eth0 -> eth) */
            char *ifp = strdup(if_name), *ptr = ifp;
            while ((*ptr < '0' || *ptr > '9') && *ptr != '\0')
                ptr++;
            *ptr = '\0';

            sprintf(template, "netcfg/internal-%s", ifp);
            free(ifp);

            if (debconf_metaget(client, template, "description") ==
                    CMD_SUCCESS && client->value != NULL) {
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

int iface_is_hotpluggable(const char *if_name)
{
    FILE* f = NULL;
    char buf[256];
    size_t len = strlen(if_name);

    if (!(f = fopen(DEVHOTPLUG, "r"))) {
        di_info("No hotpluggable devices are present in the system.");
        return 0;
    }

    while (fgets(buf, 256, f) != NULL) {
        if (!strncmp(buf, if_name, len)) {
            di_info("Detected %s as a hotpluggable device", if_name);
            fclose(f);
            return 1;
        }
    }

    fclose(f);

    di_info("Hotpluggable devices available, but %s is not one of them", if_name);
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

static char *get_bootif(void)
{
#ifdef __linux__
#define PROC_CMDLINE "/proc/cmdline"

    FILE *cmdline_file;
    char *cmdline = NULL;
    size_t dummy;
    const char *s;
    char *bootif = NULL;

    /* Look for BOOTIF= entry in kernel command line. */

    cmdline_file = file_open(PROC_CMDLINE, "r");
    if (!cmdline_file) {
        di_error("Failed to open " PROC_CMDLINE ": %s", strerror(errno));
        return NULL;
    }
    if (getline(&cmdline, &dummy, cmdline_file) < 0) {
        di_error("Failed to read line from " PROC_CMDLINE ": %s",
                 strerror(errno));
        fclose(cmdline_file);
        return NULL;
    }

    s = cmdline;
    while ((s = strstr(s, "BOOTIF=")) != NULL) {
        if (s == cmdline || s[-1] == ' ') {
            size_t bootif_len;
            char *subst;

            s += sizeof("BOOTIF=") - 1;
            bootif_len = strcspn(s, " ");
            if (bootif_len != (ETH_ALEN * 3 - 1) + 3)
                continue;
            bootif = strndup(s + 3, bootif_len - 3); /* skip hardware type */
            for (subst = bootif; *subst; subst++)
                if (*subst == '-')
                    *subst = ':';
            break;
        }
        s++;
    }

    free(cmdline);
    fclose(cmdline_file);

    if (!bootif)
        di_info("Could not find valid BOOTIF= entry in " PROC_CMDLINE);

    return bootif;

#undef PROC_CMDLINE
#else /* !__linux__ */
    return NULL;
#endif /* __linux__ */
}

static unsigned char *parse_bootif(const char *bootif, int quiet)
{
    int i;
    const char *s;
    unsigned char *bootif_addr = malloc(ETH_ALEN);

    /* Parse supplied address. */
    for (i = 0, s = bootif; i < ETH_ALEN && s; i++) {
        unsigned long bootif_byte;

        errno = 0;
        bootif_byte = strtol(s, (char **) &s, 16);
        if (errno || bootif_byte >= 256) {
            if (!quiet)
                di_error("couldn't parse link-layer address '%s'", bootif);
            free(bootif_addr);
            return NULL;
        }
        bootif_addr[i] = (unsigned char) bootif_byte;
        if (i < ETH_ALEN - 1 && *s++ != ':') {
            if (!quiet)
                di_error("couldn't parse link-layer address '%s'", bootif);
            free(bootif_addr);
            return NULL;
        }
    }

    return bootif_addr;
}

static char *find_bootif_iface(const char *bootif,
                               const unsigned char *bootif_addr)
{
#ifdef __GNU__
    /* TODO: Use device_get_status(NET_ADDRESS), see pfinet/ethernet.c */
    (void)bootif;
    (void)bootif_addr;
    return NULL;
#else
    struct ifaddrs *ifap, *ifa;
    char *ret = NULL;

    /* TODO: this won't work on the Hurd as getifaddrs doesn't return
     * unconfigured interfaces.  See comment to get_all_ifs.
     */
    if (getifaddrs(&ifap) < 0) {
        di_error("getifaddrs failed: %s", strerror(errno));
        return NULL;
    }

    for (ifa = ifap; ifa; ifa = ifa->ifa_next) {
#if defined(__FreeBSD_kernel__)
        struct sockaddr_dl *sdl;
#else
        struct sockaddr_ll *sll;
#endif

        if (ifa->ifa_flags & IFF_LOOPBACK)
            continue;
#if defined(__linux__)
        if (!strncmp(ifa->ifa_name, "sit", 3))  /* ignore tunnel devices */
            continue;
#endif
#if defined(WIRELESS)
        if (is_raw_80211(ifa->ifa_name))
            continue;
#endif
#if defined(__FreeBSD_kernel__)
        if (ifa->ifa_addr->sa_family != AF_LINK)
            continue;
        sdl = (struct sockaddr_dl *) ifa->ifa_addr;
        if (!sdl)                               /* no link-layer address */
            continue;
        if (sdl->sdl_alen != ETH_ALEN)          /* not Ethernet */
            continue;
        if (memcmp(bootif_addr, LLADDR(sdl), ETH_ALEN) != 0)
            continue;
#else
        if (ifa->ifa_addr->sa_family != AF_PACKET)
            continue;
        sll = (struct sockaddr_ll *) ifa->ifa_addr;
        if (!sll)                               /* no link-layer address */
            continue;
        if ((sll->sll_hatype != ARPHRD_ETHER &&
             sll->sll_hatype != ARPHRD_IEEE802) ||
            sll->sll_halen != ETH_ALEN)         /* not Ethernet */
            continue;
        if (memcmp(bootif_addr, sll->sll_addr, ETH_ALEN) != 0)
            continue;
#endif

        di_info("Found interface %s with link-layer address %s",
                ifa->ifa_name, bootif);
        ret = strdup(ifa->ifa_name);
        break;
    }

    freeifaddrs(ifap);

    if (!ret)
        di_error("Could not find any interface with address %s", bootif);

    return ret;
#endif
}

void netcfg_die(struct debconfclient *client)
{
    debconf_progress_stop(client);
    debconf_capb(client);
    debconf_input(client, "high", "netcfg/error");
    debconf_go(client);
    exit(1);
}

/**
 * @brief Ask which interface to configure
 * @param client    - client
 * @param interface - set the +name+ field to the answer
 * @param numif     - number of interfaces found.
 * @param defif     - default interface from link detection.
 */

int netcfg_get_interface(struct debconfclient *client, char **interface,
                         int *numif, const char *defif)
{
    char *inter = NULL, **ifs;
    size_t len;
    int ret, i, asked;
    int num_interfaces = 0;
    unsigned char *bootif_addr;
    char *bootif_iface = NULL;
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

    /* Remember old interface selection, in case it's preseeded. */
    debconf_get(client, "netcfg/choose_interface");
    old_selection = strdup(client->value);

    /* If netcfg/choose_interface is preseeded to a link-layer address in
     * the form aa:bb:cc:dd:ee:ff, or if BOOTIF is set and matches an
     * interface, override any provided default from link detection. */
    bootif_addr = parse_bootif(old_selection, 1);
    if (bootif_addr) {
        bootif_iface = find_bootif_iface(old_selection, bootif_addr);
        if (bootif_iface) {
            free(old_selection);
            old_selection = strdup(bootif_iface);
        }
        free(bootif_addr);
    } else {
        char *bootif = get_bootif();
        if (bootif) {
            bootif_addr = parse_bootif(bootif, 0);
            if (bootif_addr) {
                bootif_iface = find_bootif_iface(bootif, bootif_addr);
                free(bootif_addr);
            }
            free(bootif);
        }
    }
    if (bootif_iface) {
        /* Did we actually get back an interface we know about? */
        for (i = 0; i < num_interfaces; i++) {
            if (strcmp(ifs[i], bootif_iface) == 0) {
                defif = ifs[i];
                break;
            }
        }
        free (bootif_iface);
    }

    /* If no default was provided, use the first in the list of interfaces. */
    if (! defif && num_interfaces > 0) {
        defif = ifs[0];
    }

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

        asked = (debconf_input(client, "critical", "netcfg/choose_interface") == CMD_SUCCESS);
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
    return RETURN_TO_MAIN; /* unreachable */
}

/*
 * Verify that the hostname conforms to RFC 1123 s2.1,
 * and RFC 1034 s3.5.
 * @return 1 on success, 0 on failure.
 */
short valid_hostname (const char *hname)
{
    static const char *valid_chars =
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-";
    size_t len;
    assert(hname != NULL);

    len = strlen(hname);

    if ((len < 1) ||
        (len > MAXHOSTNAMELEN) ||
        (strspn(hname, valid_chars) != len) ||
        (hname[len - 1] == '-') ||
        (hname[0] == '-')) {
        return 0;
    }
    else
        return 1;
}

/*
 * Verify that the domain name (or FQDN) conforms to RFC 1123 s2.1, and
 * RFC1034 s3.5.
 * @return 1 on success, 0 on failure.
 */
short valid_domain (const char *dname)
{
    static const char *valid_chars =
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.";
    size_t len;
    assert(dname != NULL);

    len = strlen(dname);

    if ((len < 1) ||
        (len > MAXHOSTNAMELEN) ||
        (strspn(dname, valid_chars) != len) ||
        (dname[len - 1] == '-') ||
        (dname[0] == '-') ||
        (dname[len - 1] == '.') ||
        (dname[0] == '.') ||
        strstr(dname, "..")) {
        return 0;
    }
    else
        return 1;
}

/*
 * Write the hostname to the given string (must be capable of storing at
 * least MAXHOSTNAMELEN bytes.
 *
 * @return 0 on success, 30 on BACKUP being selected.
 */
int netcfg_get_hostname(struct debconfclient *client, char *template, char *hostname, short accept_domain)
{
    char *s, buf[1024];

    for(;;) {
        if (accept_domain)
            have_domain = 0;
        debconf_input(client, "high", template);

        if (debconf_go(client) == CMD_GOBACK)
            return GO_BACK;

        debconf_get(client, template);

        strncpy(hostname, client->value, MAXHOSTNAMELEN);

        if (!valid_domain(hostname)) {
            di_info("%s is an invalid domain", hostname);
            debconf_subst(client, "netcfg/invalid_hostname",
                          "hostname", hostname);
            snprintf(buf, sizeof(buf), "%i", MAXHOSTNAMELEN);
            debconf_subst(client, "netcfg/invalid_hostname",
                      "maxhostnamelen", buf);
            debconf_input(client, "high", "netcfg/invalid_hostname");
            debconf_go(client);
            debconf_set(client, template, "ubuntu");
            *hostname = '\0';
            continue;
        }

        if (accept_domain && (s = strchr(hostname, '.'))) {
            di_info("Detected we have an FQDN; splitting and setting domain");
            if (s[1] == '\0') { /* "somehostname." <- . should be ignored */
                *s = '\0';
            } else { /* assume we have a valid domain name given */
                strncpy(domain, s + 1, MAXHOSTNAMELEN);
                debconf_set(client, "netcfg/get_domain", domain);
                have_domain = 1;
                *s = '\0';
            }
        }
        
        if (!valid_hostname(hostname)) {
            di_info("%s is an invalid hostname", hostname);
            debconf_subst(client, "netcfg/invalid_hostname",
                          "hostname", hostname);
            snprintf(buf, sizeof(buf), "%i", MAXHOSTNAMELEN);
            debconf_subst(client, "netcfg/invalid_hostname",
                      "maxhostnamelen", buf);
            debconf_input(client, "high", "netcfg/invalid_hostname");
            debconf_go(client);
            debconf_set(client, template, "ubuntu");
            *hostname = '\0';
        } else {
            break;
        }
    }

    return 0;
}

/* @brief Get the domainname.
 * @return 0 for success, with *domain = domain, GO_BACK for 'goback',
 */
int netcfg_get_domain(struct debconfclient *client,  char domain[], const char *priority)
{
    int ret;

    if (have_domain == 1)
    {
        debconf_get(client, "netcfg/get_domain");
        assert (!empty_str(client->value));
        strncpy(domain, client->value, MAXHOSTNAMELEN);
        return 0;
    }

    debconf_input (client, priority, "netcfg/get_domain");
    ret = debconf_go(client);

    if (ret)
        return ret;

    debconf_get (client, "netcfg/get_domain");

    *domain = '\0';
    if (!empty_str(client->value)) {
        const char *start = client->value;
        while (*start == '.')
            ++start; /* trim leading dots */
        strncpy(domain, start, MAXHOSTNAMELEN);
    }

    return 0;
}

void netcfg_write_loopback (void)
{
    struct netcfg_interface lo;
    
    netcfg_interface_init(&lo);
    lo.name = LO_IF;
    lo.loopback = 1;
    
    netcfg_write_interface(NULL);
    netcfg_write_interface(&lo);
}

/*
 * ipaddress.s_addr may be 0
 * domain may be null
 * interface may be null
 * hostname may _not_ be null
 */
void netcfg_write_common(const char *ipaddress, const char *hostname, const char *domain)
{
    FILE *fp;
    char *domain_nodot = NULL;

    if (empty_str(hostname))
        return;

    if (domain) {
        char *end;

        /* strip trailing dots */
        domain_nodot = strdup(domain);
        end = domain_nodot + strlen(domain_nodot) - 1;
        while (end >= domain_nodot && *end == '.')
            *end-- = '\0';
    }

    /* Currently busybox, hostname is not available. */
    if (sethostname (hostname, strlen(hostname) + 1) < 0) {
        /* ignore errors */
    }

    if ((fp = file_open(HOSTNAME_FILE, "w"))) {
        fprintf(fp, "%s\n", hostname);
        fclose(fp);
    }

    if ((fp = file_open(HOSTS_FILE, "w"))) {
        fprintf(fp, "127.0.0.1\tlocalhost");

        if (!empty_str(ipaddress)) {
            if (domain_nodot && !empty_str(domain_nodot))
                fprintf(fp, "\n%s\t%s.%s\t%s\n", ipaddress, hostname, domain_nodot, hostname);
            else
                fprintf(fp, "\n%s\t%s\n", ipaddress, hostname);
        } else {
#if defined(__linux__) || defined(__GNU__)
            if (domain_nodot && !empty_str(domain_nodot))
                fprintf(fp, "\n127.0.1.1\t%s.%s\t%s\n", hostname, domain_nodot, hostname);
            else
                fprintf(fp, "\n127.0.1.1\t%s\n", hostname);
#else
            fprintf(fp, "\t%s\n", hostname);
#endif
        }

        fprintf(fp, "\n" IPV6_HOSTS);

        fclose(fp);
    }

    free(domain_nodot);
}


void deconfigure_network(struct netcfg_interface *iface)
{
    /* deconfiguring network interfaces */
    interface_down(LO_IF);
    if (iface)
        interface_down(iface->name);
}

void loop_setup(void)
{
    static int afpacket_notloaded = 1;

    deconfigure_network(NULL);

#if defined(__FreeBSD_kernel__)
    (void)afpacket_notloaded;
    /* GNU/kFreeBSD currently uses the ifconfig command */
    di_exec_shell_log("ifconfig "LO_IF" up");
    di_exec_shell_log("ifconfig "LO_IF" 127.0.0.1 netmask 255.0.0.0");
#else
    if (afpacket_notloaded)
        afpacket_notloaded = di_exec_shell("modprobe af_packet"); /* should become 0 */

    di_exec_shell_log("ip link set "LO_IF" up");
    di_exec_shell_log("ip -f inet addr flush dev "LO_IF);
    di_exec_shell_log("ip addr add 127.0.0.1/8 dev "LO_IF);
#endif
}

/* Determines the IP address of the interface (either from the static
 * configuration, or by querying the interface directly if using some sort
 * of autoconfiguration), then uses that address to request rDNS lookup
 * using the currently configured nameservers.  We return the name in
 * +hostname+ if one is found, and return 1, otherwise we leave the
 * +hostname+ alone and return 0.
 */
int get_hostname_from_dns (const struct netcfg_interface *interface, char *hostname, const size_t max_hostname_len)
{
    int err = 1;
    
    if (!empty_str(interface->ipaddress)) {
        /* Static configuration assumed */
        struct sockaddr_in sin;
        struct sockaddr_in6 sin6;

        di_debug("Getting default hostname from rDNS lookup of static-configured address %s", interface->ipaddress);
        if (interface->address_family == AF_INET) {
            sin.sin_family = AF_INET;
            sin.sin_port = 0;
            inet_pton(AF_INET, interface->ipaddress, &sin.sin_addr);
            err = getnameinfo((struct sockaddr *) &sin, sizeof(sin),
                              hostname, max_hostname_len, NULL, 0, NI_NAMEREQD);
        } else if (interface->address_family == AF_INET6) {
            sin6.sin6_family = AF_INET6;
            sin6.sin6_port = 0;
            inet_pton(AF_INET6, interface->ipaddress, &sin6.sin6_addr);
            err = getnameinfo((struct sockaddr *) &sin6, sizeof(sin6),
                              hostname, max_hostname_len, NULL, 0, NI_NAMEREQD);
        } else {
            di_warning("Unknown address family in interface passed to seed_hostname_from_dns(): %i", interface->address_family);
            return 0;
        }

        if (err) {
            di_debug("getnameinfo() returned %i (%s)", err, err == EAI_SYSTEM ? strerror(errno) : gai_strerror(err));
        }

        if (err == 0) {
            /* We found a name!  We found a name! */
            di_debug("Hostname found: %s", hostname);
        }
    } else {
        /* Autoconfigured interface; we need to find the IP address ourselves
         */
        struct ifaddrs *ifa_head, *ifa;
        char tmpbuf[NETCFG_ADDRSTRLEN];
        
        if (getifaddrs(&ifa_head) == -1) {
            di_warning("getifaddrs() failed: %s", strerror(errno));
            return 0;
        }
        
        for (ifa = ifa_head; ifa != NULL; ifa = ifa->ifa_next) {
            if (strcmp(ifa->ifa_name, interface->name) != 0) {
                /* This isn't the interface you're looking for */
                continue;
            }
            if (!ifa->ifa_addr) {
                /* This isn't even a record with an address... bugger that */
                continue;
            }
            if (ifa->ifa_addr->sa_family != AF_INET && ifa->ifa_addr->sa_family != AF_INET6) {
                /* Not an IPv4 or IPv6 address... don't know what to do with it */
                continue;
            }

            di_debug("Getting default hostname from rDNS lookup of autoconfigured address %s",
                     inet_ntop(ifa->ifa_addr->sa_family,
                               (ifa->ifa_addr->sa_family == AF_INET) ?
                                (void *)(&((struct sockaddr_in *)ifa->ifa_addr)->sin_addr)
                                : (void *)(&((struct sockaddr_in6 *)ifa->ifa_addr)->sin6_addr),
                               tmpbuf, sizeof(tmpbuf)
                              )
                    );
            err = getnameinfo(ifa->ifa_addr,
                              (ifa->ifa_addr->sa_family == AF_INET) ?
                                    sizeof(struct sockaddr_in)
                                    : sizeof(struct sockaddr_in6),
                              hostname, max_hostname_len, NULL, 0, NI_NAMEREQD);
            if (err) {
                di_debug("getnameinfo() returned %i (%s)", err, err == EAI_SYSTEM ? strerror(errno) : gai_strerror(err));
            }
                              
            if (err == 0) {
                /* We found a name!  We found a name! */
                di_debug("Hostname found: %s", hostname);
                break;
            }
        }
    }
            
    return !err;
}

void interface_up (const char *if_name)
{
    struct ifreq ifr;

    strncpy(ifr.ifr_name, if_name, IFNAMSIZ);

    if (skfd && ioctl(skfd, SIOCGIFFLAGS, &ifr) >= 0) {
        di_info("Activating interface %s", if_name);
        strncpy(ifr.ifr_name, if_name, IFNAMSIZ);
        ifr.ifr_flags |= (IFF_UP | IFF_RUNNING);
        ioctl(skfd, SIOCSIFFLAGS, &ifr);
    } else {
        di_info("Getting flags for interface %s failed, not activating interface.", if_name);
    }
}

void interface_down (const char *if_name)
{
    struct ifreq ifr;

    strncpy(ifr.ifr_name, if_name, IFNAMSIZ);

    if (skfd && ioctl(skfd, SIOCGIFFLAGS, &ifr) >= 0) {
        di_info("Taking down interface %s", if_name);
        strncpy(ifr.ifr_name, if_name, IFNAMSIZ);
        ifr.ifr_flags &= ~IFF_UP;
        ioctl(skfd, SIOCSIFFLAGS, &ifr);
    } else {
        di_info("Getting flags for interface %s failed, not taking down interface.", if_name);
    }
}

void parse_args (int argc, char ** argv)
{
    if (argc == 2) {
        if (!strcmp(basename(argv[0]), "ptom")) {
            unsigned int ret;
            if (inet_ptom(AF_INET, argv[1], &ret) > 0) {
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
          RESOLV_FILE, DHCLIENT_CONF, DOMAIN_FILE, 0 };
    char **ptr = remove;

    while (*ptr)
        unlink(*ptr++);
}

/* Convert a space-separated list of nameservers in a single string (as might
 * be entered into, say, debconf), and store them in the interface.
 */
void netcfg_nameservers_to_array(const char *nameservers, struct netcfg_interface *interface)
{
    char *save, *ptr, *ns;
    unsigned int i;
    union inX_addr addr;

    if (nameservers) {
        save = ptr = strdup(nameservers);

        for (i = 0; i < NETCFG_NAMESERVERS_MAX; i++) {
            int af;
            ns = strtok_r(ptr, " \n\t", &ptr);
            if (ns) {
                /* The double conversion here is to both validate that we've
                 * been given an IP address, and to ensure that the address
                 * is in it's canonical form and will fit in the size of the
                 * array element provided.
                 */
                if (inet_pton (AF_INET, ns, &addr)) {
                    /* v4! */
                    af = AF_INET;
                } else {
                    /* v6? */
                    if (inet_pton (AF_INET6, ns, &addr)) {
                        af = AF_INET6;
                    } else {
                        af = -1;
                        fprintf(stderr, "Failed to parse %s as an IP address", ns);
                    }
                }

                if (af != -1) {
                    inet_ntop (af, &addr, interface->nameservers[i], NETCFG_ADDRSTRLEN);
                } else {
                    /* Dud in this slot; empty it */
                    *(interface->nameservers[i]) = '\0';
                }
            } else
                *(interface->nameservers[i]) = '\0';
        }

        free(save);
    } else {
        /* Empty out all the nameserver strings */
        for (i = 0; i < NETCFG_NAMESERVERS_MAX; i++) *(interface->nameservers[i]) = '\0';
    }
}

int netcfg_get_nameservers (struct debconfclient *client, char **nameservers, char *default_nameservers)
{
    char *ptr;
    int ret;

    debconf_get(client,"netcfg/get_nameservers");
    if (*nameservers)
        ptr = *nameservers;
    else if (strlen(client->value))
        ptr = client->value;
    else if (default_nameservers)
        ptr = default_nameservers;
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

    return 0;
}

void netcfg_update_entropy (void)
{
#ifdef __linux__
    di_exec_shell("ip addr show >/dev/random");
#endif
}

/* Attempt to find out whether we've got link on an interface.  Don't try to
 * bring the interface up or down, we leave that to the caller.  Use a
 * progress bar so the user knows what's going on.  Return true if we got
 * link, and false otherwise.
 */
int netcfg_detect_link(struct debconfclient *client, const struct netcfg_interface *interface)
{
    char arping[256];
    int count, rv = 0;
    int link_waits;
    int gw_tries = NETCFG_GATEWAY_REACHABILITY_TRIES;
    const char *if_name = interface->name;
    const char *gateway = interface->gateway;

    if (!empty_str(gateway))
        sprintf(arping, "arping -c 1 -w 1 -f -I %s %s", if_name, gateway);

    /* Ask for link detection timeout. */
    int ok = 0;
    debconf_capb(client, "");

    while (!ok) {
        debconf_input(client, "low", "netcfg/link_wait_timeout");
        debconf_go(client);
        debconf_get(client, "netcfg/link_wait_timeout");

        char *ptr, *end_ptr;
        ptr = client->value;

        if (!empty_str(ptr)) {
            link_waits = strtol(ptr, &end_ptr, 10);
            /* The input contains a single positive integer. */
            if (*end_ptr == '\0' && link_waits > 0) {
                ok = 1;
                link_waits *= 4;
            }
        }

        if (!ok) {
            if (!empty_str(ptr)) {
                di_info("The value %s provided is not valid", ptr);
            }
            else {
                di_info("No value provided");
            }

            debconf_input (client, "critical", "netcfg/bad_link_wait_timeout");
            debconf_go (client);
            debconf_set(client, "netcfg/link_wait_timeout", "3");
        }
    }

    di_info("Waiting time set to %d", link_waits / 4);

    debconf_capb(client, "progresscancel");
    debconf_subst(client, "netcfg/link_detect_progress", "interface", if_name);
    debconf_progress_start(client, 0, link_waits, "netcfg/link_detect_progress");
    for (count = 0; count < link_waits; count++) {
        usleep(250000);
        if (debconf_progress_set(client, count) == CMD_PROGRESSCANCELLED) {
            /* User cancelled on us... bugger */
            rv = 0;
            di_info("Detecting link on %s was cancelled", if_name);
            break;
        }
        if (ethtool_lite(if_name) == 1) /* ethtool-lite's CONNECTED */ {
            di_info("Found link on %s", if_name);

            if (!empty_str(gateway) && !is_wireless_iface(if_name) && !is_layer3_qeth(if_name)) {
                for (count = 0; count < gw_tries; count++) {
                    if (di_exec_shell_log(arping) == 0)
                        break;
                }
                di_info("Gateway reachable on %s", if_name);
            }

            rv = 1;
            break;
        }
    }

    if (count == link_waits) {
        di_info("Reached timeout for link detection on %s", if_name);
    }

    debconf_progress_stop(client);
    debconf_capb(client, "backup");

    return rv;
}

void netcfg_interface_init(struct netcfg_interface *iface)
{
    memset(iface, 0, sizeof(*iface));
    
    iface->name = NULL;
    iface->dhcp = -1;
    iface->dhcpv6 = -1;
    iface->address_family = -1;  /* I hope nobody uses -1 for AF_INET */
    iface->slaac = -1;
    iface->v6_stateful_config = -1;
    iface->v6_stateless_config = -1;
    iface->loopback = -1;
    iface->mode = MANAGED;
}

/* Parse an IP address (v4 or v6), with optional CIDR netmask, into
 * +interface+.  Return 1 if all went well, and return 0 if something
 * went wrong (the "IP address" wasn't, for example).  In the event
 * something went wrong, +interface+ is guaranteed to remain
 * unchanged.
 */
int netcfg_parse_cidr_address(const char *address, struct netcfg_interface *interface)
{
    struct in_addr addr;
    struct in6_addr addr6;
    int ok;
    char *maskptr, addrstr[NETCFG_ADDRSTRLEN];
    int i;
    
    strncpy(addrstr, address, NETCFG_ADDRSTRLEN);
    
    if ((maskptr = strchr(addrstr, '/'))) {
        /* Houston, we have a netmask; split it into bits */
        *maskptr = '\0';
        maskptr++;

        /* Verify that the mask is OK */
        for (i = 0; maskptr[i]; i++) {
            if (!isdigit(maskptr[i])) {
                /* That's not good; bomb out early */
                return 0;
            }
        }
    }

    ok = inet_pton (AF_INET, addrstr, &addr);

    if (ok) {
        interface->address_family = AF_INET;
        inet_ntop(AF_INET, &addr, interface->ipaddress, INET_ADDRSTRLEN);
    } else {
        /* Potential IPv6 address */
        ok = inet_pton (AF_INET6, addrstr, &addr6);
        if (ok) {
            interface->address_family = AF_INET6;
            inet_ntop(AF_INET6, &addr6, interface->ipaddress, INET6_ADDRSTRLEN);
        }
    }

    if (ok && maskptr) {
        interface->masklen = atoi(maskptr);
    } else {
        interface->masklen = 0;
    }
        
    return ok;
}

void netcfg_network_address(const struct netcfg_interface *interface,
                            char *network)
{
    union inX_addr ipaddr, mask, net;
    
    inet_pton(interface->address_family, interface->ipaddress, &ipaddr);
    inet_mton(interface->address_family, interface->masklen, &mask);
    if (interface->address_family == AF_INET) {
    	net.in4.s_addr = ipaddr.in4.s_addr & mask.in4.s_addr;
    } else if (interface->address_family == AF_INET6) {
        int i;
        
        for (i = 0; i < 4; i++) {
            net.in6.s6_addr32[i] = ipaddr.in6.s6_addr32[i] & mask.in6.s6_addr32[i];
        }
    }
    	
    inet_ntop(interface->address_family, &net, network, NETCFG_ADDRSTRLEN);
}

void netcfg_broadcast_address(const struct netcfg_interface *interface,
                              char *broadcast)
{
    struct in_addr broad, net, mask;
    char network[INET_ADDRSTRLEN];
    
    /* IPv6 has no concept of broadcast addresses */
    if (interface->address_family != AF_INET) {
        broadcast[0] = '\0';
        return;
    }

    netcfg_network_address(interface, network);
    
    inet_pton(AF_INET, network, &net);
    inet_mton(AF_INET, interface->masklen, &mask);
    broad.s_addr = (net.s_addr | ~mask.s_addr);
    inet_ntop(AF_INET, &broad, broadcast, INET_ADDRSTRLEN);
}

/* Validate that the given gateway address actually lies within the given
 * network.  Standard boolean return.
 */
int netcfg_gateway_reachable(const struct netcfg_interface *interface)
{
    union inX_addr net, mask, gw_addr;
    char network[NETCFG_ADDRSTRLEN];
    
    netcfg_network_address(interface, network);
    
    inet_pton(interface->address_family, network, &net);
    inet_mton(interface->address_family, interface->masklen, &mask);
    inet_pton(interface->address_family, interface->gateway, &gw_addr);

    if (interface->address_family == AF_INET) {
        return (gw_addr.in4.s_addr && ((gw_addr.in4.s_addr & mask.in4.s_addr) == net.in4.s_addr));
    } else if (interface->address_family == AF_INET6) {
        int i;
        
        for (i = 0; i < 4; i++) {
            if ((gw_addr.in6.s6_addr32[i] & mask.in6.s6_addr32[i]) != net.in6.s6_addr32[i]) {
                return 0;
            }
        }
        
        return 1;
    } else {
        /* Unknown address family */
        fprintf(stderr, "Unknown address family given to netcfg_gateway_unreachable\n");
        return 0;
    }
}

/* Take an FQDN (or possibly a bare hostname) and use it to preseed the get_hostname
 * and get_domain debconf variables.
 */
void preseed_hostname_from_fqdn(struct debconfclient *client, char *buf)
{
    char *dom;

    if (valid_domain(buf)) {
        di_debug("%s is a valid FQDN", buf);
        dom = strchr(buf, '.');
        if (dom) {
            di_debug("We have a real FQDN");
            *dom++ = '\0';
        }
                    
        debconf_set(client, "netcfg/get_hostname", buf);

        if (!have_domain && dom != NULL) {
            di_debug("Preseeding domain as well: %s", dom);
            debconf_set(client, "netcfg/get_domain", dom);
            have_domain = 1;
        } else if (have_domain && !empty_str(domain)) {
            /* Global var 'domain' is holding a temporary domain name,
             * presumably glommed from DHCP.  Use it as default instead.
             */
            di_debug("Preseeding domain from global: %s", domain);
            debconf_set(client, "netcfg/get_domain", domain);
        }
    }
}

/* Classic rtrim... strip off trailing whitespace from a string */
void rtrim(char *s)
{
	int n;
	
	n = strlen(s) - 1;
	
	while (isspace(s[n])) {
		s[n] = '\0';
	}
}
