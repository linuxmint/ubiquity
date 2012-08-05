all: debian/tzmap debian/common.templates

debian/iso_3166.tab:
	isoquery -c | cut -f 1,4 | sort > debian/iso_3166.tab

debian/tzmap: gen-templates debian/common.templates.in /usr/share/zoneinfo/zone.tab debian/iso_3166.tab
	./gen-templates < debian/common.templates.in > debian/common.templates

debian/common.templates: gen-templates debian/common.templates.in /usr/share/zoneinfo/zone.tab debian/iso_3166.tab
	./gen-templates < debian/common.templates.in > debian/common.templates

clean:
	rm -f debian/tzmap debian/iso_3166.tab
