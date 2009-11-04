AC_PREREQ(2.52)
AC_INIT([ubiquity], [2.0], [https://launchpad.net/ubuntu/+source/ubiquity/+filebug])
AC_CONFIG_SRCDIR([ubiquity/filteredcommand.py])
AC_CONFIG_AUX_DIR([build])
AC_CONFIG_MACRO_DIR([m4])
AM_INIT_AUTOMAKE([foreign])

AM_MAINTAINER_MODE

AM_GNU_GETTEXT([external])
AM_GNU_GETTEXT_VERSION([0.17])

GETTEXT_PACKAGE=ubiquity
AC_SUBST([GETTEXT_PACKAGE])
IT_PROG_INTLTOOL([0.40.0], [no-xml])

AC_PROG_INSTALL
AC_PROG_MAKE_SET

AC_DEFINE_UNQUOTED(PIXMAPS_DIR, "${datadir}/${PACKAGE}/pixmaps", [pixmaps directory])
pixmapsdir="${datadir}/${PACKAGE}/pixmaps"
AC_SUBST([pixmapsdir])

AC_CONFIG_FILES([
	Makefile
	desktop/Makefile
	pixmaps/Makefile
	po/Makefile.in
	])
AC_OUTPUT
