CFLAGS = -W -Wall

ifdef DEBUG
CFLAGS += -g3
endif

LIBS = -lparted

PARTCONF_OBJS = util.o partconf.o find-parts.o

all: partconf find-partitions mkfstab mountpoint

partconf: $(PARTCONF_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ -ldl -ldebconfclient -ldebian-installer -lparted

find-partitions: partconf.h find-parts.c util.o
	$(CC) $(CFLAGS) -o $@ -DFIND_PARTS_MAIN find-parts.c util.o -lparted

mkfstab: mkfstab.c mkfstab.h
	$(CC) $(CFLAGS) -o $@ mkfstab.c -ldebian-installer

mountpoint: mountpoint.c
	$(CC) $(CFLAGS) -o $@ mountpoint.c -ldebian-installer

util.o: util.c
partconf.o: partconf.c partconf.h
find-parts.o: find-parts.c partconf.h

small: CFLAGS += -Os
small: clean partconf find-partitions mkfstab mountpoint
	strip --remove-section=.comment --remove-section=.note partconf
	strip --remove-section=.comment --remove-section=.note find-partitions
	strip --remove-section=.comment --remove-section=.note mkfstab
	strip --remove-section=.comment --remove-section=.note mountpoint

test-mkfstab: mkfstab.c mkfstab.h
	$(CC) $(CFLAGS) -o test-mkfstab -DTEST mkfstab.c $(LIBS) -ldebian-installer

test-partconf: find-parts.o partconf.c partconf.h util.o
	$(CC) $(CFLAGS) -o test-partconf -DTEST partconf.c find-parts.o util.o $(LIBS) -ldebian-installer

check: test-mkfstab test-partconf
	./test-mkfstab
	./test-partconf

clean:
	-rm -f partconf find-partitions mkfstab mountpoint \
		test-mkfstab test-partconf *.o

.PHONY: all check clean small
