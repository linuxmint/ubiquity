/* The best bits of mii-diag and ethtool mixed into one big jelly roll. */

#include <stdio.h>
#include <string.h>
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

#ifdef TEST
int main(int argc, char** argv)
#else
int ethtool_lite (char * iface)
#endif
{
	struct ethtool_value edata;
	struct ifreq ifr;
#ifdef TEST
	char* iface;
#endif
	int fd = socket(AF_INET, SOCK_DGRAM, 0);

	memset (&edata, 0, sizeof(struct ethtool_value));
	
	if (fd < 0)
	{
		di_warning("could not open control socket\n");
		return UNKNOWN;
	}

#ifdef TEST
	if (argc < 2)
	{
		fprintf(stderr, "Error: must pass an interface name\n");
		return 1;
	}
	iface = argv[1];
#endif
	
	edata.cmd = ETHTOOL_GLINK;
	ifr.ifr_data = (char *)&edata;
	strncpy (ifr.ifr_name, iface, IFNAMSIZ);
	
	if (ioctl (fd, SIOCETHTOOL, &ifr) < 0)
		di_info("ethtool ioctl on %s failed\n", iface);
	
	if (edata.data)
	{
		di_info("%s is connected.\n", iface);
		return CONNECTED;
	}
	else
	{
		u_int16_t *data = (u_int16_t *)&ifr.ifr_data;
		int ctl;
		data[0] = 0;

		if (ioctl (fd, 0x8947, &ifr) >= 0)
			ctl = 0x8948;
		else if (ioctl (fd, SIOCDEVPRIVATE, &ifr) >= 0)
			ctl = SIOCDEVPRIVATE + 1;
		else
		{
			di_warning("couldn't determine MII ioctl to use for %s\n", iface);
			return UNKNOWN;
		}

		data[1] = 1;

		if (ioctl (fd, ctl, &ifr) >= 0)
		{
			int ret = !(data[3] & 0x0004);

			di_info ("%s is %sconnected. (MII)\n", iface,
				(ret) ? "dis" : "");

			return ret ? DISCONNECTED : CONNECTED;
		}
	}

	di_warning("MII ioctl failed for %s\n", iface);
	return UNKNOWN;
}
