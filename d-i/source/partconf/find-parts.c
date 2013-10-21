#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mount.h>
#include <ctype.h>
#include <libgen.h>
#include <errno.h>
#ifdef FIND_PARTS_MAIN
#include <getopt.h>
#endif

#include "xasprintf.h"
#include "partconf.h"

// If it's an LVM volume, it's on the form
// /dev/<group>/<volume> and there's info in
// /proc/lvm/VGs/<group>/LVs/<volume>
static void
test_lvm(struct partition *p)
{
    FILE *fp;
    char buf[1024], name[1024];
    char *grp, *vol, *procfile;
    long long blocks = -1;

    if ((grp = strchr(p->path+1, '/')) == NULL)
        return;
    grp = strdup(grp+1);
    if ((vol = strchr(grp, '/')) == NULL)
        return;
    *vol++ = '\0';
    if (strchr(vol, '/') != NULL)
        return;
    procfile = xasprintf("/proc/lvm/VGs/%s/LVs/%s", grp, vol);
    if ((fp = fopen(procfile, "r")) == NULL)
        return;
    while (fgets(buf, sizeof(buf), fp) != NULL) {
        if (strstr(buf, "name:") == buf)
            sscanf(buf, "name: %s", name);
        else if (strstr(buf, "size:") == buf)
            sscanf(buf, "size: %lld", &blocks);
    }
    fclose(fp);
    // So, *is* it right?
    if (strcmp(name, p->path) == 0 && blocks > 0)
        p->size = blocks * 512L;
}

// If it's an EVMS volume, it's on the form
// /dev/evms/<volume> and there's info in
// /proc/evms/volumes
// XXX THIS IS UNTESTED XXX
static void
test_evms(struct partition *p)
{
    FILE *fp;
    char buf[1024], name[1024];
    long long blocks;
    int i;

    if (strstr(p->path, "/dev/evms/") != p->path)
        return;
    if ((fp = fopen("/proc/evms/volumes", "r")) == NULL)
        return;
    // Skip three lines
    for (i = 0; i < 3; i++)
        if (fgets(buf, sizeof(buf), fp) == NULL)
            return;
    while (fgets(buf, sizeof(buf), fp) != NULL) {
        sscanf(buf, "%*d %*d %lld %*s %*s %s", &blocks, name);
        if (strcmp(p->path, name) == 0) {
            p->size = blocks * 512L;
            break;
        }
    }
    fclose(fp);
}

// RAID volumes are /dev/md/# for numbers #
// Stats are found in /proc/mdstat
// XXX THIS IS UNTESTED XXX
static void
test_raid(struct partition *p)
{
    FILE *fp;
    char buf[1024], name[1024];
    long long blocks;
    int volno;

    if (strstr(p->path, "/dev/md/") != p->path)
        return;
    if ((fp = fopen("/proc/mdstat", "r")) == NULL)
        return;
    while (fgets(buf, sizeof(buf), fp) != NULL) {
        if (strstr(buf, "md") != buf)
            continue;
        sscanf(buf, "md%d : ", &volno);
        sprintf(name, "/dev/md/%d", volno);
        if (strcmp(name, p->path) == 0) {
            if (fgets(buf, sizeof(buf), fp) == NULL)
                break;
            sscanf(buf, "%lld", &blocks);
            p->size = blocks * 512L;
            free(p->description);
            p->description = xasprintf("RAID logical volume %d", volno);
            break;
        }
    }
    fclose(fp);
}

/**
 * Determine if a device is a CD-ROM/DVD based on major/minor device
 * number. Based on information from Linux's Documentation/devices.txt.
 */
