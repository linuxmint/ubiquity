AC_INIT([partman-base],
	m4_esyscmd_s([head -n1 debian/changelog | sed -n 's/.*(\(.*\)).*/\1/p']))
AM_INIT_AUTOMAKE([-Wall foreign])

AC_USE_SYSTEM_EXTENSIONS
AC_PROG_CC

PKG_CHECK_MODULES([libparted], [libparted])

AC_ARG_VAR([libparted_fs_resize_LIBS], [linker flags for libparted-fs-resize])
AC_MSG_CHECKING([for libparted >= 3.1])
PKG_CHECK_EXISTS([libparted >= 3.1],
		 [libparted_fs_resize_LIBS="-lparted-fs-resize"
		  AC_MSG_RESULT([yes])],
		 [AC_MSG_RESULT([no])])

AC_CONFIG_HEADER([config.h])
AC_CONFIG_FILES([Makefile])
AC_OUTPUT
