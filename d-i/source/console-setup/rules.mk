ifndef RULES_MK
RULES_MK:=a conditional to make it included only once
###########################################################################

SHELL = /bin/sh

build : build-linux build-freebsd build-mini-linux build-mini-freebsd

.PHONY: build build-linux build-freebsd build-common
build-common:
build-linux build-freebsd: build-common
.PHONY: build-mini-linux build-mini-freebsd
build-mini-linux: build-linux
build-mini-freebsd: build-freebsd
.PHONY: clean maintainer-clean

%.gz : %
	gzip -9n <$< >$@

###########################################################################
endif
