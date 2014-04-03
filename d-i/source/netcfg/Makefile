NETCFG_VERSION := $(shell dpkg-parsechangelog | grep ^Version: |sed 's/Version: //')
NETCFG_BUILD_DATE := $(shell date '+%Y%m%d-%H%M')
DEB_HOST_ARCH_OS ?= $(shell dpkg-architecture -qDEB_HOST_ARCH_OS)
DEB_HOST_ARCH ?= $(shell dpkg-architecture -qDEB_HOST_ARCH)

CC		?= gcc
TARGETS		?= netcfg-static netcfg

LDOPTS		= -ldebconfclient -ldebian-installer
CFLAGS		= -W -Wall -Werror -DNDEBUG -DNETCFG_VERSION="\"$(NETCFG_VERSION)\"" -DNETCFG_BUILD_DATE="\"$(NETCFG_BUILD_DATE)\"" -I.
COMMON_OBJS	= netcfg-common.o wireless.o write_interface.o ipv6.o
NETCFG_O   	= netcfg.o dhcp.o static.o ethtool-lite.o wpa.o wpa_ctrl.o rdnssd.o autoconfig.o
NETCFG_STATIC_O	= netcfg-static.o static.o ethtool-lite.o

WIRELESS	= 1
NM		= 1
ifneq ($(DEB_HOST_ARCH_OS),linux)
WIRELESS	= 0
NM		= 0
endif
ifeq ($(DEB_HOST_ARCH),s390)
WIRELESS	= 0
endif
ifeq ($(DEB_HOST_ARCH),s390x)
WIRELESS	= 0
endif
ifeq ($(DEB_HOST_ARCH),sparc)
WIRELESS	= 0
endif

ifneq ($(WIRELESS),0)
LDOPTS		+= -liw
CFLAGS		+= -DWIRELESS
endif
ifneq ($(NM),0)
CFLAGS		+= -DNM
NETCFG_O	+= nm-conf.o
endif

ifneq (,$(findstring noopt,$(DEB_BUILD_OPTIONS)))
CFLAGS += -O0 -g3
else
CFLAGS += -Os -fomit-frame-pointer
endif

all: $(TARGETS)

netcfg-static: $(NETCFG_STATIC_O)
netcfg: $(NETCFG_O)

ethtool-lite: ethtool-lite-test.o
	$(CC) -o $@ $<

ethtool-lite-test.o: ethtool-lite.c
	$(CC) -c $(CFLAGS) -DTEST $(DEFS) $(INCS) -o $@ $<

$(TARGETS): $(COMMON_OBJS)
	$(CC) -o $@ $^ $(LDOPTS)

%.o: %.c
	$(CC) -c $(CFLAGS) $(DEFS) $(INCS) -o $@ $<

clean:
	rm -f $(TARGETS) ethtool-lite *.o test/*.o test/run

include test/tests.mk

.PHONY: all clean

# vim:ts=8:noet
