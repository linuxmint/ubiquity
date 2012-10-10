/* wallpaper - Small application to set a desktop background on all displays.
 * Almost entirely stolen from lightdm.
 *
 * Copyright (C) 2011 Canonical Ltd.
 * Copyright (C) 2010-2011 Robert Ancell.
 * Author: Robert Ancell <robert.ancell@canonical.com>
 * 
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version. See http://www.gnu.org/copyleft/gpl.html the full text of the
 * license.
 */

#include <gdk/gdkx.h>
#include <cairo-xlib.h>
#include <sys/stat.h>
#include <gtk/gtk.h>
#include <X11/Xatom.h>

static cairo_surface_t *
create_root_surface (GdkScreen *screen)
{
    Atom prop_root, prop_esetroot;
    gint number, width, height;
    Display *display;
    Pixmap pixmap;
    cairo_surface_t *surface;

    number = gdk_screen_get_number (screen);
    width = gdk_screen_get_width (screen);
    height = gdk_screen_get_height (screen);

    /* Open a new connection so with Retain Permanent so the pixmap remains when the greeter quits */
    gdk_flush ();
    display = XOpenDisplay (gdk_display_get_name (gdk_screen_get_display (screen)));
    if (!display)
    {
        g_warning ("Failed to create root pixmap");
        return NULL;
    }
    XSetCloseDownMode (display, RetainPermanent);
    pixmap = XCreatePixmap (display, RootWindow (display, number), width, height, DefaultDepth (display, number));
    XCloseDisplay (display);

    /* Convert into a Cairo surface */
    surface = cairo_xlib_surface_create (GDK_SCREEN_XDISPLAY (screen),
                                         pixmap,
                                         GDK_VISUAL_XVISUAL (gdk_screen_get_system_visual (screen)),
                                         width, height);

    /* Use this pixmap for the background */
    XSetWindowBackgroundPixmap (GDK_SCREEN_XDISPLAY (screen),
                                RootWindow (GDK_SCREEN_XDISPLAY (screen), number),
                                cairo_xlib_surface_get_drawable (surface));



    /* Fix to make the code work when a compositor is running */
    Pixmap xpm = cairo_xlib_surface_get_drawable (surface);
    prop_root = XInternAtom(GDK_SCREEN_XDISPLAY (screen), "_XROOTPMAP_ID", False);
    prop_esetroot = XInternAtom(GDK_SCREEN_XDISPLAY (screen), "ESETROOT_PMAP_ID", False);

    XChangeProperty(GDK_SCREEN_XDISPLAY (screen), RootWindow (GDK_SCREEN_XDISPLAY (screen), number), prop_root, XA_PIXMAP, 32, PropModeReplace, (unsigned char *) &xpm, 1);
    XChangeProperty(GDK_SCREEN_XDISPLAY (screen), RootWindow (GDK_SCREEN_XDISPLAY (screen), number), prop_esetroot, XA_PIXMAP, 32, PropModeReplace, (unsigned char *) &xpm, 1);


    return surface;
}

int main (int argc, char** argv) {
	GdkScreen *screen;
	int monitor;
	int i;
	GError *error = NULL;
	GdkPixbuf *background_pixbuf = NULL;
	GdkRectangle monitor_geometry;
	cairo_t *c;
	cairo_surface_t *surface;
	struct stat st;

	gtk_init (&argc, &argv);

	if (argc != 2 || stat(argv[1], &st) != 0) {
		g_error ("First parameter must be an existing background");
		return 1;
	}
	background_pixbuf = gdk_pixbuf_new_from_file (argv[1], &error);

	if (!background_pixbuf) {
		g_error ("Failed to load background: %s", error->message);
		return 1;
	}
	g_clear_error (&error);
	for (i = 0; i < gdk_display_get_n_screens (gdk_display_get_default ()); i++) {
		screen = gdk_display_get_screen (gdk_display_get_default (), i);
		surface = create_root_surface (screen);
		c = cairo_create (surface);
		for (monitor = 0; monitor < gdk_screen_get_n_monitors (screen); monitor++) {
			gdk_screen_get_monitor_geometry (screen, monitor, &monitor_geometry);
			GdkPixbuf *pixbuf = gdk_pixbuf_scale_simple (background_pixbuf,
				monitor_geometry.width, monitor_geometry.height,
				GDK_INTERP_BILINEAR);
			gdk_cairo_set_source_pixbuf (c, pixbuf, monitor_geometry.x, monitor_geometry.y);
			g_object_unref (pixbuf);
			cairo_paint (c);
		}
		cairo_destroy (c);
		gdk_flush ();
		XClearWindow (GDK_SCREEN_XDISPLAY (screen), RootWindow (GDK_SCREEN_XDISPLAY (screen), i));
	}
	gtk_main ();
	return 0;
}
