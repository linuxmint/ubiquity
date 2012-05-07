/* «panel» - Installer session panel
 *
 * Copyright (C) 2010 Canonical Ltd.
 *
 * Authors:
 *
 * - Evan Dandrea <ev@ubuntu.com>
 *
 * This file is part of Ubiquity.
 *
 * Ubiquity is free software; you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free
 * Software Foundation; either version 2 of the License, or at your option)
 * any later version.
 *
 * Ubiquity is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with Ubiquity; if not, write to the Free Software Foundation, Inc., 51
 * Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 */
/* Mostly stolen from gnome-panel and unity. */
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <cairo/cairo.h>
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <libindicator/indicator-object.h>

#define ENTRY_DATA_NAME "indicator-custom-entry-data"


static gchar * indicator_order[] = {
  "indicator-session-devices",
  "indicator-sound",
  "nm-applet",
  "bluetooth-manager",
  "ubiquity",
  "keyboard",
  NULL
};

enum {
	STRUT_LEFT = 0,
	STRUT_RIGHT = 1,
	STRUT_TOP = 2,
	STRUT_BOTTOM = 3,
	STRUT_LEFT_START = 4,
	STRUT_LEFT_END = 5,
	STRUT_RIGHT_START = 6,
	STRUT_RIGHT_END = 7,
	STRUT_TOP_START = 8,
	STRUT_TOP_END = 9,
	STRUT_BOTTOM_START = 10,
	STRUT_BOTTOM_END = 11
};

static Atom net_wm_strut              = 0;
static Atom net_wm_strut_partial      = 0;

void
set_strut (GtkWindow *gtk_window,
                 guint32    left_size,
                 guint32    left_start,
                 guint32    left_end,
                 guint32    top_size,
                 guint32    top_start,
                 guint32    top_end)
{
  Display   *display;
  Window     window;
  GdkWindow *gdk_window;
  gulong     struts [12] = { 0, };

  g_return_if_fail (GTK_IS_WINDOW (gtk_window));

  if (!left_size)
    return;

  gdk_window = gtk_widget_get_window (GTK_WIDGET (gtk_window));
  display = GDK_WINDOW_XDISPLAY (gdk_window);
  window  = GDK_WINDOW_XID (gdk_window);

  if (net_wm_strut == None)
    net_wm_strut = XInternAtom (display, "_NET_WM_STRUT", False);
  if (net_wm_strut_partial == None)
    net_wm_strut_partial = XInternAtom (display, "_NET_WM_STRUT_PARTIAL",False);

  struts [STRUT_LEFT] = left_size;
  struts [STRUT_LEFT_START] = left_start;
  struts [STRUT_LEFT_END] = left_end;

  struts [STRUT_TOP] = top_size;
  struts [STRUT_TOP_START] = top_start;
  struts [STRUT_TOP_END] = top_end;

  gdk_error_trap_push ();
  XChangeProperty (display, window, net_wm_strut,
                   XA_CARDINAL, 32, PropModeReplace,
                   (guchar *) &struts, 4);
  XChangeProperty (display, window, net_wm_strut_partial,
                   XA_CARDINAL, 32, PropModeReplace,
                   (guchar *) &struts, 12);
  gdk_error_trap_pop_ignored ();
}

/* Stolen from indicator-loader.c in unity. */
static void
entry_added (IndicatorObject * io, IndicatorObjectEntry * entry, gpointer user_data)
{
    g_debug("Signal: Entry Added");

    GtkWidget * menuitem = gtk_menu_item_new();
    GtkWidget * hbox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 3);

    if (entry->image != NULL) {
        gtk_box_pack_start(GTK_BOX(hbox), GTK_WIDGET(entry->image), FALSE, FALSE, 0);
    }
    gtk_container_add(GTK_CONTAINER(menuitem), hbox);
    gtk_widget_show(hbox);

    if (entry->menu != NULL) {
        gtk_menu_item_set_submenu(GTK_MENU_ITEM(menuitem), GTK_WIDGET(entry->menu));
    }

    if (entry->name_hint != NULL) {
        int i;
        int found = 0;
        for (i = 0; indicator_order[i] != NULL; i++) {
            if (g_strcmp0(entry->name_hint, indicator_order[i]) == 0) {
                gtk_menu_shell_insert(GTK_MENU_SHELL(user_data), menuitem, i);
                found = 1;
                break;
            }
        }
        if (found == 0) {
            gtk_menu_shell_append(GTK_MENU_SHELL(user_data), menuitem);
        }
    }
    else {
        gtk_menu_shell_append(GTK_MENU_SHELL(user_data), menuitem);
    }

    gtk_widget_show(menuitem);

    g_object_set_data(G_OBJECT(menuitem), ENTRY_DATA_NAME, entry);

    return;
}

static void
entry_removed_cb (GtkWidget * widget, gpointer userdata)
{
    gpointer data = g_object_get_data(G_OBJECT(widget), ENTRY_DATA_NAME);

    if (data != userdata) {
        return;
    }

    gtk_widget_destroy(widget);
    return;
}

static void
entry_removed (IndicatorObject * io, IndicatorObjectEntry * entry, gpointer user_data)
{
    g_debug("Signal: Entry Removed");

    gtk_container_foreach(GTK_CONTAINER(user_data), entry_removed_cb, entry);

    return;
}

