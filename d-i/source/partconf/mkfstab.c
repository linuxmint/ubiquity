#include <errno.h>

#include "xasprintf.h"
#include "mkfstab.h"

static int has_device(struct fstab_entry *entry) {
	return (strcmp(entry->typ, "proc") != 0
		&& strcmp(entry->typ, "tmpfs") != 0);
}

char *find_mountdevice(const char *mountpoint, char *default_device) {
	FILE *fmounts = NULL;
	char line[1024];
	char *newdevice = NULL;

	newdevice = default_device+1;

	fmounts = fopen("/proc/mounts", "r");
	if(fmounts == NULL) {
		fprintf(stderr, "%s: %s\n", strerror(errno), "/proc/mounts");
		return(strdup(newdevice));
	}

	while(fgets(line, 1024, fmounts) != NULL) {
		char filesystem[1024];
		char mntpoint[1024];

		sscanf(line, "%s %s %*s", filesystem, mntpoint);
		
		/* skip loopback mount cdrom */
		if(strcmp(mountpoint, "/cdrom") == 0
		  && (NULL != strstr(filesystem, "loop")))
			continue;
		if(strcasecmp(mntpoint, mountpoint) == 0) {
			return(strdup(filesystem));
		}
	}

	fclose(fmounts);
	return(strdup(newdevice));
}

void insert_line(const char *line) {
	int i = 0;
	struct fstab_entry *dummy = NULL;
	char filesystem[1024];
	char mountpoint[1024];
	char typ[1024];
	char options[1024];

	if(line[0] == '#')
		return;

	dummy = malloc(sizeof(*dummy));
	if(dummy == NULL) {
		fprintf(stderr, "Unable to allocate memory!\n");
		exit(EXIT_FAILURE);
	}

	dummy->filesystem = NULL;
	dummy->mountpoint = NULL;
	dummy->typ = NULL;
	dummy->options = NULL;
	dummy->dump = 0;
	dummy->pass = 0;

	sscanf(line, "%s %s %s %s %*s %*s",
		filesystem, mountpoint, typ, options);

	if(strlen(filesystem) > 0) {
		if(filesystem[0] == '$') {
			dummy->filesystem = find_mountdevice(mountpoint, filesystem);
		} else {
			dummy->filesystem = strdup(filesystem);
		}
	}
	if(strlen(mountpoint) > 0) {
		if (strcmp(mountpoint, TARGET) == 0)
			dummy->mountpoint = strdup("/");
		else if (strstr(mountpoint, TARGET) == mountpoint)
			dummy->mountpoint = strdup(mountpoint + strlen(TARGET));
		else
			dummy->mountpoint = strdup(mountpoint);
        }
	if(strlen(typ) > 0)
		dummy->typ = strdup(typ);

	/* handle reiserfs */
	if(strstr(dummy->typ, "reiserfs") && strstr(dummy->mountpoint, "/boot")) {
		dummy->options = strdup("notail");
	} else if(strstr(dummy->typ, "swap")) {
		dummy->options = strdup("sw");
	} else if(strcmp(options, "rw") != 0) {
		dummy->options = strdup(options);
	} else {
		if((strcmp(dummy->mountpoint, "/") == 0) &&
		  ((strcmp(dummy->typ, "ext2") == 0) ||
		   (strcmp(dummy->typ, "ext3") == 0) ||
		   (strcmp(dummy->typ, "ext4") == 0))) {
			dummy->options = strdup("errors=remount-ro");
		} else {
			dummy->options = strdup("defaults");
		}
	}

#ifdef DEBUG
	printf("%s %s", dummy->filesystem, dummy->mountpoint);
#endif

	/* check if an record with this entry already exists */
	for(i=0; i<count_entries; i++) {
		if(strcasecmp(dummy->filesystem, entries[i]->filesystem) == 0) {
#ifdef DEBUG
			printf(" -> insert (fs): %d\n", i);
#endif
			free(entries[i]);
			entries[i] = dummy;
			return;
		}
		if(strcasecmp(dummy->mountpoint, entries[i]->mountpoint) == 0) {
#ifdef DEBUG
			printf(" -> insert (mnt): %d\n", i);
#endif
			free(entries[i]);
			entries[i] = dummy;
			return;
		}
	}

#ifdef DEBUG
	printf(" -> pos: %d\n", i);
#endif

	if(count_entries >= MAX_ENTRIES) {
		fprintf(stderr, "Unable to add entry... max entry count reached!\n");
		return;
	}

	entries[i] = dummy;
	count_entries++;
}

