AC_PREREQ(2.52)
AC_INIT([ubiquity], [2.8], [https://launchpad.net/ubuntu/+source/ubiquity/+filebug])
AC_CONFIG_SRCDIR([src/panel/panel.c])
AC_CONFIG_AUX_DIR([build])
AC_CONFIG_MACRO_DIR([m4])
AM_INIT_AUTOMAKE([foreign])

AM_CONFIG_HEADER([config.h])

AM_MAINTAINER_MODE

AM_PROG_LIBTOOL

AM_GNU_GETTEXT([external])
AM_GNU_GETTEXT_VERSION([0.17])

GETTEXT_PACKAGE=ubiquity
AC_SUBST([GETTEXT_PACKAGE])
IT_PROG_INTLTOOL([0.40.0], [no-xml])

AC_PROG_CC
AC_HEADER_STDC
AC_PROG_INSTALL
AC_PROG_MAKE_SET

GTK3_REQUIRED=3.1.4
GIO_REQUIRED=2.5.11
AM_PATH_PYTHON([2.5])

if test "x$UBIQUITY_NO_GTK" = x; then
  PKG_CHECK_MODULES(WEBCAM, [gtk+-3.0 >= $GTK3_REQUIRED
			  gio-2.0 >= $GIO_REQUIRED
			  gstreamer-0.10
			  gstreamer-interfaces-0.10
			  gudev-1.0])
  AC_SUBST(WEBCAM_CFLAGS)
  AC_SUBST(WEBCAM_LIBS)
  PKG_CHECK_MODULES(PANEL, [glib-2.0
			  gtk+-3.0 >= $GTK3_REQUIRED
			  indicator3-0.4
			  x11])
  AC_SUBST(PANEL_CFLAGS)
  AC_SUBST(PANEL_LIBS)
  PKG_CHECK_MODULES(WALLPAPER, [glib-2.0
			  gtk+-3.0 >= $GTK3_REQUIRED
			  x11])
  AC_SUBST(WALLPAPER_CFLAGS)
  AC_SUBST(WALLPAPER_LIBS)
  GOBJECT_INTROSPECTION_CHECK([0.6.7])
  AC_CONFIG_FILES(
	src/Makefile
	src/wallpaper/Makefile
	src/webcam/Makefile
	src/panel/Makefile
	)
else
  AC_SUBST(WEBCAM_CFLAGS, [""])
  AC_SUBST(WEBCAM_LIBS, [""])
  AC_SUBST(PANEL_CFLAGS, [""])
  AC_SUBST(PANEL_LIBS, [""])
  AC_SUBST(WALLPAPER_CFLAGS, [""])
  AC_SUBST(WALLPAPER_LIBS, [""])
fi


AM_PATH_PYTHON([2.6])
UBIQUITY_CHECK_PYTHON_HEADERS(,[AC_MSG_ERROR([could not find Python headers])])

AC_CHECK_FUNCS([setresuid setresgid getresuid getresgid])

AC_DEFINE_UNQUOTED(PIXMAPS_DIR, "${datadir}/${PACKAGE}/pixmaps", [pixmaps directory])
pixmapsdir="${datadir}/${PACKAGE}/pixmaps"
AC_SUBST([pixmapsdir])

#*******************************************************************************
# Check for python
#*******************************************************************************
AM_PATH_PYTHON()
AM_CHECK_PYTHON_HEADERS(,AC_MSG_ERROR([install python-devel]))

#*******************************************************************************
# Check for PYGOBJECT
#*******************************************************************************

AC_MSG_CHECKING(for pygobject defs)
PYGOBJECT_DEFSDIR=`$PKG_CONFIG --variable=defsdir pygobject-2.0`
AC_SUBST(PYGOBJECT_DEFSDIR)
AC_MSG_RESULT($PYGOBJECT_DEFSDIR)

AC_MSG_CHECKING(for pygobject codegen)
PYGOBJECT_CODEGEN="$PYTHON `$PKG_CONFIG --variable=codegendir pygobject-2.0`/codegen.py"
AC_SUBST(PYGOBJECT_CODEGEN)
AC_MSG_RESULT($PYGOBJECT_CODEGEN)

AC_MSG_CHECKING(for pygobject h2def)
PYGOBJECT_H2DEF="$PYTHON `$PKG_CONFIG --variable=codegendir pygobject-2.0`/h2def.py"
AC_SUBST(PYGOBJECT_H2DEF)
AC_MSG_RESULT($PYGOBJECT_H2DEF)


AC_CONFIG_FILES([
	Makefile
	desktop/Makefile
	pixmaps/Makefile
	po/Makefile.in
	ubiquity/Makefile
	])
AC_OUTPUT

