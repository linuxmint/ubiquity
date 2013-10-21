icon16dir = $(datadir)/icons/hicolor/16x16/apps
icon16_DATA = 16x16/apps/ubiquity.svg 16x16/apps/ubiquity-kde.png
icon22dir = $(datadir)/icons/hicolor/22x22/apps
icon22_DATA = 22x22/apps/ubiquity.svg 22x22/apps/ubiquity-kde.png
icon24dir = $(datadir)/icons/hicolor/24x24/apps
icon24_DATA = 24x24/apps/ubiquity.svg
icon32dir = $(datadir)/icons/hicolor/32x32/apps
icon32_DATA = 32x32/apps/ubiquity.svg 32x32/apps/ubiquity-kde.png
icon48dir = $(datadir)/icons/hicolor/48x48/apps
icon48_DATA = 48x48/apps/ubiquity.svg 48x48/apps/ubiquity-kde.png
icon64dir = $(datadir)/icons/hicolor/64x64/apps
icon64_DATA = 64x64/apps/ubiquity.svg 64x64/apps/ubiquity-kde.png
icon128dir = $(datadir)/icons/hicolor/128x128/apps
icon128_DATA = 128x128/apps/ubiquity-kde.png
icon_files = \
	$(icon16_DATA) \
	$(icon22_DATA) \
	$(icon24_DATA) \
	$(icon32_DATA) \
	$(icon48_DATA) \
	$(icon128_DATA)

gtk_update_icon_cache = gtk-update-icon-cache -f -t $(datadir)/icons/hicolor

install-data-hook: update-icon-cache
uninstall-hook: update-icon-cache
update-icon-cache:
	@-if test -z "$(DESTDIR)"; then \
		echo "Updating Gtk icon cache."; \
		$(gtk_update_icon_cache); \
	else \
		echo "*** Icon cache not updated.  After (un)install, run this:"; \
		echo "***   $(gtk_update_icon_cache)"; \
	fi
