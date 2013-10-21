#! /bin/sh -e
if ! type intltool-update >/dev/null 2>&1; then
	echo "Install intltool and try again." >&2
	exit 1
fi
AUTOMAKE=automake-1.13 ACLOCAL=aclocal-1.13 autoreconf -I m4 -fi
intltoolize --copy --force --automake
# We want to keep po/ubiquity.pot in the source package.
sed -i '/rm .*\$(GETTEXT_PACKAGE)\.pot/s/ \$(GETTEXT_PACKAGE)\.pot//' \
	po/Makefile.in.in
