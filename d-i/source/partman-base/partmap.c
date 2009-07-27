/*
 *	libparted-based partition map identifier
 *	Copyright (C) 2007	Robert Millan <rmh@aybabtu.com>
 *
 *	This program is free software; you can redistribute it and/or modify
 *	it under the terms of the GNU General Public License as published by
 *	the Free Software Foundation; either version 2 of the License, or
 *	(at your option) any later version.
 *
 *	This program is distributed in the hope that it will be useful,
 *	but WITHOUT ANY WARRANTY; without even the implied warranty of
 *	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the
 *	GNU General Public License for more details.
 *
 *	You should have received a copy of the GNU General Public License along
 *	with this program; if not, write to the Free Software Foundation, Inc.,
 *	51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#include <parted/parted.h>
#include <stdio.h>

int
main (int argc, char **argv)
{
	PedDevice *device;
	PedDisk *disk;

	if (argc != 2) {
		fprintf (stderr, "Usage: %s DEVICE\n", argv[0]);
		exit (1);
	}

	device = ped_device_get (argv[1]);
	if (!device)
		exit (1);

	disk = ped_disk_new (device);
	if (!disk)
		exit (1);

	printf ("%s\n", disk->type->name);

	return 0;
}
