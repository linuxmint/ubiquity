## Process this file with automake to produce Makefile.in

SUBDIRS = desktop pixmaps po
if PYGOBJECT_CODEGEN
  SUBDIRS += src
endif

ACLOCAL_AMFLAGS = -I m4

EXTRA_DIST = m4/ChangeLog

DISTCLEANFILES = intltool-extract intltool-merge intltool-update
