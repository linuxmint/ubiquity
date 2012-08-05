all: check-scripts debian/languagelist.data debian/short-tmp/shortlists debian/templates check-scripts check-data check-utf8

LIST     = languagelist

debian/languagelist.data: $(LIST)
	LC_COLLATE=C ./mklanguagelist.data $(LIST) debian/languagelist.data

debian/templates.base: debian/localechooser.templates-in debian/iso_3166.tab
	./mktemplates.continents debian/iso_3166.tab regionmap debian/templates.continents
	cat debian/localechooser.templates-in debian/templates.continents >debian/templates.base-in
	./mktemplates.base debian/templates.base-in debian/templates.base

debian/iso-codes:
	./get-iso-codes

debian/iso_3166.tab:
	isoquery -c | cut -f 1,4 | sort >debian/iso_3166.tab
	[ -s debian/iso_3166.tab ]

debian/templates: $(LIST) debian/templates.base debian/short-tmp/shortlists
	./mktemplates.shortlist
	./mktemplates.warnings $(LIST) debian/templates

debian/short-tmp/shortlists: debian/iso_3166.tab debian/iso-codes
	./mkshort

check-scripts:
	@set -e ; \
	if [ -x /bin/ash ] ; then SH=ash ; else SH=dash; fi ; \
	for s in finish-install.d/05localechooser post-base-installer.d/05localechooser debian/postinst languagemap localechooser ; do \
		echo "Checking syntax of $$s" ; \
		$$SH -n $$s ; \
	done

check-utf8: $(LIST)
	iconv -f utf-8 -t unicode $(LIST) > /dev/null

check-data:
	# Check that the listed locale is supported, to make sure it will work.
	@for locale in `grep -v "^#" $(LIST) | cut -d\; -f6 | grep _` ; do \
		if grep -q "^$$locale " /usr/share/i18n/SUPPORTED ; then \
			: ; \
		else \
			echo "warning: locale $$locale not listed in /usr/share/i18n/SUPPORTED" ; \
		fi ; \
	done

.PHONY: demo
localechooser.templates: debian/templates
	grep -v '#' $^ > $@
demo: localechooser.templates localechooser
	DEBIAN_FRONTEND=dialog DEBCONF_DEBUG=developer /usr/share/debconf/frontend ./localechooser

clean:
	$(RM) localechooser.templates debian/templates debian/templates.continents debian/templates.base-in debian/templates.base debian/templates.tmp debian/languagelist.data debian/iso_3166.tab
	$(RM) -rf debian/short-tmp debian/iso-codes
