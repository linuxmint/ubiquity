#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <ctype.h>
#include <libgen.h>
#include <errno.h>

#include <cdebconf/debconfclient.h>
#include <debian-installer.h>

#include "xasprintf.h"
#include "partconf.h"

static struct debconfclient *debconf = NULL;
struct partition *parts[MAX_PARTS];
static char *filesystems[MAX_FSES];
static int part_count = 0, fs_count = 0;
static char *fschoices;

static PedExceptionOption
my_exception_handler(PedException* ex)
{
    if (ex->type < PED_EXCEPTION_ERROR) {
        return PED_EXCEPTION_IGNORE;
    }
    return PED_EXCEPTION_CANCEL;
}

// True if any partition will get a new file system
int
will_mkfs(void)
{
    int i;

    for (i = 0; i < part_count; i++) {
        if (parts[i]->op.filesystem != NULL)
            return 1;
    }
    return 0;
}

char *
build_part_choices(struct partition *parts[], const int part_count)
{
    char *list[part_count];
    char *tmp, *tmp2;
    int i;
    size_t max_len, len;

    //printf("part_count=%d\n", part_count);
    if (part_count <= 0)
        return NULL;
    max_len = 0;
    for (i = 0; i < part_count; i++) {
        len = strlen(parts[i]->description) - strcount(parts[i]->description, ',');
        if (len > max_len)
            max_len = len;
    }
    // pad with spaces
    for (i = 0; i < part_count; i++) {
        list[i] = xasprintf("%-*s", (int)max_len, parts[i]->description);
    }
    max_len = strlen("n/a");
    for (i = 0; i < part_count; i++) {
        if (parts[i]->size > 0 && strlen(size_desc(parts[i]->size)) > max_len)
            max_len = strlen(size_desc(parts[i]->size));
    }
    // add and pad
    for (i = 0; i < part_count; i++) {
        tmp = xasprintf("%s  %-*s", list[i], (int)max_len,
                (parts[i]->size > 0) ? size_desc(parts[i]->size) : "n/a");
        free(list[i]);
        list[i] = tmp;
    }
    max_len = strlen("n/a");
    for (i = 0; i < part_count; i++) {
        if (parts[i]->op.filesystem != NULL) {
            if (strlen(parts[i]->op.filesystem) > max_len)
                max_len = strlen(parts[i]->op.filesystem);
        } else if (parts[i]->fstype != NULL && strlen(parts[i]->fstype) > max_len)
            max_len = strlen(parts[i]->fstype);
    }
    for (i = 0; i < part_count; i++) {
        tmp = xasprintf("%s  %-*s", list[i], (int)max_len,
                (parts[i]->op.filesystem != NULL) ? parts[i]->op.filesystem :
                (parts[i]->fstype != NULL) ? parts[i]->fstype : "n/a");
        free(list[i]);
        list[i] = tmp;
    }
    max_len = 0;
    for (i = 0; i < part_count; i++) {
        if (parts[i]->op.mountpoint != NULL && strlen(parts[i]->op.mountpoint) > max_len)
            max_len = strlen(parts[i]->op.mountpoint);
    }
    if (max_len > 0)
        for (i = 0; i < part_count; i++) {
            tmp = xasprintf("%s  %-*s", list[i], (int)max_len,
                    (parts[i]->op.mountpoint != NULL) ? parts[i]->op.mountpoint : "");
            free(list[i]);
            list[i] = tmp;
        }
    /* PHEW */
    tmp = list[0];
    //printf("<%s>\n", list[0]);
    for (i = 1; i < part_count; i++) {
        //printf("<%s>\n", list[i]);
        tmp2 = xasprintf("%s, %s", tmp, list[i]);
        free(list[i]);
        free(tmp);
        tmp = tmp2;
    }
    return tmp;
}

static char *
fs_to_choice(char *fs)
{
    static char *choicefmt = NULL;
    char *tmp;

    // Cache the format string
    if (choicefmt == NULL) {
        debconf_metaget(debconf, "partconf/internal-create-fs-choice", "description");
        choicefmt = strdup(debconf->value);
    }
    tmp = xasprintf(choicefmt, fs);
    return tmp;
}

