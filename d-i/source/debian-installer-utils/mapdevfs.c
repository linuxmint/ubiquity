/*
 *  map devfs names to old-style names
 *
 */

#include <debian-installer.h>

int main (int argc, char **argv) {
	static char buf[256];
	size_t len = sizeof(buf);

	if (argc != 2) {
		fprintf(stderr, "Wrong number of args: mapdevfs <path>\n");
		return 1;
	}

	if ((di_system_devfs_map_from(argv[1], buf, len))) {
		printf("%s\n", buf);
		return 0;
	}

	return 1;
}
