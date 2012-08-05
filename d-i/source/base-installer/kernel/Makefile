ARCHES = alpha amd64 armeb armel armhf hppa i386 ia64 m68k mips mipsel powerpc s390 sh4 sparc kfreebsd-amd64 kfreebsd-i386

test:
	@STATUS=0; \
	cd tests && \
	for x in $(ARCHES); do ./runtests "$$x" || STATUS=1; done; \
	exit "$$STATUS"