char *
build_fs_choices(void)
{
    char *tmp, *tmp2;
    int i;

    tmp = NULL;
    for (i = 0; i < fs_count; i++) {
        if (tmp == NULL)
            tmp2 = fs_to_choice(filesystems[i]);
        else
            tmp2 = xasprintf("%s, %s", tmp, fs_to_choice(filesystems[i]));
        free(tmp);
        tmp = tmp2;
    }
    return tmp;
}

// Check /proc/filesystems and /sbin/mkfs.* to figure out which
// filesystems are available.
int
get_all_filesystems(void)
{
    FILE *fp, *fptmp;
    char buf[1024], buf2[1024], *ptr;

    fp = fopen("/proc/filesystems", "r");
    if (fp == NULL)
        return 0;
    fs_count = 0;
    while ((ptr = fgets(buf, sizeof(buf), fp)) != NULL) {
        if (strstr(ptr, "nodev") == ptr)
            continue;
        while (*ptr != '\0' && isspace(*ptr))
            ptr++;
        if (*ptr == '\0')
            continue;
        filesystems[fs_count] = ptr;
        while (*ptr != '\0' && !isspace(*ptr) && *ptr != '\n')
            ptr++;
        *ptr = '\0';
        // Check if there's a corresponding mkfs program
        snprintf(buf2, sizeof(buf2)-1, "/sbin/mkfs.%s", filesystems[fs_count]);
        if ((fptmp = fopen(buf2, "r")) == NULL)
            continue;
        fclose(fptmp);
        filesystems[fs_count] = strdup(filesystems[fs_count]);
        fs_count++;
    }
    fclose(fp);
    return fs_count;
}

static int
sanity_checks(void)
{
    int i, j, ok;
    static char *bad_mounts[] = {
        "/proc",
        "/dev",
        "/etc",
        NULL
    };

    // Check for root file system
    if (!check_proc_mounts("")) {
        ok = 0;
        for (i = 0; i < part_count; i++) {
            if (parts[i]->op.mountpoint == NULL)
                continue;
            if (strcmp(parts[i]->op.mountpoint, "/") == 0) {
                ok = 1;
                break;
            }
        }
        if (!ok) {
            debconf_input(debconf,"critical", "partconf/sanity-no-root");
            debconf_go(debconf);
            return 0;
        }
    }
    // Check for bad mount points (/proc, /dev, /etc)
    ok = 1;
    for (i = 0; i < part_count; i++) {
        if (parts[i]->op.mountpoint == NULL)
            continue;
        for (j = 0; bad_mounts[j] != NULL; j++) {
            if (strcmp(parts[i]->op.mountpoint, bad_mounts[j]) == 0) {
                debconf_subst(debconf, "partconf/sanity-bad-mount", 
			     "MOUNT", parts[i]->op.mountpoint);
                debconf_input(debconf, "critical", "partconf/sanity-bad-mount");
                debconf_go(debconf);
                ok = 0;
                break;
            }
        }
    }
    if (!ok)
        return 0;
    // Check for double mounts
    ok = 1;
    for (i = 0; i < part_count; i++) {
        if (parts[i]->op.mountpoint == NULL)
            continue;
        if (check_proc_mounts(parts[i]->op.mountpoint)) {
            debconf_subst(debconf, "partconf/sanity-double-mount",
                          "MOUNT", parts[i]->op.mountpoint);
            debconf_input(debconf, "critical", "partconf/sanity-double-mount");
            debconf_go(debconf);
            ok = 0;
        }
        else
            for (j = i+1; j < part_count; j++) {
                if (parts[j]->op.mountpoint == NULL)
                    continue;
                if (strcmp(parts[i]->op.mountpoint, parts[j]->op.mountpoint) == 0) {
                    debconf_subst(debconf,"partconf/sanity-double-mount",
                                  "MOUNT", parts[i]->op.mountpoint);
                    debconf_input(debconf, "critical",
                                  "partconf/sanity-double-mount");
                    debconf_go(debconf);
                    ok = 0;
                    break;
                }
            }
    }
    if (!ok)
        return 0;
    if (will_mkfs()) {
        // Confirm
        // XXX Can we build a sane substitution string? Would be nice to say
        // XXX something like "Partitions 1, 3 and 7 on IDE3 master", but this
        // XXX is probably hard, especially for i18n. :-( If multi-line
        // XXX substitutions worked, we could just list the partitions.
        debconf_input(debconf, "critical", "partconf/confirm");
        if (debconf_go(debconf) == 30)
            return 0;
        debconf_get(debconf, "partconf/confirm");
        if (strcmp(debconf->value, "false") == 0)
            return 0;
    }
    return 1;
}

