maindir ?= $(shell pwd)
kbddir := $(maindir)/Keyboard
fntdir := $(maindir)/Fonts
include rules.mk
include Keyboard/Makefile
include Fonts/Makefile

# The following two shortcuts will be redefined, so they can not be
# used in recipes and target specific variables.
. := $(maindir)
~ := main

prefix := /usr/local
# etcdir must be either /etc or
etcdir := $(prefix)/etc
bootprefix := $(patsubst %/usr,%/,$(prefix:%/=%))
mandir := $(prefix)/share/man

acmfiles := $(wildcard $./acm/*.acm)

gzipped_acmfiles := $(addsuffix .gz, $(acmfiles))

gzipped-acmfiles : $(gzipped_acmfiles)

build-common: gzipped-acmfiles

.PHONY: install-common
install-common: build-common
	install -d  $(bootprefix)/bin/
	install setupcon $(bootprefix)/bin/
	install -d $(etcdir)/default
	install -m 644 config/keyboard $(etcdir)/default/
	install -m 644 config/console-setup $(etcdir)/default/
	install -d $(mandir)/man1/
	install -m 644 man/setupcon.1 $(mandir)/man1/
	install -d $(mandir)/man5/
	install -m 644 man/keyboard.5 $(mandir)/man5/
	install -m 644 man/console-setup.5 $(mandir)/man5/

.PHONY: install-common-linux
install-common-linux: build-linux
	install -d $(prefix)/share/consolefonts/
	install -m 644 Fonts/*.psf.gz $(prefix)/share/consolefonts/
	install -d $(prefix)/share/consoletrans
	install -m 644 acm/*.acm.gz $(prefix)/share/consoletrans/
	install -d $(etcdir)/console-setup
	install -m 644 Keyboard/compose.*.inc $(etcdir)/console-setup/
	install -m 644 Keyboard/remap.inc $(etcdir)/console-setup/

.PHONY: install-common-freebsd
install-common-freebsd: build-freebsd
	install -d $(prefix)/share/syscons/fonts/
	install -m 644 Fonts/*.fnt $(prefix)/share/syscons/fonts/
	install -d $(prefix)/share/syscons/scrnmaps/
	install -m 644 Fonts/*.scm $(prefix)/share/syscons/scrnmaps/
	install -d $(prefix)/share/consoletrans
	install -m 644 acm/*.acm $(prefix)/share/consoletrans/
	install -d $(etcdir)/console-setup
	install -m 644 Fonts/terminfo $(etcdir)/console-setup/
	install -m 644 Fonts/termcap $(etcdir)/console-setup/
	install -m 644 Keyboard/dkey.*.inc $(etcdir)/console-setup/
	install -m 644 Keyboard/remap.inc $(etcdir)/console-setup/

.PHONY: install-ckbcomp
install-ckbcomp: 
	if [ -z "$(xkbdir)" ]; then \
		mkdir -p $(etcdir)/console-setup \
		&& cp -r Keyboard/ckb/ $(etcdir)/console-setup/ckb; \
	fi
	install -d $(prefix)/bin/
	install -m 755 Keyboard/ckbcomp $(prefix)/bin/
	install -d $(mandir)/man1/
	install -m 644 man/ckbcomp.1 $(mandir)/man1/

.PHONY : install-ckbcomp-mini
install-ckbcomp-mini: build-mini-linux build-mini-freebsd
	install -d $(prefix)/share/console-setup/
	-install -m 644 Keyboard/*.ekmap.gz $(prefix)/share/console-setup/
	-install -m 644 Keyboard/*.ekbd.gz $(prefix)/share/console-setup/
	install -m 644 Keyboard/charmap_functions.sh $(prefix)/share/console-setup/
	install -d $(prefix)/bin/
	install -m 755 Keyboard/ckbcomp-mini $(prefix)/bin/
	ln -s ckbcomp-mini $(prefix)/bin/ckbcomp
	install -d $(mandir)/man1/
	install -m 644 man/ckbcomp.1 $(mandir)/man1/
	ln -s ckbcomp.1 $(mandir)/man1/ckbcomp-mini.1

.PHONY: install-linux
install-linux: install-common install-common-linux install-ckbcomp

.PHONY: install-freebsd
install-freebsd: install-common install-common-freebsd install-ckbcomp

.PHONY : install-mini-linux
install-mini-linux: install-common install-common-linux install-ckbcomp-mini

.PHONY : install-mini-freebsd
install-mini-freebsd: install-common install-common-freebsd install-ckbcomp-mini

common-uninstall: | build-linux build-mini-linux build-freebsd build-mini-freebsd
	-for font in Fonts/*.psf.gz; do \
		rm $(prefix)/share/consolefonts/$${font##*/}; \
	done
	-for acm in acm/*.acm.gz acm/*.acm; do \
		rm $(prefix)/share/consoletrans/$${acm##*/}; \
	done
	-for font in Fonts/*.fnt; do \
		rm $(prefix)/share/syscons/fonts/$${font##*/}; \
	done
	-for scm in Fonts/*.scm; do \
		rm $(prefix)/share/syscons/scrnmaps/$${scm##*/}; \
	done
	-rm -r $(prefix)/share/console-setup/
	-rm $(prefix)/share/man/man1/ckbcomp.1
	-rm $(prefix)/share/man/man1/setupcon.1
	-rm $(prefix)/share/man/man5/keyboard.5
	-rm $(prefix)/share/man/man5/console-setup.5
	-rm -r $(etcdir)/console-setup/
	-rm $(etcdir)/default/keyboard
	-rm $(etcdir)/default/console-setup
	-rm $(prefix)/bin/ckbcomp
	-rm $(bootprefix)/bin/setupcon

.PHONY: uninstall-linux
uninstall-linux: build-linux common-uninstall

.PHONY: uninstall-mini-linux
uninstall-mini-linux: build-mini-linux common-uninstall

.PHONY: uninstall-freebsd
uninstall-freebsd: build-freebsd common-uninstall

.PHONY: uninstall-mini-freebsd
uninstall-mini-freebsd: build-mini-freebsd common-uninstall

%.txt : %
	groff -mandoc -Tascii $< | col -bx >$@

txtmanpages := $./man/bdf2psf.1.txt $./man/console-setup.5.txt		\
	$./man/setupcon.1.txt $./man/ckbcomp.1.txt $./man/keyboard.5.txt

clean .PHONY : $~clean
$~clean:
	-rm -f $(maindir)/acm/*.acm.gz
	-rm -f $(maindir)/*~

maintainer-clean .PHONY : $~maintainer-clean
$~maintainer-clean: $~clean
	-rm -f $(txtmanpages)
	$(MAKE) $(txtmanpages)
