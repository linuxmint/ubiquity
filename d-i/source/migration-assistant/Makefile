ARGS=-g -Wall -D_GNU_SOURCE
LIBXML_LIBS := $(shell xml2-config --libs)
LIBXML_CFLAGS := $(shell xml2-config --cflags)
BIN=$(DESTDIR)/usr/bin

all: ma-import ma-search-items ma-search-users

registry.o : registry.c registry.h
	$(CC) $(ARGS) -c registry.c
# TODO: Split XML utils out of regular utils.
ma-search-users : registry.o utils.o ma-search-users.c
	$(CC) $(ARGS) -c ma-search-users.c
	$(CC) $(ARGS) $(LIBXML_LIBS) -o ma-search-users ma-search-users.o registry.o utils.o

ma-search-items : registry.o utils.o search-items.c
	$(CC) $(ARGS) -c search-items.c
	$(CC) $(ARGS) $(LIBXML_LIBS) -o ma-search-items search-items.o registry.o utils.o

ma-import : gaim-import.o windows-import.o evolution-import.o firefox-import.o import.o utils.o
	$(CC) $(ARGS) -c import.c
	$(CC) $(ARGS) $(LIBXML_LIBS) -o ma-import gaim-import.o windows-import.o firefox-import.o evolution-import.o registry.o import.o utils.o

evolution-import.o : registry.o utils.o evolution-import.c
	$(CC) $(ARGS) $(LIBXML_CFLAGS) -c evolution-import.c

gaim-import.o : registry.o utils.o gaim-import.c
	$(CC) $(ARGS) $(LIBXML_CFLAGS) -c gaim-import.c

utils.o: utils.c utils.h
	$(CC) $(ARGS) $(LIBXML_CFLAGS) -c utils.c

firefox-import.o: firefox-import.c registry.o
	$(CC) $(ARGS) -c firefox-import.c

windows-import.o: windows-import.c utils.o registry.o
	$(CC) $(ARGS) -c windows-import.c

strip: ma-import ma-search-items
	strip --remove-section=.comment --remove-section=.note ma-import ma-search-items
clean :
	-rm -f *.o ma-import ma-search-items ma-search-users

install:
	install -d $(BIN)
	cp ma-import $(BIN)
	cp ma-search-items $(BIN)

.PHONY: clean install strip all
