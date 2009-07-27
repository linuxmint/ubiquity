ifndef TARGETS
TARGETS=mapdevfs log-output
endif

CFLAGS=-Wall -W -Os -fomit-frame-pointer -g
INSTALL=install
STRIPTOOL=strip
STRIP = $(STRIPTOOL) --remove-section=.note --remove-section=.comment

all: $(TARGETS)

mapdevfs: mapdevfs.c
	$(CC) $(CFLAGS) $^ -o $@ -ldebian-installer

log-output: log-output.c
	$(CC) $(CFLAGS) $^ -o $@ -ldebian-installer

strip: $(TARGETS)
	$(STRIP) $^

clean:
	rm -f $(OBJECTS) $(TARGETS)
