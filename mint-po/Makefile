all: buildmo

buildmo:
	@echo "Building the Mint mo files"
	# WARNING: the second sed below will only works correctly with the languages that don't contain "-"
	for file in `ls *.po`; do \
		lang=`echo $$file | sed 's@po/@@' | sed 's/.po//' | sed 's/mintubiquity-//'`; \
		install -d usr/share/locale/$$lang/LC_MESSAGES/; \
		msgfmt -o usr/share/locale/$$lang/LC_MESSAGES/mintubiquity.mo $$file; \
	done \

install: buildmo

clean:
	rm -rf usr/share/locale/*/LC_MESSAGES/mintubiquity.mo