static int
mountpoint_sort_func(const void *v1, const void *v2)
{
    struct partition *p1, *p2;
    char *m1, *m2;

    p1 = *(struct partition **)v1;
    p2 = *(struct partition **)v2;
    m1 = p1->op.mountpoint;
    m2 = p2->op.mountpoint;
    // have to sort the NULLs too, because of how quicksort works
    if (m1 == NULL && m2 == NULL)
        return 0;
    else if (m1 == NULL)
        return -1;
    else if (m2 == NULL)
        return 1;
    if (strstr(m1, m2) == m1)
        return 1;
    else if (strstr(m2, m1) == m2)
        return -1;
    else
        return strcmp(m1, m2);
}

/*
 * Like mkdir -p
 */
static void
makedirs(const char *dir)
{
    DIR *d;
    char *dirtmp, *basedir;

    if ((d = opendir(dir)) != NULL) {
        closedir(d);
        return;
    }
    if (mkdir(dir, 0755) < 0) {
        dirtmp = strdup(dir);
        basedir = dirname(dirtmp);
        makedirs(basedir);
        free(dirtmp);
        mkdir(dir, 0755);
    }
}

static int
mkfstab(void)
{
    char *cmd = "/usr/lib/partconf/mkfstab";

    append_message("partconf: Create fstab\n");
    return system(cmd);
}

// This is a swap partition IFF
//   The new fs is swap
// or
//   The existing fs is swap and we have no new fs
#define IS_SWAP(p)  (((p)->op.filesystem != NULL && strcmp((p)->op.filesystem, "swap") == 0) ||\
       ((p)->op.filesystem == NULL && (p)->fstype != NULL && strcmp((p)->fstype, "swap") == 0))

static void
finish(void)
{
    int i, ret;
    char *cmd, *mntpt, *errq = NULL, *fs;

    // Sort the partitions according to the order they have to be mounted
    qsort(parts, part_count, sizeof(struct partition *), mountpoint_sort_func);
    for (i = 0; i < part_count; i++) {
        fs = parts[i]->op.filesystem;
        if (fs == NULL)
            fs = parts[i]->fstype;
        else {
            // Create the file system/swap
            if (strcmp(fs, "swap") == 0) {
                append_message("partconf: Creating swap on %s\n", parts[i]->path);
                cmd = xasprintf("mkswap %s >/dev/null 2>>/var/log/messages", parts[i]->path);
                ret = system(cmd);
                free(cmd);
                if (ret != 0) {
                    errq = "partconf/failed-mkswap";
                    break;
                }
            } else {
		char *mkfs_opts="";
		/* mkfs.reiserfs is interactive unless passed a -q */
		if (strcmp(fs, "reiserfs") == 0) {
			mkfs_opts="-q";
		}
		/* mkfs.xfs will not overwrite existing filesystems unless
		 * one passes -f. at this point, user has claimed "yes, do
		 * as I say!" so let's force it here. */
		else if (strcmp(fs, "xfs") == 0) {
		  	mkfs_opts="-f";
		}
                append_message("partconf: Creating %s file system on %s\n", fs, parts[i]->path);
                cmd = xasprintf("mkfs.%s %s %s >/dev/null 2>>/var/log/messages", fs, mkfs_opts, parts[i]->path);
                ret = system(cmd);
                free(cmd);
                if (ret != 0) {
                    errq = "partconf/failed-mkfs";
                    debconf_subst(debconf,errq, "FS", parts[i]->op.filesystem);
                    break;
                }
            }
        }
        if (fs != NULL) {
            if (strcmp(fs, "swap") == 0 && !check_proc_swaps(parts[i]->path)) {
                // Activate swap
                append_message("partconf: Activating swap on %s\n", parts[i]->path);
                cmd = xasprintf("swapon %s >/dev/null 2>>/var/log/messages", parts[i]->path);
                ret = system(cmd);
                free(cmd);
                /* 
                 * Since we check if the swap is already activated, it may
                 * make sense to make this fatal. For now, it is, anyway.
                 */
                if (ret != 0) {
                    errq = "partconf/failed-swapon";
                    break;
                }
            } else if (parts[i]->op.mountpoint != NULL) {
                // And mount
                append_message("partconf: Mounting %s on %s\n",
                        parts[i]->path, parts[i]->op.mountpoint);
                mntpt = xasprintf("/target%s", parts[i]->op.mountpoint);
                makedirs(mntpt);
                fs = parts[i]->op.filesystem ? parts[i]->op.filesystem : parts[i]->fstype;
                ret = mount(parts[i]->path, mntpt, fs, 0xC0ED0000, NULL);
                // Ignore failure due to unknown filesystem
                if (ret < 0 && errno != ENODEV) {
                    append_message("mount: %s\n", strerror(errno));
                    errq = "partconf/failed-mount";
                    debconf_subst(debconf, errq, "MOUNT", mntpt);
                    free(mntpt);
                    break;
                }
                free(mntpt);
            }
        }
    }
    if (errq != NULL) {
        debconf_subst(debconf, errq, "PARTITION", parts[i]->path);
        debconf_input(debconf,"critical", errq);
        debconf_go(debconf);
        exit(30);
    }
    mkfstab();

    exit(0);
}