bool
is_cdrom(const char * const device_name)
{
    struct stat st;

    if (stat(device_name, &st) != 0)
            return false;

    switch (major(st.st_rdev)) {
        case 11: /* SCSI CD-ROM devices */
        case 113: /* Parallel port ATAPI CD-ROM devices */
            return true;
        default:
            break;
    }

    if (minor(st.st_rdev) == 0) {
        switch (major(st.st_rdev)) {
            case 15: /* Sony CDU-31A/CDU-33A CD-ROM */
            case 16: /* GoldStar CD-ROM */
            case 17: /* Optics Storage CD-ROM */
            case 18: /* Sanyo CD-ROM */
            case 20: /* Hitachi CD-ROM */
            case 23: /* Mitsumi proprietary CD-ROM */
            case 24: /* Sony CDU-535 CD-ROM */
            case 29: /* Aztech/Orchid/Okano/Wearnes CD-ROM */
            case 30: /* Philips LMS CM-205 CD-ROM */
            case 32: /* Philips LMS CM-206 CD-ROM */
                return true;
            default:
                break;
        }
    }

    if (minor(st.st_rdev) <= 3) {
        switch (major(st.st_rdev)) {
            case 25: /* First Matsushita (Panasonic/SoundBlaster: CD-ROM */
            case 26: /* Second Matsushita (Panasonic/SoundBlaster: CD-ROM */
            case 27: /* Fourth Matsushita (Panasonic/SoundBlaster: CD-ROM */
            case 28: /* Third Matsushita (Panasonic/SoundBlaster: CD-ROM */
            case 46: /* Parallel port ATAPI CD-ROM devices */
                return true;
            default:
                break;
        }
    }

    return false;
}

#ifndef FIND_PARTS_MAIN
int
block_partition(const char *part)
{
    DIR *dir = NULL;
    struct dirent *entry = NULL;

    dir = opendir(BLOCK_D);
    if(dir == NULL)
        return(0);

    while((entry = readdir(dir)) != NULL) {
        char *cmd = NULL;
        int ret;

        if(entry->d_name[0] == '.')
            continue;

        cmd = xasprintf("/bin/sh %s/%s \"%s\" 1>/dev/null 2>&1",
            BLOCK_D, entry->d_name, part);
        ret = system(cmd);
        if(ret != 0) {
            closedir(dir);
            return(1);
        }
    }

    closedir(dir);
    return(0);
}
#endif

static void
get_partition_info(struct partition *p, PedPartition *part, PedDevice *dev, bool ignore_fs_type)
{
    if (PART_SIZE_BYTES(dev, part) > 0)
        p->size = PART_SIZE_BYTES(dev, part);
    if (!ignore_fs_type && part->fs_type != NULL) {
        if (strncmp(part->fs_type->name, "linux-swap", 10) == 0)
            p->fstype = strdup("swap");
        else
            p->fstype = strdup(part->fs_type->name);
    } else {
        if (ped_partition_is_flag_available(part, PED_PARTITION_LVM) &&
                ped_partition_get_flag(part, PED_PARTITION_LVM)) {
            p->fstype = strdup("LVM");
        }
        if (ped_partition_is_flag_available(part, PED_PARTITION_RAID) &&
                ped_partition_get_flag(part, PED_PARTITION_RAID)) {
            p->fstype = strdup("RAID");
        }
    }
}

