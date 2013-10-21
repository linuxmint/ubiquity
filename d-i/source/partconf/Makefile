CFLAGS = -W -Wall

ifdef DEBUG
CFLAGS += -g3
endif

STRIP = strip

PARTCONF_OBJS = xasprintf.o util.o partconf.o find-parts.o

all: partconf find-partitions mkfstab mountpoint

partconf: LDLIBS := -ldl -ldebconfclient -ldebian-installer -lparted
partconf: $(PARTCONF_OBJS)

find-partitions: partconf.h find-parts.c util.o xasprintf.o
	$(CC) $(CFLAGS) -o $@ -DFIND_PARTS_MAIN find-parts.c util.o xasprintf.o -lparted

mkfstab: LDLIBS := -ldebian-installer
mkfstab: mkfstab.o xasprintf.o

mountpoint: LDLIBS := -ldebian-installer
mountpoint: mountpoint.o

xasprintf.o: xasprintf.c xasprintf.h
util.o: util.c
partconf.o: partconf.c partconf.h
find-parts.o: find-parts.c partconf.h

small: CFLAGS += -Os
small: clean partconf find-partitions mkfstab mountpoint
	$(STRIP) --remove-section=.comment --remove-section=.note partconf
	$(STRIP) --remove-section=.comment --remove-section=.note find-partitions
	$(STRIP) --remove-section=.comment --remove-section=.note mkfstab
	$(STRIP) --remove-section=.comment --remove-section=.note mountpoint

test-mkfstab: mkfstab.c mkfstab.h
	$(CC) $(CFLAGS) -o test-mkfstab -DTEST mkfstab.c xasprintf.o -lparted -ldebian-installer

test-partconf: find-parts.o partconf.c partconf.h util.o
	$(CC) $(CFLAGS) -o test-partconf -DTEST partconf.c find-parts.o util.o xasprintf.o -lparted -ldebian-installer

check: test-mkfstab test-partconf
	./test-mkfstab
	./test-partconf

clean:
	-rm -f partconf find-partitions mkfstab mountpoint \
		test-mkfstab test-partconf *.o

.PHONY: all check clean small