static struct partition *curr_part = NULL;
static char *curr_q = NULL;

static int
partition_menu(void)
{
    char *choices;
    
    /* Get partition information */
    choices = build_part_choices(parts, part_count);
    //printf("Choices: <%s>\n", choices);
    debconf_subst(debconf, "partconf/partitions", "PARTITIONS", choices);
    free(choices);
    debconf_input(debconf, "critical", "partconf/partitions");
    curr_part = NULL;
    return 0;
}

int
streqcomma(const char *s1, const char *s2)
{
    while (*s1 && *s2) {
        if (*s1 == '\\')
            s1++;
        if (*s1 != *s2)
            return 0;
        s1++;
        s2++;
    }
    return *s1 == *s2 || *s2 == ' ';
}

static int
filesystem(void)
{
    int i;
    char *partname;

    debconf_get(debconf, "partconf/partitions");
    if (strcmp(debconf->value, "Finish") == 0) {
        if (!sanity_checks())
            return 1; // will back up
        finish();
    }
    if (strcmp(debconf->value, "Abort") == 0)
        return -1;
    partname = strdup(debconf->value);
    curr_part = NULL;
    for (i = 0; i < part_count; i++) {
        //fprintf(stderr, "pname='%s', pdesc='%s'\n", partname, parts[i]->description);
        if (streqcomma(parts[i]->description, partname)) {
//        if (strstr(partname, parts[i]->description) == partname) {
            curr_part = parts[i];
            break;
        }
    }
    if (curr_part == NULL)
        return -1;
    if (curr_part->fstype != NULL) {
        curr_q = "partconf/existing-filesystem";
        debconf_subst(debconf, curr_q, "FSTYPE", curr_part->fstype);
        debconf_set(debconf, curr_q, "Leave the file system intact");
    } else
        curr_q = "partconf/create-filesystem";
    debconf_subst(debconf, curr_q, "FSCHOICES", fschoices);
    debconf_subst(debconf, curr_q, "PARTITION", curr_part->path);
    debconf_input(debconf, "critical", curr_q);
    return 0;
}

