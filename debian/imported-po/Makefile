all: update

templates.pot: ../ubiquity.templates-imported
	debconf-updatepo --skip-merge --podir=.
	./add-contexts templates.pot

update: templates.pot
	@if [ -z "$(GTK_PO)" ]; then \
		echo "Set GTK_PO to the location of a current GTK+ po/ directory." >&2; \
		exit 1; \
	fi
	@if [ -z "$(PANEL_PO)" ]; then \
		echo "Set PANEL_PO to the location of a current gnome-panel po/ directory." >&2; \
		exit 1; \
	fi
	rm -f *.po
	for p in $(GTK_PO)/*.po; do \
		[ -f "$$p" ] || continue; \
		b="$$(basename "$$p")"; \
		[ -f "../po/$$b" ] || continue; \
		msgmerge -q "$$p" -C "$$PANEL_PO/$$b" templates.pot | \
		msgattrib --translated --no-fuzzy --no-obsolete -o "$$b" -; \
	done

stats:
	for p in *.po; do \
		printf '%s: ' "$$(basename "$$p" .po)"; \
		msgfmt --statistics -o /dev/null "$$p"; \
	done
