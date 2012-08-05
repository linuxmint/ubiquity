#ifndef PARTCONF_H_
#define PARTCONF_H_ 1

#include <parted/parted.h>
#include <stdarg.h>
#include <stdbool.h>

#define FS_ID_SWAP      "82"
#define FS_ID_LINUX     "83"
#define FS_ID_LVM       "8E"

#define PART_SIZE_BYTES(dev,part)       ((long long)(part)->geom.length * (long long)(dev)->sector_size)

#define MAX_DISCS       64
#define MAX_PARTS       1024
#define MAX_FSES        64

#define BLOCK_D "/var/lib/partconf/block.d"

/* What we want to do with a partition */
struct operation {
    char                *filesystem; /* 'swap' is special case */
    char                *mountpoint;
    int                  done;
};

/* Represents a partition */
struct partition {
    char                *path;
    char                *description;
    char                *fstype;
    char                *fsid;
    long long            size;
    struct operation     op;
};

/* util.h */
char    *size_desc(long long bytes);
void     modprobe(const char *mod);
int      check_proc_mounts(const char *mntpoint);
int      check_proc_swaps(const char *dev);
void     append_message(const char *fmt, ...);
int      strcount(const char *s, int c);
int      umount_target(void);

/* find-parts.c */
int      get_all_partitions(struct partition *parts[], const int max_parts, bool ignore_fs_type, PedPartitionFlag require_flag);

#endif /* PARTCONF_H_ */
