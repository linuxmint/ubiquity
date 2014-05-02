AC_PREREQ(2.52)
AC_INIT([ubiquity], [2.18], [https://launchpad.net/ubuntu/+source/ubiquity/+filebug])
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
AC_PROG_INSTALL
AC_PROG_MAKE_SET

GTK3_REQUIRED=3.1.4
GIO_REQUIRED=2.5.11
INDICATOR_REQUIRED=12.10.2
IDO_REQUIRED=13.10.1

if test "x$UBIQUITY_NO_GTK" = x; then
  PKG_CHECK_MODULES(PANEL, [glib-2.0
			  gtk+-3.0 >= $GTK3_REQUIRED
			  indicator3-0.4 >= $INDICATOR_REQUIRED
			  libido3-0.1 >= $IDO_REQUIRED
			  x11])
  AC_SUBST(PANEL_CFLAGS)
  AC_SUBST(PANEL_LIBS)
  PKG_CHECK_MODULES(WALLPAPER, [glib-2.0
			  gtk+-3.0 >= $GTK3_REQUIRED
			  x11])
  AC_SUBST(WALLPAPER_CFLAGS)
  AC_SUBST(WALLPAPER_LIBS)
  PKG_CHECK_MODULES(MOCK_RESOLVER, [glib-2.0
			  gio-2.0])
  AC_SUBST(MOCK_RESOLVER_CFLAGS)
  AC_SUBST(MOCK_RESOLVER_LIBS)
  GOBJECT_INTROSPECTION_CHECK([0.6.7])
  AC_CONFIG_FILES(
	src/Makefile
	src/wallpaper/Makefile
	src/panel/Makefile
	src/mockresolver/Makefile
	)
else
  AC_SUBST(PANEL_CFLAGS, [""])
  AC_SUBST(PANEL_LIBS, [""])
  AC_SUBST(WALLPAPER_CFLAGS, [""])
  AC_SUBST(WALLPAPER_LIBS, [""])
fi

AC_DEFINE_UNQUOTED(PIXMAPS_DIR, "${datadir}/${PACKAGE}/pixmaps", [pixmaps directory])
pixmapsdir="${datadir}/${PACKAGE}/pixmaps"
AC_SUBST([pixmapsdir])

INDICATOR_DIR=${datadir}/unity/indicators
AC_SUBST(INDICATOR_DIR)

AC_CONFIG_FILES([
	Makefile
	data/Makefile
	data/icons/Makefile
	pixmaps/Makefile
	po/Makefile.in
	])
AC_OUTPUT

