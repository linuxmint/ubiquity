#include <stdio.h>
#include <string.h>
#include <parted/parted.h>

int
main(int argc, char *argv[])
{
	const char *bootdisk;
	int bootpart = -1;
	PedDevice *dev;
	PedDisk *disk;
	PedPartition *part;
	int i;

	if (argc <= 1) {
		fprintf(stderr, "Usage: ensure-active BOOTDISK [BOOTPART]\n");
		return 1;
	}

	bootdisk = argv[1];
	if (argc > 2 && *argv[2]) {
		char *end;
		bootpart = strtol(argv[2], &end, 0);
		if (*end || bootpart < 1 || bootpart > 4)
			bootpart = -1;
	}

	ped_exception_fetch_all();
	dev = ped_device_get(bootdisk);
	if (!dev) {
		fprintf(stderr, "Can't open %s\n", bootdisk);
		return 1;
	}
	disk = ped_disk_new(dev);
	if (!disk || !disk->type || !disk->type->name) {
		fprintf(stderr, "Can't read partition table from %s\n",
			bootdisk);
		return 1;
	}
	if (strcmp(disk->type->name, "msdos") != 0) {
		/* this only matters for DOS partition tables */
		fprintf(stderr, "No DOS partition table on %s; nothing to do\n",
			bootdisk);
		return 0;
	}

	for (part = ped_disk_next_partition(disk, NULL); part;
	     part = ped_disk_next_partition(disk, part)) {
		if (ped_partition_is_active(part) &&
		    ped_partition_get_flag(part, PED_PARTITION_BOOT)) {
			printf("Partition %d of %s is already active\n",
			       part->num, bootdisk);
			return 0;
		}
	}

	if (bootpart) {
		part = ped_disk_get_partition(disk, bootpart);
		if (part && ped_partition_is_active(part)) {
			printf("Setting partition %d of %s to active... ",
			       bootpart, bootdisk);
			ped_exception_fetch_all();
			ped_partition_set_flag(part, PED_PARTITION_BOOT, 1);
			ped_exception_leave_all();
			if (ped_exception) {
				ped_exception_catch();
				puts("failed.");
			} else {
				ped_disk_commit(disk);
				puts("done.");
				return 0;
			}
		}
	}

	/* We don't care at this point; just pick the first primary
	 * partition that exists.
	 */
	for (i = 1; i <= 4; ++i) {
		part = ped_disk_get_partition(disk, i);
		if (!part || !ped_partition_is_active(part))
			continue;
		printf("Setting partition %d of %s to active... ",
		       i, bootdisk);
		ped_exception_fetch_all();
		ped_partition_set_flag(part, PED_PARTITION_BOOT, 1);
		ped_exception_leave_all();
		if (ped_exception) {
			ped_exception_catch();
			if (i < 4)
				puts("failed; trying next primary partition.");
			else
				puts("failed.");
			continue;
		}
		ped_disk_commit(disk);
		puts("done.");
		return 0;
	}

	fputs("Failed to make any primary partition active.  Hope your BIOS "
	      "doesn't mind there being no active partition!\n", stderr);
	return 1;
}
