bin_PROGRAMS = parted_server parted_devices partmap
bin_SCRIPTS = partman partman-command partman-commit

parted_server_SOURCES = parted_server.c
parted_server_LDADD = $(libparted_fs_resize_LIBS) $(libparted_LIBS)

parted_devices_SOURCES = parted_devices.c
parted_devices_LDADD = $(libparted_LIBS)

partmap_SOURCES = partmap.c
partmap_LDADD = $(libparted_LIBS)

check-local:
	cd test && ./conversions
