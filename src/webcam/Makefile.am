CLEANFILES = 

AM_CPPFLAGS = $(WEBCAM_CFLAGS)
AM_LDFLAGS = $(WEBCAM_LIBS)

#pkglib_PROGRAMS = webcam

lib_LTLIBRARIES = libubiwebcam.la

libubiwebcam_la_SOURCES = webcam.h webcam.c
libubiwebcam_la_LDFLAGS = -version-info 0:0:0 -no-undefined \
	-export-symbols-regex "^[^_].*"
libubiwebcam_la_LIBADD = $(WEBCAM_LIBS)
if HAVE_INTROSPECTION
-include $(INTROSPECTION_MAKEFILE)
INTROSPECTION_SCANNER_ARGS = --add-include-path=$(srcdir)
INTROSPECTION_COMPILER_ARGS = --includedir=$(srcdir)

INTROSPECTION_GIRS = UbiquityWebcam-1.0.gir

introspection_sources = $(libubiwebcam_la_SOURCES)

UbiquityWebcam-1.0.gir: libubiwebcam.la
UbiquityWebcam_1_0_gir_INCLUDES = GObject-2.0 Gtk-3.0 Gst-0.10
UbiquityWebcam_1_0_gir_CFLAGS = $(INCLUDES) --identifier-prefix=Ubiquity
UbiquityWebcam_1_0_gir_LIBS = libubiwebcam.la
UbiquityWebcam_1_0_gir_FILES = $(introspection_sources)

girdir = $(datadir)/gir-1.0
gir_DATA = $(INTROSPECTION_GIRS)

typelibdir = $(libdir)/girepository-1.0
typelib_DATA = $(INTROSPECTION_GIRS:.gir=.typelib)

CLEANFILES += $(gir_DATA) $(typelib_DATA)
endif
