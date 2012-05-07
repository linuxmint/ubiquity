CFLAGS=-Wall -Os -D_GNU_SOURCE
LIBS=-lparted

all: parted_server parted_devices partmap

parted_server: parted_server.c
	$(CC) $(CFLAGS) parted_server.c $(LIBS) -o parted_server

parted_devices: parted_devices.c
	$(CC) $(CFLAGS) parted_devices.c $(LIBS) -o parted_devices

partmap: partmap.c
	$(CC) $(CFLAGS) partmap.c $(LIBS) -o partmap

clean:
	rm -f parted_server parted_devices partmap

test:
	cd test && ./conversions

.PHONY: clean
