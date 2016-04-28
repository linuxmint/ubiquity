ifndef TARGETS
TARGETS=mapdevfs log-output resolv
endif

CFLAGS=-Wall -W -Os -fomit-frame-pointer -g
INSTALL=install
STRIPTOOL=strip
STRIP = $(STRIPTOOL) --remove-section=.note --remove-section=.comment

all: $(TARGETS)

mapdevfs: mapdevfs.c
	$(CC) $(CFLAGS) $(LDFLAGS) $^ -o $@ -ldebian-installer

log-output: log-output.c
	$(CC) $(CFLAGS) $(LDFLAGS) $^ -o $@ -ldebian-installer

resolv: resolv.c

strip: $(TARGETS)
	$(STRIP) $^

clean:
	rm -f $(OBJECTS) $(TARGETS)

test:
	$(MAKE) -C testsuite test
