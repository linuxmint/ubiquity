#!/usr/bin/make -f

TESTS=$(wildcard t/*.t)

check:
	failures=0; for t in $(TESTS); do $$t || failures=$$((failures+1)); done; if [ $$failures -gt 0 ]; then echo Test suite failures: $$failures; exit 1; else echo Test suite successful; fi
