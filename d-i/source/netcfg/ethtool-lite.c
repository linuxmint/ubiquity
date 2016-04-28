/* The best bits of mii-diag and ethtool mixed into one big jelly roll. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
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

#define SYSCLASSNET "/sys/class/net/"

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

#if defined(__linux__)
	int len = strlen(SYSCLASSNET) + strlen(iface) + strlen("/carrier") + 1;
	char* filename = malloc(len);
	snprintf(filename, len, SYSCLASSNET "%s/carrier", iface);
	FILE* fp = fopen(filename, "r");
	free(filename);

	char result[2];
	if (fgets(result, sizeof(result), fp) == NULL) {
		fclose(fp);
		if (errno == EINVAL) {
			di_info("ethtool-lite: %s is down", iface);
			return DISCONNECTED;
		}
		di_error("ethtool-lite: getting carrier failed: %s",
			strerror(errno));
		return UNKNOWN;
	}
	fclose(fp);

	switch (result[0]) {
	case '1':
		di_info("ethtool-lite: %s: carrier up", iface);
		return CONNECTED;
	case '0':
		di_info("ethtool-lite: %s: carrier down", iface);
		return DISCONNECTED;
	}
	di_info("ethtool-lite: %s: could not determine carrier state; got \"%s\"",
		iface, result);
	return UNKNOWN;
#elif defined(__FreeBSD_kernel__)
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

	struct ifmediareq ifmr;

	memset(&ifmr, 0, sizeof(ifmr));
	strncpy(ifmr.ifm_name, iface, sizeof(ifmr.ifm_name));

	if (ioctl(fd, SIOCGIFMEDIA, (caddr_t)&ifmr) < 0) {
		di_warning("ethtool-lite: SIOCGIFMEDIA ioctl on %s failed\n", iface);
		close(fd);
		return UNKNOWN;
	}
	close(fd);

	if (ifmr.ifm_status & IFM_AVALID) {
		if (ifmr.ifm_status & IFM_ACTIVE) {
			di_info("ethtool-lite: %s is connected.\n", iface);
			return CONNECTED;
		} else {
			di_info("ethtool-lite: %s is disconnected.\n", iface);
			return DISCONNECTED;
		}
	}

	di_warning("ethtool-lite: couldn't determine status for %s\n", iface);
#elif defined(__GNU__)
	di_warning("ethtool-lite: unsupported on GNU/Hurd for %s\n", iface);
#endif
	return UNKNOWN;
}
