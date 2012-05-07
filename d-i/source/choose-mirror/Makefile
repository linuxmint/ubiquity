export USE_HTTP=1
#export USE_FTP=1
USE_FTP_MANUAL=1

DEB_HOST_ARCH ?= $(shell dpkg-architecture -qDEB_HOST_ARCH)

CFLAGS=-Wall -g -D_GNU_SOURCE -DARCH_TEXT='"$(DEB_HOST_ARCH)"'
templates=debian/choose-mirror-bin.templates-in

ifeq (1,${USE_HTTP})
CFLAGS:=$(CFLAGS) -DWITH_HTTP
templates:=$(templates) debian/choose-mirror-bin.templates.http-in
endif
ifeq (1,${USE_FTP})
CFLAGS:=$(CFLAGS) -DWITH_FTP
templates:=$(templates) debian/choose-mirror-bin.templates.ftp.base-in
templates:=$(templates) debian/choose-mirror-bin.templates.ftp.sel-in
endif
ifeq (1,${USE_FTP_MANUAL})
CFLAGS:=$(CFLAGS) -DWITH_FTP_MANUAL
templates:=$(templates) debian/choose-mirror-bin.templates.ftp.base-in
endif
templates:=$(templates) debian/choose-mirror-bin.templates.both-in

OBJS=$(subst .c,.o,$(wildcard *.c))
BIN=choose-mirror
LIBS=-ldebconfclient -ldebian-installer

# Derivative distributions may want to change these.
#MIRRORLISTURL=http://anonscm.debian.org/viewvc/webwml/webwml/english/mirror/Mirrors.masterlist?revision=HEAD
MASTERLIST=Mirrors.masterlist.ubuntu

ifdef DEBUG
CFLAGS:=$(CFLAGS) -DDODEBUG
else
CFLAGS:=$(CFLAGS) -Os -fomit-frame-pointer
endif

all: $(BIN) debian/choose-mirror-bin.templates

ifdef MIRRORLISTURL
# Freshen Mirrors.masterlist file, but allow failure.
$(MASTERLIST): force-try-update
	if [ "$$ONLINE" != n ]; then \
		if wget -nv '$(MIRRORLISTURL)' -O - > $@.new && \
		   test -s $@.new; then \
        		mv $@.new $@; \
		else \
			rm -f $@.new; \
		fi; \
	fi
force-try-update: ;
endif

debian/iso_3166.tab:
	isoquery -c | cut -f 1,4 | sort >debian/iso_3166.tab

debian/httplist-countries: $(MASTERLIST) debian/iso_3166.tab
	./mirrorlist httplist $^

debian/ftplist-countries: $(MASTERLIST) debian/iso_3166.tab
	./mirrorlist ftplist $^

debian/choose-mirror-bin.templates: $(MASTERLIST) $(templates) debian/httplist-countries debian/ftplist-countries debian/iso_3166.tab
	# Grab ISO codes from iso-codes package
	./get-iso-codes
	# Build the templates
	./mktemplates $(templates)

mirrors_http.h: $(MASTERLIST) debian/iso_3166.tab
	if [ "$$USE_HTTP" ]; then ./mirrorlist http $^; fi

mirrors_ftp.h: $(MASTERLIST) debian/iso_3166.tab
	if [ "$$USE_FTP" ]; then ./mirrorlist ftp $^; fi

choose-mirror.o: mirrors_http.h mirrors_ftp.h

$(BIN): $(OBJS)
	$(CC) -o $(BIN) $(OBJS) $(LIBS) $(LDFLAGS)

strip: $(BIN)
	strip --remove-section=.comment --remove-section=.note $(BIN)

# Size optimized and stripped binary target.
small: CFLAGS:=-Os $(CFLAGS) -DSMALL
small: clean strip debian/choose-mirror-bin.templates
	ls -l $(BIN)

ftp: CFLAGS:=-Os -Wall -g -D_GNU_SOURCE -DWITH_FTP -DSMALL
ftp: clean strip
	ls -l $(BIN)

http: CFLAGS:=-Os -Wall -g -D_GNU_SOURCE -DWITH_HTTP -DSMALL
http: clean strip
	ls -l $(BIN)

clean:
	rm -f $(BIN) $(OBJS) *~ mirrors_*.h
	rm -f debian/templates-countries debian/httplist-countries debian/ftplist-countries
	rm -f demo demo.templates
	rm -rf debian/iso-codes/ debian/pobuild*/
	rm -f debian/iso_3166.tab

reallyclean: clean
	rm -f debian/choose-mirror-bin.templates
ifdef MIRRORLISTURL
	rm -f Mirrors.masterlist
endif

.PHONY: demo
demo: choose-mirror demo.templates
	ln -sf choose-mirror demo
	DEBCONF_DEBUG=developer /usr/share/debconf/frontend ./demo

demo.templates: debian/choose-mirror-bin.templates
	po2debconf $< > $@
