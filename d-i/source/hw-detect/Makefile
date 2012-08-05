DEB_HOST_ARCH ?= $(shell dpkg-architecture -qDEB_HOST_ARCH)
DEB_HOST_ARCH_OS ?= $(shell dpkg-architecture -qDEB_HOST_ARCH_OS 2>/dev/null)
DEB_HOST_GNU_TYPE  ?= $(shell dpkg-architecture -qDEB_HOST_GNU_TYPE)
DEB_BUILD_GNU_TYPE ?= $(shell dpkg-architecture -qDEB_BUILD_GNU_TYPE)

# Take account of old dpkg-architecture output.
ifeq ($(DEB_HOST_ARCH_OS),)
  DEB_HOST_ARCH_OS := $(subst -gnu,,$(shell dpkg-architecture -qDEB_HOST_GNU_SYSTEM))
  ifeq ($(DEB_HOST_ARCH_OS),gnu)
    DEB_HOST_ARCH_OS := hurd
  endif
endif

CC = gcc
ifneq ($(DEB_BUILD_GNU_TYPE), $(DEB_HOST_GNU_TYPE))
export CC=$(DEB_HOST_GNU_TYPE)-gcc
endif
CFLAGS = -W -Wall -Os -g
CFLAGS_ARCH = -DCPU_TEXT='"$(DEB_HOST_ARCH)"'

bindir=$(DESTDIR)/bin/
hpdir=$(DESTDIR)/etc/hotplug.d
netdir=$(DESTDIR)/etc/network
udevdir=$(DESTDIR)/etc/udev/rules.d
didir=$(DESTDIR)/lib/debian-installer.d
fidir=$(DESTDIR)/usr/lib/finish-install.d
sharedir=$(DESTDIR)/usr/share/hw-detect/
postbaseinstallerdir=$(DESTDIR)/usr/lib/post-base-installer.d/
prepkgseldir=$(DESTDIR)/usr/lib/pre-pkgsel.d/
usrbindir=$(DESTDIR)/usr/bin
man1dir=$(DESTDIR)/usr/share/man/man1

INSTALL=install
INSTALL_DATA = ${INSTALL} -m 644

all: archdetect devnames-static.gz

test:
	set -e; for sh in *.sh; do sh -n $$sh; done

clean:
	rm -f *~
	rm -f *.o
	rm -f archdetect
	rm -f devnames-static.gz

install: install-hw-detect install-ethdetect install-disk-detect install-driver-injection-disk-detect install-archdetect install-archdetect-deb

install-hw-detect: hw-detect.sh
	$(INSTALL) -d $(bindir)
ifeq ($(DEB_HOST_ARCH_OS),linux)
	$(INSTALL) hw-detect.sh $(bindir)/hw-detect
	$(INSTALL) hotplug-pcmcia.sh $(bindir)/hotplug-pcmcia
	$(INSTALL) sysfs-update-devnames.sh $(bindir)/sysfs-update-devnames
	$(INSTALL) -d $(udevdir)
	$(INSTALL_DATA) net-hotplug.rules $(udevdir)/010_net-hotplug.rules
	$(INSTALL) check-missing-firmware.sh $(bindir)/check-missing-firmware
	$(INSTALL) -d $(postbaseinstallerdir)
	$(INSTALL) hw-detect.post-base-installer.d/* $(postbaseinstallerdir)
	$(INSTALL) -d $(prepkgseldir)
	$(INSTALL) hw-detect.pre-pkgsel.d/* $(prepkgseldir)
	$(INSTALL) -d $(hpdir)/net
	$(INSTALL) net-hotplug.sh $(hpdir)/net/hw-detect.hotplug
	$(INSTALL) -d $(fidir)
	$(INSTALL) hw-detect.finish-install.d/* $(fidir)
ifeq ($(DEB_HOST_ARCH),powerpc)
	$(INSTALL) discover-mac-io.sh $(bindir)/discover-mac-io
	$(INSTALL) discover-ibm.sh $(bindir)/discover-ibm
endif
ifeq ($(DEB_HOST_ARCH),sparc)
	$(INSTALL) discover-sbus.sh $(bindir)/discover-sbus
	$(INSTALL) -d $(sharedir)
	$(INSTALL_DATA) sbus.list $(sharedir)/sbus.list
endif
else
	$(INSTALL) detect-stub.sh $(bindir)/hw-detect
endif

install-ethdetect: ethdetect.sh
	$(INSTALL) -d $(bindir) $(netdir)
	$(INSTALL) ethdetect.sh $(bindir)/ethdetect
	$(INSTALL) -m644 devnames-static.gz $(netdir)/

install-disk-detect: disk-detect.sh
	$(INSTALL) -d $(bindir)
	$(INSTALL) disk-detect.sh $(bindir)/disk-detect

install-driver-injection-disk-detect: driver-injection-disk.sh
	$(INSTALL) -d $(bindir)
	$(INSTALL) driver-injection-disk.sh $(bindir)/driver-injection-disk

install-archdetect: archdetect
	$(INSTALL) -d $(bindir)
	$(INSTALL) archdetect $(bindir)

install-archdetect-deb: archdetect
	$(INSTALL) -d $(usrbindir)
	$(INSTALL) archdetect $(usrbindir)
	$(INSTALL) -d $(man1dir)
	$(INSTALL) archdetect.1 $(man1dir)

archdetect: archdetect.o 
	${CC} ${LDFLAGS} -o $@ $^ -ldebian-installer

archdetect.o: %.o:%.c
	$(CC) $(CFLAGS) $(CFLAGS_ARCH) -c $<

devnames-static.gz: devnames-static.txt
	grep -v '^#' $< | gzip -9c > $@
