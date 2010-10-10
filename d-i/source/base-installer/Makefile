ifndef TARGETS
TARGETS=pkgdetails run-debootstrap
endif
ifeq ($(shell dpkg-architecture -qDEB_HOST_ARCH),i386)
TARGETS+=dmi-available-memory
endif

CFLAGS = -Wall -g -D_GNU_SOURCE

ifdef DEBUG
CFLAGS:=$(CFLAGS) -g3
else
CFLAGS:=$(CFLAGS) -Os -fomit-frame-pointer
endif

all: $(TARGETS)

pkgdetails: pkgdetails.c
	$(CC) $(CFLAGS) -o $@ $^

run-debootstrap: run-debootstrap.c
	$(CC) $(CFLAGS) -o $@ $^ -ldebconfclient -ldebian-installer

dmi-available-memory: dmi-available-memory.c
	$(CC) $(CFLAGS) -o $@ $^

small: CFLAGS:=-Os $(CFLAGS)
small: $(TARGETS)
	strip --remove-section=.comment --remove-section=.note $^
	ls -l $^

clean:
	-rm -f $(TARGETS)

test:
	$(MAKE) -C kernel test
