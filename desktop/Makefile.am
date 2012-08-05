@INTLTOOL_DESKTOP_RULE@

desktopdir = $(datadir)/applications
desktop_DATA = $(desktop_in_files:.desktop.in=.desktop)
desktop_in_files = \
	oem-config-prepare-gtk.desktop.in \
	oem-config-prepare-kde.desktop.in \
	ubiquity-gtkui.desktop.in \
	ubiquity-kdeui.desktop.in

EXTRA_DIST = $(desktop_in_files)

CLEANFILES = $(desktop_DATA)