static int
mountpoint(void)
{
    int i;

    debconf_get(debconf, curr_q);
    if (strcmp(debconf->value, "Leave the file system intact") == 0) {
        free(curr_part->op.filesystem);
        curr_part->op.filesystem = NULL;
        if (curr_part->fstype != NULL && strcmp(curr_part->fstype, "swap") == 0)
            return 0;
    }
    else if (strcmp(debconf->value, "Create swap space") == 0) {
        free(curr_part->op.filesystem);
        curr_part->op.filesystem = strdup("swap"); // special case
        free(curr_part->op.mountpoint);
        curr_part->op.mountpoint = NULL;
        return 0;
    } else {
        char *tmp = strdup(debconf->value);

        for (i = 0; i < fs_count; i++) {
            if (strcmp(tmp, fs_to_choice(filesystems[i])) == 0)
                break;
        }
        free(tmp);
        if (i == fs_count)
            return -1;
        free(curr_part->op.filesystem);
        curr_part->op.filesystem = strdup(filesystems[i]);
    }
    if (curr_part->op.filesystem == NULL || strcmp(curr_part->op.filesystem, "swap") != 0) {
        // TODO: default to current mount point, if any
        debconf_subst(debconf, "partconf/mountpoint", "PARTITION", curr_part->path);
        debconf_input(debconf, "critical", "partconf/mountpoint");
    }
    return 0;
}

static int do_mount_manual = 0;

static int
mountpoint_manual(void)
{
    if (curr_part->op.filesystem != NULL && strcmp(curr_part->op.filesystem, "swap") == 0)
        return 0;
    do_mount_manual = 0;
    debconf_get(debconf, "partconf/mountpoint");
    if (strcmp(debconf->value, "Don't mount it") == 0) {
        free(curr_part->op.mountpoint);
        curr_part->op.mountpoint = NULL;
    } else if (strcmp(debconf->value, "Enter manually") == 0) {
        debconf_subst(debconf, "partconf/mountpoint-manual", "PARTITION", curr_part->path);
	debconf_input(debconf, "critical", "partconf/mountpoint-manual");
	do_mount_manual = 1;
    } else {
	//printf("Setting mountpoint to %s\n", debconf->value);
        free(curr_part->op.mountpoint);
        curr_part->op.mountpoint = strdup(debconf->value);
    }
    return 0;
}

static int
fixup(void)
{
    if (!do_mount_manual)
	return 0;
    debconf_get(debconf,"partconf/mountpoint-manual");
    free(curr_part->op.mountpoint);
    curr_part->op.mountpoint = strdup(debconf->value);
    return 0;
}

#ifndef TEST
int
main(void)
{
    int i, state = 0, ret;
    int (*states[])() = {
        partition_menu,
        filesystem,
        mountpoint,
        mountpoint_manual,
        fixup, // never does an INPUT, just handles the manual mountpoint result
        NULL
    };

    /* FIXME: How can we tell which file system modules to load?  */
    char *file_system_modules[] = {"ext2", "ext3", "ext4", "reiserfs", "jfs", "xfs", NULL};

    debconf = debconfclient_new();
    debconf_capb(debconf, "backup");
    ped_exception_set_handler(my_exception_handler);

    for (i = 0; file_system_modules[i]; i++)
	modprobe(file_system_modules[i]);

    if (check_proc_mounts("")) {
        // Chicken out if /target is already mounted
        debconf_input(debconf, "critical", "partconf/already-mounted");
        debconf_go(debconf);
        debconf_get(debconf,"partconf/already-mounted");
        if (strcmp(debconf->value, "false") == 0)
            return 0;
    }
    if (!umount_target()) {
        debconf_input(debconf, "critical", "partconf/umount-failed");
        debconf_go(debconf);
        return 1;
    }
    if ((part_count = get_all_partitions(parts, MAX_PARTS, false, 0)) <= 0) {
        debconf_input(debconf, "critical", "partconf/no-partitions");
        debconf_go(debconf);
        return 1;
    }
    if (get_all_filesystems() <= 0) {
        debconf_input(debconf, "critical", "partconf/no-filesystems");
        debconf_go(debconf);
        return 1;
    }
    fschoices = build_fs_choices();
    while (state >= 0) {
        ret = states[state]();
        if (ret < 0)
	    return 10;
        else if (ret == 0 && debconf_go(debconf) == 0)
            state++;
        else
            state--;
        if (states[state] == NULL)
            state = 0;
    }
    return ret;
}
#else
int
main(int argc, char **argv)
{
    assert(!streqcomma("foo", "foobar"));
    assert(streqcomma("foo", "foo bar"));
    return 0;
}
#endif
