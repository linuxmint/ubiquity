/* Given a device name, a filesystem, and an optional label, check if the
 * filesystem is one that can sensibly be automounted, and if so print a
 * sensible default mount point for it. Mount points are chosen to match
 * those selected by pmount.
 */

#include <stdio.h>
#include <string.h>
#include <limits.h>

#include <debian-installer.h>

/* Filesystem names as returned by libparted. */
const char *fs_list[] = {
    "ext2",
    "ext3",
    "ext4",
    "fat16",
    "fat32",
    "hfs",
    "jfs",
    "ntfs",
    "reiserfs",
    "xfs",
    NULL
};

int
automountable_filesystem(const char *fs)
{
    const char **walk;
    for (walk = fs_list; *walk; ++walk)
        if (!strcmp(fs, *walk))
            return 1;
    return 0;
}

void
replace(char *s, char from, char to)
{
    char *p;
    for (p = s; *p; ++p)
        if (*p == from)
            *p = to;
}

#ifndef PATH_MAX
#define PATH_MAX 4095
#endif

int
main(int argc, char *argv[])
{
    const char *device, *fs, *label = NULL;

    if (argc < 3) {
        fprintf(stderr, "Usage: %s DEVICE FILESYSTEM [LABEL]\n", argv[0]);
        return 1;
    }

    device = argv[1];
    fs = argv[2];
    if (argc >= 4)
        label = argv[3];

    if (automountable_filesystem(fs)) {
        if (label)
            printf("/media/%s\n", label);
        else {
            char mapped[PATH_MAX + 1], *mappedtail;
            if (di_system_devfs_map_from(device, mapped, PATH_MAX + 1)) {
                mappedtail = mapped;
                if (!strncmp(mappedtail, "/dev/", 5))
                    mappedtail += 5;
                replace(mappedtail, '/', '_');
                printf("/media/%s\n", mappedtail);
            }
        }
    }

    return 0;
}
