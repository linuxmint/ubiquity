## Process this file with automake to produce Makefile.in

INCLUDES = $(PYTHON_INCLUDES)

pkgpyexec_LTLIBRARIES = _osextras.la
_osextras_la_CFLAGS = -fPIC $(PYTHON_INCLUDES)
_osextras_la_LDFLAGS = -module -avoid-version \
		       -export-symbols-regex init_osextras
_osextras_la_SOURCES = osextrasmodule.c
