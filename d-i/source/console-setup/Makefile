etcdir = /etc
prefix = /usr/local
xkbdir = $(shell pwd)/Keyboard/ckb
export xkbdir

bootprefix = $(patsubst %/usr,%/,$(prefix:%/=%))

SHELL = /bin/sh

all: build

build:
	cd Fonts && $(MAKE) build
	cd Keyboard && $(MAKE) build
	touch build

.PHONY: install
install: build
	install -d $(prefix)/share/consolefonts/
	install -m 644 Fonts/*.psf.gz $(prefix)/share/consolefonts/
	install -d $(prefix)/share/consoletrans
	install -m 644 Keyboard/acm/*.acm.gz $(prefix)/share/consoletrans
	install -d $(prefix)/share/console-setup
	install -m 644 Keyboard/MyKeyboardNames.pl $(prefix)/share/console-setup/KeyboardNames.pl
	install Keyboard/kbdnames-maker $(prefix)/share/console-setup
	install -d  $(prefix)/bin/
	install Keyboard/ckbcomp $(prefix)/bin/
	install -d  $(bootprefix)/bin/
	install setupcon $(bootprefix)/bin/
	install -d $(etcdir)/console-setup
	install -m 644 Keyboard/compose.*.inc $(etcdir)/console-setup/
	install -m 644 Keyboard/remap.inc $(etcdir)/console-setup/
	cp -r Keyboard/ckb/ $(etcdir)/console-setup/
#	cp Keyboard/rules $(etcdir)/console-setup/ckb/rules/console
#	cp Keyboard/rules.xml $(etcdir)/console-setup/ckb/rules/console.xml
	install -d $(etcdir)/default
	install -m 644 config.kbd $(etcdir)/default/keyboard
	install -m 644 config $(etcdir)/default/console-setup

.PHONY: uninstall
uninstall: build
	-for font in Fonts/*.psf.gz; do \
		rm $(prefix)/share/consolefonts/$${font##*/}; \
	done
	-for acm in Keyboard/acm/*.acm.gz; do \
		rm $(prefix)/share/consoletrans/$${acm##*/}; \
	done
	-rm -rf $(etcdir)/console-setup/
	-rm $(prefix)/bin/ckbcomp
	-rm $(bootprefix)/bin/setupcon

.PHONY: clean
clean:
	cd Fonts && $(MAKE) clean
	cd Keyboard && $(MAKE) clean
	-rm -f *~
	-rm -f build

.PHONY: maintainer-clean
maintainer-clean: clean
	cd Fonts && $(MAKE) maintainer-clean
	cd Keyboard && $(MAKE) maintainer-clean
