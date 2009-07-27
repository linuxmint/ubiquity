#! /bin/sh -e
if ! type intltool-update >/dev/null 2>&1; then
	echo "Install intltool and try again." >&2
	exit 1
fi
AUTOMAKE=automake-1.10 ACLOCAL=aclocal-1.10 autoreconf -I m4 -fi
intltoolize --copy --force --automake
