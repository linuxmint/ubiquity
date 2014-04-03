CFLAGS := -Os -g -Wall

all: ensure-active prep-bootdev

ensure-active: ensure-active.c
	$(CC) $(CFLAGS) $^ -o $@ -lparted

prep-bootdev: prep-bootdev.c
	$(CC) $(CFLAGS) $^ -o $@ -lparted

clean:
	rm -f ensure-active prep-bootdev
