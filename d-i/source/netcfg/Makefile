NETCFG_VERSION := $(shell dpkg-parsechangelog | grep ^Version: |sed 's/Version: //')
NETCFG_BUILD_DATE := $(shell date '+%Y%m%d-%H%M')

CC		= gcc
TARGETS		?= netcfg-static netcfg

LDOPTS		= -ldebconfclient -ldebian-installer
CFLAGS		= -W -Wall -Werror -DNDEBUG -DNETCFG_VERSION="\"$(NETCFG_VERSION)\"" -DNETCFG_BUILD_DATE="\"$(NETCFG_BUILD_DATE)\"" -I.
COMMON_OBJS	= netcfg-common.o wireless.o write_interface.o ipv6.o

WIRELESS	= 1
ifneq ($(DEB_HOST_ARCH_OS),linux)
WIRELESS	= 0
endif
ifeq ($(DEB_HOST_ARCH),s390)
WIRELESS	= 0
endif

ifneq ($(WIRELESS),0)
LDOPTS		+= -liw
CFLAGS		+= -DWIRELESS
endif

ifneq (,$(findstring noopt,$(DEB_BUILD_OPTIONS)))
CFLAGS += -O0 -g3
else
CFLAGS += -Os -fomit-frame-pointer
endif

all: $(TARGETS)

netcfg-static: netcfg-static.o static.o ethtool-lite.o
netcfg: netcfg.o dhcp.o static.o ethtool-lite.o wpa.o wpa_ctrl.o rdnssd.o autoconfig.o

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
