defsdir = $(datadir)/pygobject/2.0/defs
defs_DATA = cheese.defs

ACLOCAL_AMFLAGS = -I m4


pkgpyexec_LTLIBRARIES = cheese.la
cheese_la_LDFLAGS = -module -avoid-version -export-symbols-regex initcheese
cheese_la_LIBADD = $(CHEESE_LIBS)
cheese_la_SOURCES = cheesemodule.c cheese.c

CLEANFILES = cheese.c
EXTRA_DIST = cheese.override $(defs_DATA) test.py
INCLUDES = $(CHEESE_CFLAGS) \
	$(PYTHON_INCLUDES)

cheese.c: cheese.defs cheese.override
.defs.c:
	(cd $(srcdir)\
	 && $(PYGOBJECT_CODEGEN) \
	 	--py_ssize_t-clean \
		--override $*.override \
		--register cheese-types.defs \
		--register $(PYGTK_DEFS_DIR)/gtk-base-types.defs \
		--register $(PYGTK_DEFS_DIR)/gdk-base-types.defs \
		--prefix py$* $*.defs) > gen-$*.c \
	&& cp gen-$*.c $*.c \
	&& rm -f gen-$*.c

update-defs:
	$(PYGOBJECT_H2DEF) \
	$(top_builddir)/libcheese/cheese-widget.h \
	$(top_builddir)/libcheese/cheese-avatar-chooser.h \
	$(top_builddir)/libcheese/cheese-camera-device-monitor.h > cheese-new.defs

.PHONY: update-defs
