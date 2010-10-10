AC_PREREQ(2.52)
AC_INIT([ubiquity], [2.4], [https://launchpad.net/ubuntu/+source/ubiquity/+filebug])
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

GTK_REQUIRED=2.10.0
AM_PATH_PYTHON([2.5])

if test "x$UBIQUITY_NO_GTK" = x; then
  PKG_CHECK_MODULES(PANEL, [glib-2.0
			  gtk+-2.0 >= $GTK_REQUIRED
			  indicator
			  x11])
  AC_SUBST(PANEL_CFLAGS)
  AC_SUBST(PANEL_LIBS)
  PKG_CHECK_MODULES(CHEESE, [glib-2.0
			     gtk+-2.0 >= $GTK_REQUIRED
			     gobject-2.0
			     pygobject-2.0
			     cheese-gtk])
  AC_SUBST(CHEESE_CFLAGS)
  AC_SUBST(CHEESE_LIBS)
  AM_PATH_GTK_2_0([$GTK_REQUIRED])
  AC_CONFIG_FILES(
	src/Makefile
	src/panel/Makefile
	src/cheese/Makefile
	)
else
  AC_SUBST(BASE_CFLAGS, [""])
  AC_SUBST(BASE_LIBS, [""])
  AC_SUBST(CHEESE_CFLAGS, [""])
  AC_SUBST(CHEESE_LIBS, [""])
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


#*******************************************************************************
# Check for PYGTK
#*******************************************************************************

AC_MSG_CHECKING(for pygtk defs)
PYGTK_DEFS_DIR="`$PKG_CONFIG --variable=defsdir pygtk-2.0`"
AC_SUBST(PYGTK_DEFS_DIR)
AC_MSG_RESULT($PYGTK_DEFS_DIR)



#*******************************************************************************
AC_CONFIG_FILES([
	Makefile
	desktop/Makefile
	pixmaps/Makefile
	po/Makefile.in
	ubiquity/Makefile
	])
AC_OUTPUT

