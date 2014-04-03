/* The best bits of mii-diag and ethtool mixed into one big jelly roll. */

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <net/if.h>
#include <sys/types.h>
#include <sys/ioctl.h>
#ifndef TEST
# include <debian-installer/log.h>
# define CONNECTED 1
# define DISCONNECTED 2
# define UNKNOWN 3
#else
# define di_info(fmt, ...) printf(fmt, ## __VA_ARGS__)
# define di_warning(fmt, ...) fprintf(stderr, fmt, ## __VA_ARGS__)
# define CONNECTED 0
# define DISCONNECTED 0
# define UNKNOWN 1
#endif

#if defined(__linux__)

#ifndef ETHTOOL_GLINK
# define ETHTOOL_GLINK 0x0000000a
#endif

#ifndef SIOCETHTOOL
# define SIOCETHTOOL 0x8946
#endif

struct ethtool_value
{
	u_int32_t cmd;
	u_int32_t data;
};

#elif defined(__FreeBSD_kernel__)

#include <net/if_media.h>

#endif

#ifdef TEST
int main(int argc, char** argv)
#else
int ethtool_lite (const char * iface)
#endif
{
#ifdef TEST
	char* iface;
#endif
	int fd = socket(AF_INET, SOCK_DGRAM, 0);

	if (fd < 0)
	{
		di_warning("ethtool-lite: could not open control socket\n");
		return UNKNOWN;
	}

#ifdef TEST
	if (argc < 2)
	{
		fprintf(stderr, "ethtool-lite: Error: must pass an interface name\n");
		close(fd);
		return 1;
	}
	iface = argv[1];
#endif

#if defined(__linux__)
	struct ethtool_value edata;
	struct ifreq ifr;

	memset (&edata, 0, sizeof(struct ethtool_value));
	edata.cmd = ETHTOOL_GLINK;
	ifr.ifr_data = (char *)&edata;
	strncpy (ifr.ifr_name, iface, IFNAMSIZ);

	if (ioctl (fd, SIOCETHTOOL, &ifr) >= 0)
	{
		di_info("ethtool-lite: %s is %sconnected.\n", iface,
		        (edata.data) ? "" : "dis");
		close(fd);
		return (edata.data) ? CONNECTED : DISCONNECTED;
	}
	else
	{
		di_info("ethtool-lite: ethtool ioctl on %s failed\n", iface);
		u_int16_t *data = (u_int16_t *)&ifr.ifr_data;
		int ctl;
		data[0] = 0;

		if (ioctl (fd, 0x8947, &ifr) >= 0)
			ctl = 0x8948;
		else if (ioctl (fd, SIOCDEVPRIVATE, &ifr) >= 0)
			ctl = SIOCDEVPRIVATE + 1;
		else
		{
			di_warning("ethtool-lite: couldn't determine MII ioctl to use for %s\n", iface);
			close(fd);
			return UNKNOWN;
		}

		data[1] = 1;

		if (ioctl (fd, ctl, &ifr) >= 0)
		{
			int ret = !(data[3] & 0x0004);

			di_info ("ethtool-lite: %s is %sconnected. (MII)\n", iface,
				(ret) ? "dis" : "");

			close(fd);
			return ret ? DISCONNECTED : CONNECTED;
		}
	}

	di_warning("ethtool-lite: MII ioctl failed for %s\n", iface);

#elif defined(__FreeBSD_kernel__)
	struct ifmediareq ifmr;

	memset(&ifmr, 0, sizeof(ifmr));
	strncpy(ifmr.ifm_name, iface, sizeof(ifmr.ifm_name));

	if (ioctl(fd, SIOCGIFMEDIA, (caddr_t)&ifmr) < 0) {
		di_warning("ethtool-lite: SIOCGIFMEDIA ioctl on %s failed\n", iface);
		close(fd);
		return UNKNOWN;
	}

	if (ifmr.ifm_status & IFM_AVALID) {
		if (ifmr.ifm_status & IFM_ACTIVE) {
			di_info("ethtool-lite: %s is connected.\n", iface);
			close(fd);
			return CONNECTED;
		} else {
			di_info("ethtool-lite: %s is disconnected.\n", iface);
			close(fd);
			return DISCONNECTED;
		}
	}

	di_warning("ethtool-lite: couldn't determine status for %s\n", iface);
#elif defined(__GNU__)
	di_warning("ethtool-lite: unsupported on GNU/Hurd for %s\n", iface);
#endif
	close(fd);
	return UNKNOWN;
}