int
get_all_partitions(struct partition *parts[], const int max_parts, bool ignore_fs_type, PedPartitionFlag require_flag)
{
    struct partition *p;
    int part_count = 0;
    PedDevice *dev = NULL;
    PedDisk *disk;
    PedPartition *part;

    ped_device_probe_all();
    while ((dev = ped_device_get_next(dev)) != NULL) {
        if (dev->read_only)
            continue;
        if (strstr(dev->path, "/dev/mtd") == dev->path)
            continue;
        if (is_cdrom(dev->path))
            continue;
        if (!ped_disk_probe(dev))
            continue;
        disk = ped_disk_new(dev);

        part = NULL;
        while ((part = ped_disk_next_partition(disk, part)) != NULL) {
            if (part->type & (PED_PARTITION_METADATA | PED_PARTITION_FREESPACE | PED_PARTITION_EXTENDED))
                continue;

            if (part_count >= max_parts)
                break;

#ifndef FIND_PARTS_MAIN
            /* allow other udebs to block partitions */
            if(block_partition(ped_partition_get_path(part)) != 0)
                continue;
#endif

            if (require_flag && !ped_partition_get_flag(part, require_flag))
                continue;

            p = malloc(sizeof(*p));
            p->path = ped_partition_get_path(part);
            if (strstr(p->path, "/dev/hd") == p->path) {
                static char *targets[] = { "master", "slave" };
                char drive;
                int part;

                if (sscanf(p->path, "/dev/hd%c%d", &drive, &part) == 2
                        && drive >= 'a' && drive <= 'z')
                    p->description = xasprintf("IDE%d %s\\, part. %d",
                            (drive - 'a') / 2 + 1, targets[(drive - 'a') % 2],
                            part);
                else
                    p->description = strdup(p->path);
            } else if (strstr(p->path, "/dev/sd") == p->path) {
                char drive;
                int host, bus, target, lun, part;
                int done = 0;

                if (sscanf(p->path, "/dev/sd%c%d", &drive, &part) == 2
                        && drive >= 'a' && drive <= 'z') {
                    struct stat st;
                    char *disk, *disk_pos, *sys_device;
                    disk = strdup(p->path + 5);
                    for (disk_pos = disk + strlen(disk) - 1; disk_pos > disk;
                         --disk_pos) {
                        if (*disk_pos >= '0' && *disk_pos <= '9')
                            *disk_pos = 0;
                        else
                            break;
                    }
                    sys_device = malloc(strlen(disk) + 19);
                    sprintf(sys_device, "/sys/block/%s/device", disk);
                    /* TODO: device symlinks are allegedly slated to go
                     * away, but it's not entirely clear what their
                     * replacement will be yet ...
                     */
                    if (lstat(sys_device, &st) == 0 && S_ISLNK(st.st_mode)) {
                        char buf[512];
                        memset(buf, 0, 512);
                        if (readlink(sys_device, buf, 511) > 0) {
                            const char *bus_id = basename(buf);
                            if (sscanf(bus_id, "%d:%d:%d:%d",
                                        &host, &bus, &target, &lun) == 4) {
                                p->description = xasprintf("SCSI%d (%d\\,%d\\,%d) part. %d",
                                        host + 1, bus, target, lun, part);
                                done = 1;
                            }
                        }
                    }
                }
                if (!done)
                    p->description = strdup(p->path);
            } else
                p->description = strdup(p->path);
            p->fstype = NULL;
            p->fsid = NULL;
            p->size = 0L;
            p->op.filesystem = NULL;
            p->op.mountpoint = NULL;
            p->op.done = 0;
            test_lvm(p);
            test_evms(p);
            test_raid(p);
            /* FIXME: Other tests? */

            get_partition_info(p, part, dev, ignore_fs_type);
            parts[part_count++] = p;
        }

        if (part_count >= max_parts)
            break;
    }

    return part_count;
}


#ifdef FIND_PARTS_MAIN

int
main(int argc, char *argv[])
{
    struct partition *parts[MAX_PARTS];
    int part_count, i;
    bool ignore_fs_type = false;
    bool colons = false;
    PedPartitionFlag require_flag = 0;

    int opt;
    struct option longopts[] = {
        { "ignore-fstype",  no_argument,        NULL, 'i' },
        { "colons",         no_argument,        NULL, 'c' },
        { "flag",           required_argument,  NULL, 'f' },
        { NULL, 0, NULL, 0 }
    };

    while ((opt = getopt_long(argc, argv, "icf:", longopts, NULL)) != EOF) {
        switch (opt) {
            case 'i':
                ignore_fs_type = true;
                break;
            case 'c':
                colons = true;
                break;
            case 'f':
                require_flag = ped_partition_flag_get_by_name(optarg);
                if (!require_flag) {
                    fprintf(stderr, "Unknown parted flag '%s'\n", optarg);
                    exit(1);
                }
                break;
        }
    }

    if ((part_count = get_all_partitions(parts, MAX_PARTS, ignore_fs_type, require_flag)) <= 0)
        return 1;
    for (i = 0; i < part_count; i++) {
        if (colons)
            printf("%s:%s:%lld\n",
                    parts[i]->path,
                    parts[i]->fstype != NULL ? parts[i]->fstype : "",
                    parts[i]->size);
        else
            printf("%s\t%s\t%s\n",
                    parts[i]->path,
                    parts[i]->fstype != NULL ? parts[i]->fstype : "",
                    parts[i]->size > 0 ? size_desc(parts[i]->size) : "");
    }
    return 0;
}

#endif
