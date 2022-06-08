kbddir ?= $(shell pwd)
include $(kbddir)/../rules.mk

# The following two shortcuts will be redefined, so they can not be
# used in recipes and target specific variables.
. := $(kbddir)
~ := kbd

gzipped-ekmaps := $./amiga.ekmap.gz $./ataritt.ekmap.gz		\
		$./pc105.ekmap.gz	\
		$./sun4.ekmap.gz $./sun5.ekmap.gz

gzipped-ekbds := $./pc105.ekbd.gz

xkbdir ?= /usr/share/X11/xkb

%.tree : %.ekmap.gz $./keymaptree.use
	(cd $(kbddir) && set -x && \
		./keymaptree -output $@ -useonly "$$(cat $./Keyboard/keymaptree.use | grep -v '^#' | xargs | sed 's/ /,/g')" -names ./KeyboardNames.pl $(notdir $(@:%.tree=%)))

$./%.ekmap : model = $(notdir $(@:%.ekmap=%))
$./%.ekmap :
	(cd $(kbddir) && \
		./kbdcompiler $(model) ./KeyboardNames.pl $(xkbdir)) >$@

$./%.ekbd : model = $(notdir $(@:%.ekbd=%))
$./%.ekbd :
	(cd $(kbddir) && \
		./kbdcompiler freebsd-$(model) ./KeyboardNames.pl $(xkbdir)) >$@

$./charmap_functions.sh : $(acmfiles)
	$(kbddir)/make_charmap_functions $(kbddir)/../acm $(charmaps) >$@

acmfiles := $(wildcard $./../acm/*.acm)

charmaps := $(basename $(notdir $(acmfiles)))

compose_files := $(addprefix $./compose.,$(addsuffix .inc, $(charmaps)))
dkey_files := $(addprefix $./dkey.,$(addsuffix .inc, $(charmaps)))

$(compose_files): charmap = $(patsubst compose.%.inc,%, $(notdir $@))
$(dkey_files): charmap = $(patsubst dkey.%.inc,%, $(notdir $@))
$(compose_files) $(dkey_files): acmfile = $(kbddir)/../acm/$(charmap).acm

VISCII-XCOMPOSE := $./locale/vi_VN.viscii/Compose
ISO-8859-1-XCOMPOSE := $./locale/iso8859-1/Compose
ISO-8859-2-XCOMPOSE := $./locale/iso8859-2/Compose
ISO-8859-3-XCOMPOSE := $./locale/iso8859-3/Compose
ISO-8859-4-XCOMPOSE := $./locale/iso8859-4/Compose
ISO-8859-7-XCOMPOSE := $./locale/iso8859-7/Compose
ISO-8859-9-XCOMPOSE := $./locale/iso8859-9/Compose
ISO-8859-13-XCOMPOSE := $./locale/iso8859-13/Compose
ISO-8859-14-XCOMPOSE := $./locale/iso8859-14/Compose
ISO-8859-15-XCOMPOSE := $./locale/iso8859-15/Compose

$(compose_files) :
	echo '# Compose sequences for $(charmap)' >$@
	$(if $($(charmap)-XCOMPOSE), \
		$(kbddir)/compose_translator --acm $(acmfile) \
			$($(charmap)-XCOMPOSE) >>$@)

$(dkey_files) : $(kbddir)/dkey_sequences
	$(kbddir)/dkey_bsd $(acmfile) $(kbddir)/dkey_sequences >$@

build-common .PHONY : compose-files dkey-files
compose-files : $(compose_files)
dkey-files : $(dkey_files)
build-mini-linux : gzipped-ekmaps $./charmap_functions.sh $./pc105.tree
.PHONY : gzipped-ekmaps
gzipped-ekmaps : $(gzipped-ekmaps)
build-mini-freebsd : gzipped-ekbds $./charmap_functions.sh
.PHONY : gzipped-ekbds
gzipped-ekbds : $(gzipped-ekbds)

kbdcleanfiles := $(wildcard $./*~ $./*.ekmap $./*.ekbd)			\
		$./linux-keymaps $./freebsd-keymaps $./keymaps		\
		$./ckbcomp.log $./keymaps.dir $./names.list		\
		$./charmap_functions.sh $./compose $(compose_files)	\
		$(dkey_files) $(gzipped-ekmaps) $(gzipped-ekbds)

clean .PHONY : $~clean
$~clean:
	-rm -rf $(kbdcleanfiles)
	-rm -f *.tree

maintainer-clean .PHONY : $~maintainer-clean
$~maintainer-clean: $~clean
	cd $(kbddir) && ./xmlreader $(xkbdir)/rules/xorg.xml >KeyboardNames.pl

KeyboardNames.pl $./KeyboardNames.pl:
	$(kbddir)/xmlreader $(xkbdir)/rules/xorg.xml >$@