static gboolean
load_module (const gchar * name, GtkWidget * menu)
{
    g_debug("Looking at Module: %s", name);
    g_return_val_if_fail(name != NULL, FALSE);

    if (!g_str_has_suffix(name, G_MODULE_SUFFIX)) {
        return FALSE;
    }

    g_debug("Loading Module: %s", name);

    /* Build the object for the module */
    IndicatorObject * io = indicator_object_new_from_file(name);

    /* Connect to its signals */
    g_signal_connect(G_OBJECT(io), INDICATOR_OBJECT_SIGNAL_ENTRY_ADDED,   G_CALLBACK(entry_added),    menu);
    g_signal_connect(G_OBJECT(io), INDICATOR_OBJECT_SIGNAL_ENTRY_REMOVED, G_CALLBACK(entry_removed),  menu);
    /* Work on the entries */
    GList * entries = indicator_object_get_entries(io);
    GList * entry = NULL;

    for (entry = entries; entry != NULL; entry = g_list_next(entry)) {
        IndicatorObjectEntry * entrydata = (IndicatorObjectEntry *)entry->data;
        entry_added(io, entrydata, menu);
    }

    g_list_free(entries);

    return TRUE;
}

/* At some point subclass GtkWindow instead. */
static void
on_realize(GtkWidget *win, gpointer data) {
	guint width;
	GtkAllocation allocation;
	gtk_widget_get_allocation(win, &allocation);
	width = gdk_screen_width();
	gtk_window_set_decorated (GTK_WINDOW (win), FALSE);
	set_strut(GTK_WINDOW(win), width, 0, allocation.height, allocation.height, 0, width);
	// We don't care about showing the panel on all desktops just yet.
	gtk_window_stick (GTK_WINDOW (win));
	gtk_window_set_type_hint(GTK_WINDOW(win), GDK_WINDOW_TYPE_HINT_DOCK);
	gdk_window_set_geometry_hints (gtk_widget_get_window(win), NULL, GDK_HINT_POS);
	gdk_window_move_resize(gtk_widget_get_window(win), 0, 0, width, allocation.height);
	gtk_window_set_has_resize_grip(GTK_WINDOW(win), FALSE);
}

static const char* indicators[] = {
	"/usr/lib/indicators3/7/libsession.so",
	"/usr/lib/indicators3/7/libapplication.so",
	"/usr/lib/indicators3/7/libsoundmenu.so",
	NULL
};

static void
draw_child (GtkWidget *child, gpointer client_data) {
	struct {
		GtkWidget *container;
		cairo_t *cr;
	} *data = client_data;
	
	gtk_container_propagate_draw (GTK_CONTAINER (data->container), child, data->cr);
}

static gint
on_draw(GtkWidget *widget, cairo_t *cr, gpointer userdata) {
	GdkPixbuf *pixbuf;
	pixbuf = gdk_pixbuf_new_from_file("/usr/share/themes/Ambiance/gtk-2.0/apps/img/panel.png", NULL);
	if (!pixbuf) {
		pixbuf = gdk_pixbuf_new_from_file("/usr/share/lxpanel/images/lubuntu-background.png", NULL);
	}
	if (!pixbuf) {
		pixbuf = gdk_pixbuf_new_from_file("/usr/share/ubiquity/pixmaps/panel.png", NULL);
	}
	if (pixbuf) {
		gdk_cairo_set_source_pixbuf(cr, pixbuf, 0, 0);
		cairo_pattern_set_extend(cairo_get_source(cr), CAIRO_EXTEND_REPEAT);
		cairo_paint(cr);
		g_object_unref(pixbuf);
	} else {
		g_warning("Could not find background image.");
	}
	struct {
		GtkWidget *container;
		cairo_t *cr;
	} data;
	data.container = widget;
	data.cr = cr;
	gtk_container_forall (GTK_CONTAINER(widget), draw_child, &data);
	return FALSE;
}

int
main(int argc, char* argv[]) {
	GtkWidget *win;
	GtkCssProvider *cssprovider;

	/* Disable global menus */
	g_unsetenv ("UBUNTU_MENUPROXY");
	gtk_init(&argc, &argv);
	win = gtk_window_new (GTK_WINDOW_TOPLEVEL);
	g_signal_connect(win, "realize", G_CALLBACK(on_realize), NULL);

	cssprovider = gtk_css_provider_new ();
	gtk_css_provider_load_from_data(cssprovider,
			"GtkMenuBar {\n"
			"    -GtkMenuBar-internal-padding: 0;\n"
			"    -GtkMenuBar-shadow-type: none;\n"
			"}\n"
			"GtkWidget {\n"
			"    -GtkWidget-focus-line-width: 0;\n"
			"    -GtkWidget-focus-padding: 0;\n"
			"}\n"
			".menuitem {\n"
			"    padding: 0px 0px 0px 0px;\n"
			"}\n", -1, NULL);

	gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),
		GTK_STYLE_PROVIDER (cssprovider), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);

	GtkWidget* menubar = gtk_menu_bar_new();
	gtk_menu_bar_set_pack_direction(GTK_MENU_BAR(menubar), GTK_PACK_DIRECTION_RTL);
	int i;
	for(i = 0; indicators[i]; i++) {
		if (!load_module(indicators[i], menubar)) {
			g_error("Unable to load module");
		}
	}
	GtkWidget* hbox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 3);
	gtk_container_add(GTK_CONTAINER(win), hbox);
	gtk_box_pack_end(GTK_BOX(hbox), menubar, FALSE, FALSE, 0);
	g_signal_connect_after(menubar, "draw", G_CALLBACK(on_draw), NULL);
	g_signal_connect(win, "draw", G_CALLBACK(on_draw), NULL);
	gtk_widget_show_all(win);
	gdk_window_process_updates(gtk_widget_get_window(win), TRUE);
	gtk_widget_set_app_paintable(win, TRUE);
	gtk_main();
	return 0;
}
