CC		= gcc
TARGETS		?= netcfg-static netcfg

LDOPTS		= -ldebconfclient -ldebian-installer -liw
CFLAGS		= -W -Wall -DNDEBUG 
COMMON_OBJS	= netcfg-common.o wireless.o

ifeq ($(NO_WIRELESS),)
CFLAGS		+= -DWIRELESS
endif

ifneq (,$(findstring noopt,$(DEB_BUILD_OPTIONS)))
CFLAGS += -O0 -g3
else
CFLAGS += -Os -fomit-frame-pointer
endif

all: $(TARGETS)

netcfg-static: netcfg-static.o static.o
netcfg: netcfg.o dhcp.o static.o ethtool-lite.o

$(TARGETS): $(COMMON_OBJS)
	$(CC) -o $@ $^ $(LDOPTS)

%.o: %.c
	$(CC) -c $(CFLAGS) $(DEFS) $(INCS) -o $@ $<

clean:
	rm -f $(TARGETS) *.o

.PHONY: all clean

# vim:ts=8:noet
