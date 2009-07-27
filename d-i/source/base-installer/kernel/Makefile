ARCHES = alpha amd64 arm armeb armel hppa i386 ia64 lpia m68k mips mipsel powerpc ppc64 s390 sparc

test:
	@STATUS=0; \
	cd tests && \
	for x in $(ARCHES); do ./runtests "$$x" || STATUS=1; done; \
	exit "$$STATUS"
