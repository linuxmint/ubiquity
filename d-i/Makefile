unexport DH_OPTIONS

APTDIR := apt
LISTDIR := lists
SOURCEDIR := source

ifndef DEB_HOST_ARCH
DEB_HOST_ARCH := $(shell dpkg-architecture -qDEB_HOST_ARCH)
endif

PACKAGES := $(shell cat $(LISTDIR)/any)
ifneq (,$(wildcard $(LISTDIR)/$(DEB_HOST_ARCH)))
PACKAGES += $(shell cat $(LISTDIR)/$(DEB_HOST_ARCH))
endif
# We don't need to build console-setup.
PACKAGES := $(filter-out console-setup,$(PACKAGES))

update:
	@perl -MDpkg::Deps -e1 >/dev/null 2>&1 || { \
		echo "You need dpkg-dev >= 1.14.8 installed to do this." >&2; \
		exit 1; \
	}
	./get-sources update
	./get-sources $(shell sort -u $(LISTDIR)/*)
	./update-control
ifdef UPDATE_LOCAL
	mv manifest.old manifest
else
	./update-changelog
endif

check:
	./check-manifest

maintainer-clean:
	rm -rf $(SOURCEDIR)

build:
	set -e; for package in $(PACKAGES); do \
		if [ -d "$(SOURCEDIR)/$$package" ]; then \
			(cd "$(SOURCEDIR)/$$package" && \
			 debian/rules build) || exit 1; \
		fi; \
	done

clean:
	rm -rf $(APTDIR)
	for dir in $(SOURCEDIR)/*; do \
		if [ "$${dir##*/}" != console-setup ] && [ -d "$$dir" ]; then \
			(cd "$$dir" && debian/rules clean) || exit 1; \
		fi; \
	done
	$(MAKE) -C $(SOURCEDIR)/console-setup/Keyboard clean
	rm -f $(SOURCEDIR)/*.deb $(SOURCEDIR)/*.udeb
	rm -f manifest.old
	rm -rf udeb-control templates

install:
	set -e; for package in $(PACKAGES); do \
		if [ -d "$(SOURCEDIR)/$$package" ]; then \
			(export NO_PKG_MANGLE=1; \
			 cd "$(SOURCEDIR)/$$package" && \
			 debian/rules binary && \
			 rm -rf debian/*/DEBIAN) || exit 1; \
		fi; \
	done
	rm -rf udeb-control templates
	mkdir -p udeb-control
	set -e; for udeb in $(SOURCEDIR)/*.udeb; do \
		if [ -f "$$udeb" ]; then \
			name="$$(basename "$$udeb" .udeb)"; \
			dpkg-deb -e "$$udeb" "udeb-control/$$name"; \
			if [ -f "udeb-control/$$name/templates" ]; then \
				sed -n '/./,$$p' "udeb-control/$$name/templates" | \
					egrep -iv '^(indices.*|help):' >> templates; \
				if [ "$$(tail -n1 templates)" ]; then \
					echo >> templates; \
				fi; \
			fi; \
		fi; \
	done

.PHONY: update build clean install
