SHELL = /bin/sh

xkbdir ?= ./ckb

build : compose_files dkey_files KeyboardNames.pl

models = amiga ataritt macintosh_old pc105 sun4 sun5

gzipped_ekmaps =  $(addsuffix .ekmap.gz, $(models))

gzipped_ekbds = pc105.ekbd.gz

build-mini-linux : $(gzipped_ekmaps) charmap_functions.sh pc105.tree

build-mini-freebsd : $(gzipped_ekbds) charmap_functions.sh

%.gz : %
	gzip -9 <$< >$@

%.ekmap : 
	./kbdcompiler $(@:%.ekmap=%) KeyboardNames.pl $(xkbdir) >$@

%.tree : %.ekmap.gz keymaptree.use
	./keymaptree -output $@ -useonly "$$(< keymaptree.use grep -v '^#' | xargs | sed 's/ /,/g')" -names KeyboardNames.pl $(@:%.tree=%)

%.ekbd : 
	./kbdcompiler freebsd-$(@:%.ekbd=%) KeyboardNames.pl $(xkbdir) >$@

charmap_functions.sh : $(acmfiles)
	./make_charmap_functions ../acm $(charmaps) >$@

acmfiles = $(wildcard ../acm/*.acm)

charmaps = $(basename $(notdir $(acmfiles)))

compose_files = $(addprefix compose.,$(addsuffix .inc, $(charmaps)))
dkey_files = $(addprefix dkey.,$(addsuffix .inc, $(charmaps)))

$(compose_files): charmap = $(patsubst compose.%.inc,%, $@)
$(dkey_files): charmap = $(patsubst dkey.%.inc,%, $@)

VISCII-XCOMPOSE = locale/vi_VN.viscii/Compose
ISO-8859-1-XCOMPOSE = locale/iso8859-1/Compose
ISO-8859-2-XCOMPOSE = locale/iso8859-2/Compose
ISO-8859-3-XCOMPOSE = locale/iso8859-3/Compose
ISO-8859-4-XCOMPOSE = locale/iso8859-4/Compose
ISO-8859-7-XCOMPOSE = locale/iso8859-7/Compose
ISO-8859-9-XCOMPOSE = locale/iso8859-9/Compose
ISO-8859-13-XCOMPOSE = locale/iso8859-13/Compose
ISO-8859-14-XCOMPOSE = locale/iso8859-14/Compose
ISO-8859-15-XCOMPOSE = locale/iso8859-15/Compose


$(compose_files) :
	echo '# Compose sequences for $(charmap)' >$@
	$(if $($(charmap)-XCOMPOSE), \
		./compose_translator --acm ../acm/$(charmap).acm \
				     $($(charmap)-XCOMPOSE) >>$@)

$(dkey_files) : dkey_sequences
	./dkey_bsd ../acm/$(charmap).acm dkey_sequences >$@

compose_files : $(compose_files)
dkey_files : $(dkey_files)


.PHONY: clean
clean:
	-rm -f *~
	-rm -rf compose $(compose_files) $(dkey_files)
	-rm -rf linux-keymaps freebsd-keymaps keymaps tree-keymaps
	-rm -f keymaps.dir names.list
	-rm -f charmap_functions.sh
	-rm -f $(gzipped_ekmaps) $(gzipped_ekbds)
	-rm -f *.tree

.PHONY: maintainer-clean
maintainer-clean: clean
	./xmlreader >KeyboardNames.pl

KeyboardNames.pl:
	./xmlreader $(xkbdir)/rules/xorg.xml >KeyboardNames.pl