void get_fstab_d_dir() {
	DIR *fstab_d = NULL;
	struct dirent *dentry;

	fstab_d = opendir(FSTAB_D);
	if(fstab_d == NULL) {
		fprintf(stderr, "%s: %s\n", strerror(errno), FSTAB_D);
		return;
	}

	while((dentry = readdir(fstab_d)) != NULL) {
		struct stat sbuf;
		char *fullname = NULL;
		FILE *file = NULL;
		char line[1024];
		
		/* ignore dot-files */
		if(dentry->d_name[0] == '.')
			continue;

		/* skipping directories */
		fullname = xasprintf("%s/%s", FSTAB_D, dentry->d_name);
		if(stat(fullname, &sbuf) == -1) {
			fprintf(stderr, "%s: %s\n", strerror(errno), fullname);
			continue;
		}
		if(!S_ISREG(sbuf.st_mode))
			continue;

		file = fopen(fullname, "r");
		if(file == NULL) {
			fprintf(stderr, "%s: %s\n", strerror(errno), fullname);
			continue;
		}

		while(fgets(line, 1024, file) != NULL) {
			char filesystem[1024];


			sscanf(line, "%s %*s", filesystem);
			if(filesystem[0] == '/') {
				struct stat buf;
				if(stat(filesystem, &buf) != 0) {
					continue;
				}
			}

			insert_line(line);
		}

		fclose(file);
		free(fullname);
	}

	closedir(fstab_d);
}

void get_filesystems() {
	FILE *fmounts = NULL;
	char line[1024];

	fmounts = fopen("/proc/mounts", "r");
	if(fmounts == NULL) {
		fprintf(stderr, "%s: %s\n", strerror(errno), "/proc/mounts");
		return;
	}

	while(fgets(line, 1024, fmounts) != NULL) {
		char mountpoint[1024];

		sscanf(line, "%*s %s %*s", mountpoint);
		if (strstr(mountpoint, TARGET) != mountpoint)
			continue;
		insert_line(line);
	}

	fclose(fmounts);
}

void get_swapspaces() {
	FILE *fswaps = NULL;
	char line[1024];

	fswaps = fopen("/proc/swaps", "r");
	if(fswaps == NULL) {
		fprintf(stderr, "%s: %s\n", strerror(errno), "/proc/swaps");
		return;
	}

	while(fgets(line, 1024, fswaps) != NULL) {
		char filesystem[1024];
		char *swline = NULL;

		if(line[0] != '/')
			continue;

		sscanf(line, "%s %*s %*s %*s %*s", filesystem);
		swline = xasprintf("%s\tnone\tswap\tsw", filesystem);
		insert_line(swline);
	}

	fclose(fswaps);
}

void mapdevfs(struct fstab_entry *entry) {
	char device[PATH_MAX] = "";

	if(entry->filesystem == NULL)
		return;

#ifdef DEBUG
	printf("Query devfs for: %s\n", entry->filesystem);
#endif

	di_system_devfs_map_from(entry->filesystem, device, PATH_MAX);
	if(device != NULL && strlen(device) > 0) {
#ifdef DEBUG
		printf("Mapped device: %s\n", device);
#endif
		free(entry->filesystem);
		entry->filesystem = strdup(device);
	}
}

#define ATTRIBUTE_UNUSED __attribute__ ((__unused__))

#ifndef TEST
int main(int argc ATTRIBUTE_UNUSED, char *argv[] ATTRIBUTE_UNUSED) {
	int i = 0;
	FILE *outfile = NULL;

#ifdef LOCAL
	printf("W: using local mode!\n\n");
#endif

	if (system("modprobe floppy 1>/dev/null 2>&1") != 0) {
		/* ignore failures */
	}

	get_filesystems();
	get_swapspaces();
	get_fstab_d_dir();

	mkdir(FSTAB_DIR, 0755); /* may not yet exist */
	
	outfile = fopen(FSTAB_FILE, "w");
	if(outfile == NULL)
		return(0);

#ifdef DEBUG
	printf("---------------------------------\n");
#endif
	/* Not using FSTAB_FILE because it contain /target/ which will
	 * be confusing when read after the boot from HD. */
	fprintf(outfile, HEADER, "/etc/fstab");
	for(i=0; i<count_entries; i++) {
		int pass;

		if(!has_device(entries[i]))
			pass = 0;
		else {
			if(strcmp(entries[i]->mountpoint, "/cdrom") == 0
			   || strcmp(entries[i]->mountpoint, "/floppy") == 0
			   || strcmp(entries[i]->typ, "swap") == 0)
				pass = 0;
			else if(strcmp(entries[i]->mountpoint, "/") == 0)
				pass = 1;
			else
				pass = 2;

			mapdevfs(entries[i]);
		}
#ifdef DEBUG
		fprintf(stdout, "%s\t%s\t%s\t%s\t%d %d\n",
			entries[i]->filesystem, entries[i]->mountpoint,
			entries[i]->typ, entries[i]->options,
			0, pass);
#endif
		fprintf(outfile, "%s\t%s\t%s\t%s\t%d %d\n",
			entries[i]->filesystem, entries[i]->mountpoint,
			entries[i]->typ, entries[i]->options,
			0, pass);
	}

	fclose(outfile);

	return(EXIT_SUCCESS);
}
#else
int main(int argc ATTRIBUTE_UNUSED, char **argv ATTRIBUTE_UNUSED) {
	struct fstab_entry proc_entry = {"proc", "/proc", "proc", "defaults"};
	struct fstab_entry tmpfs_entry = {"none", "/tmp", "tmpfs", "defaults"};
	assert(!has_device(&proc_entry));
	assert(!has_device(&tmpfs_entry));
	return 0;
}
#endif
