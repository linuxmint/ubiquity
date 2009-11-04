ARCH := $(shell dpkg-architecture -qDEB_HOST_ARCH)
ifeq ($(ARCH),powerpc)
CFLAGS=-Wall -O2 -D_GNU_SOURCE
else
CFLAGS=-Wall -Os -D_GNU_SOURCE
endif
LIBS=-lparted

all: parted_server parted_devices partmap

parted_server: parted_server.c
	$(CC) $(CFLAGS) $(LIBS) parted_server.c -o parted_server

parted_devices: parted_devices.c
	$(CC) $(CFLAGS) $(LIBS) parted_devices.c -o parted_devices

partmap: partmap.c
	$(CC) $(CFLAGS) $(LIBS) partmap.c -o partmap

clean:
	rm -f parted_server parted_devices partmap

.PHONY: clean
