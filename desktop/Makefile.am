@INTLTOOL_DESKTOP_RULE@

desktopdir = $(datadir)/applications
desktop_DATA = $(desktop_in_files:.desktop.in=.desktop)
desktop_in_files = \
	ubiquity-gtkui.desktop.in \
	ubiquity-kdeui.desktop.in \
	ubiquity-mythbuntu.desktop.in

EXTRA_DIST = $(desktop_in_files)

CLEANFILES = $(desktop_DATA)
