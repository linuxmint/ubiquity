## Process this file with automake to produce Makefile.in

SUBDIRS = cut-and-paste

INCLUDES = $(PYTHON_INCLUDES) $(PYGTK_CFLAGS)

defsdir = $(datadir)/pygtk/2.0/defs
defs_DATA = e-map.defs

EXTRA_DIST = $(defs_DATA)

pkgpyexec_LTLIBRARIES = emap.la
emap_la_CFLAGS = -fPIC $(PYTHON_INCLUDES) $(PYGTK_CFLAGS) \
		 -I$(srcdir)/cut-and-paste/e-map
emap_la_LDFLAGS = $(PYGTK_LIBS) \
		  -module -avoid-version -export-symbols-regex initemap
emap_la_LIBADD = -Lcut-and-paste/e-map -lemap
emap_la_SOURCES = emapmodule.c
nodist_emap_la_SOURCES = e-map.c
CLEANFILES = e-map.c
EXTRA_DIST += e-map.override

%.c: %.defs %.override
	(cd $(srcdir) \
	 && $(PYGOBJECT_CODEGEN) --prefix e_map \
	    --register $(PYGTK_DEFSDIR)/gdk-types.defs \
	    --register $(PYGTK_DEFSDIR)/gtk-types.defs \
	    --override $*.override \
	    $<) > gen-$@ \
	&& cp gen-$@ $@ \
	&& rm -f gen-$@
