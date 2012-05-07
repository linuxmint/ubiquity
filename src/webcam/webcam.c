/* UbiquityWebcam - a library interface to webcams over GStreamer and V4L2.
 * 
 * Copyright (C) 2011 Canonical Ltd.
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

/* LD_LIBRARY_PATH=.libs GI_TYPELIB_PATH=. ipython
 * from gi.repository import UbiquityWebcam
 * w = UbiquityWebcam.Webcam()
 */

#include <assert.h>

#include <glib-object.h>
#include <gtk/gtk.h>

#define G_UDEV_API_IS_SUBJECT_TO_CHANGE 1
#include <gudev/gudev.h>

#include "webcam.h"

static void button_clicked_cb (GtkWidget *widget, GstElement *camerabin);
static gboolean message_cb (GstBus *bus, GstMessage *msg, gpointer data);
static GstBusSyncReply window_id_cb (GstBus *bus, GstMessage *msg, gpointer data);

G_DEFINE_TYPE (UbiquityWebcam, ubiquity_webcam, GTK_TYPE_BOX)

#define UBIQUITY_WEBCAM_PRIVATE(o) \
	(G_TYPE_INSTANCE_GET_PRIVATE ((o), UBIQUITY_TYPE_WEBCAM, UbiquityWebcamPrivate))

struct _UbiquityWebcamPrivate
{
	GtkWidget *drawing_area;
	GtkWidget *button;
	GstElement *camerabin;
	GstElement *sink;
	GstElement *src;
	GstElement *testsrc;
	GstElement *fakevideosink;
	GstCaps *viewfinder_caps;
	GstBus *bus;
};

enum {
	PROP_0,
	PROP_BUTTON
};

static gulong video_window_xid = 0;

static void
ubiquity_webcam_get_property (GObject *object, guint prop_id, GValue *value,
			      GParamSpec *pspec) {
	UbiquityWebcamPrivate *priv = UBIQUITY_WEBCAM_PRIVATE (object);

	switch (prop_id) {
		case PROP_BUTTON:
			g_value_set_object (value, (GObject *) priv->button);
			break;
		default:
			G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id,
							   pspec);
	}
}

static void
ubiquity_webcam_class_init (UbiquityWebcamClass *klass) {
	GObjectClass *object_class = G_OBJECT_CLASS (klass);
	GtkWidgetClass *widget_class = GTK_WIDGET_CLASS (klass);
	GtkBoxClass *box_class = GTK_BOX_CLASS (klass);

	object_class->get_property = ubiquity_webcam_get_property;

	g_object_class_install_property (
		object_class, PROP_BUTTON,
		g_param_spec_object (
			"take-button", "'Take Photo' button",
			"The button that may be pressed to take a photo",
			GTK_TYPE_WIDGET,
			G_PARAM_READABLE | G_PARAM_STATIC_NAME |
			G_PARAM_STATIC_NICK | G_PARAM_STATIC_BLURB));

	g_type_class_add_private (klass, sizeof (UbiquityWebcamPrivate));
}

static void
drawing_area_realized_cb (GtkWidget *widget, gpointer data) {
	video_window_xid = GDK_WINDOW_XID (gtk_widget_get_window (widget));
}

static void
ubiquity_webcam_init (UbiquityWebcam *self) {
	UbiquityWebcamPrivate *priv;
	gint width = 172, height = 129;

	assert (width * 3 == height * 4); /* 4x3 ratio */

	priv = self->priv = UBIQUITY_WEBCAM_PRIVATE (self);

	gtk_orientable_set_orientation (GTK_ORIENTABLE (self),
					GTK_ORIENTATION_VERTICAL);
	gtk_box_set_spacing (GTK_BOX (self), 1);
	priv->drawing_area = gtk_drawing_area_new ();
	gtk_widget_set_size_request (priv->drawing_area, width, height);
	g_signal_connect (priv->drawing_area, "realize",
			G_CALLBACK(drawing_area_realized_cb), NULL);
	gtk_widget_set_double_buffered (priv->drawing_area, FALSE);

	priv->button = gtk_button_new ();
	gtk_button_set_label (GTK_BUTTON (priv->button), "Take Photo");

	gtk_box_pack_start (GTK_BOX (self), priv->drawing_area, TRUE, TRUE, 0);
	gtk_box_pack_start (GTK_BOX (self), priv->button, FALSE, FALSE, 0);

	priv->camerabin = gst_element_factory_make ("camerabin2" , "cam");
	priv->viewfinder_caps = gst_caps_new_simple ("video/x-raw-rgb",
		"width", G_TYPE_INT, 640,
		"height", G_TYPE_INT, 480, NULL);
	g_object_set (G_OBJECT (priv->camerabin),
		"viewfinder-caps", priv->viewfinder_caps, NULL);
    g_signal_new ("image-captured",
					UBIQUITY_TYPE_WEBCAM,
					G_SIGNAL_RUN_FIRST,
					0,
					NULL,
					NULL,
					g_cclosure_marshal_VOID__OBJECT,
					G_TYPE_NONE, 1,
					G_TYPE_STRING);
	if (!priv->camerabin) {
		g_print ("Failed to create camerabin.\n");
		return;
	}
	g_signal_connect (priv->button, "clicked",
			G_CALLBACK(button_clicked_cb), priv->camerabin);

	priv->bus = gst_element_get_bus (priv->camerabin);
	gst_bus_add_signal_watch (priv->bus);
	g_signal_connect (priv->bus, "message", G_CALLBACK (message_cb), self);
	gst_bus_set_sync_handler (priv->bus, (GstBusSyncHandler) window_id_cb, NULL);
	gst_object_ref (priv->bus);
	gst_object_ref (priv->camerabin);
}

void
ubiquity_webcam_test (UbiquityWebcam *webcam) {
	UbiquityWebcamPrivate *priv = UBIQUITY_WEBCAM_PRIVATE (webcam);
	if (!priv || !priv->camerabin)
		return;
	if (priv->src)
		return;
	priv->src = gst_element_factory_make ("wrappercamerabinsrc", NULL);
	priv->testsrc = gst_element_factory_make ("videotestsrc", NULL);
	g_object_set (G_OBJECT (priv->testsrc), "is-live", TRUE,
		"peer-alloc", FALSE, NULL);
	g_object_set (G_OBJECT (priv->src), "video-source", priv->testsrc, NULL);
	g_object_set (G_OBJECT (priv->camerabin), "camera-source", priv->src, NULL);
	ubiquity_webcam_stop (webcam);
	ubiquity_webcam_play (webcam);
	gst_object_ref (priv->src);
	gst_object_ref (priv->testsrc);
}

gboolean
ubiquity_webcam_available (void) {
	GUdevEnumerator *enumerator;
	GUdevClient *client;
	GList *devices;
	guint length;
  	const gchar *const subsystems[] = {NULL};
  	client = g_udev_client_new (subsystems);
	enumerator = g_udev_enumerator_new (client);
	g_udev_enumerator_add_match_property (enumerator, "ID_V4L_CAPABILITIES", ":capture:");
	devices = g_udev_enumerator_execute (enumerator);
	length = g_list_length (devices);
	g_list_free_full (devices, g_object_unref);
	return length > 0;
}

void
ubiquity_webcam_play (UbiquityWebcam *webcam) {
	UbiquityWebcamPrivate *priv = UBIQUITY_WEBCAM_PRIVATE (webcam);
	if (!priv || !priv->camerabin)
		return;
	if (gst_element_set_state (priv->camerabin, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE) {
		g_print ("setting camerabin to PLAYING failed\n");
		return;
	}
}

void
ubiquity_webcam_stop (UbiquityWebcam *webcam) {
	UbiquityWebcamPrivate *priv = UBIQUITY_WEBCAM_PRIVATE (webcam);
	if (!priv || !priv->camerabin)
		return;
	if (gst_element_set_state (priv->camerabin, GST_STATE_NULL) == GST_STATE_CHANGE_FAILURE) {
		g_print ("setting camerabin to STOPPED failed\n");
		return;
	}
}

UbiquityWebcam*
ubiquity_webcam_new (void) {
	return g_object_new (UBIQUITY_TYPE_WEBCAM, NULL);
}

static void
ubiquity_webcam_realize (GtkWidget *widget)
{
}
static gboolean
message_cb (GstBus *bus, GstMessage *msg, gpointer data) {
	const GstStructure *st;
	switch (GST_MESSAGE_TYPE (msg)) {
		case GST_MESSAGE_ERROR: {
			GError *err = NULL;
			gchar *debug = NULL;
			gst_message_parse_error (msg, &err, &debug);
			g_warning ("Error: %s [%s]\n", err->message, debug);
			g_error_free (err);
			g_free (debug);
			break;
		}
	}
	st = gst_message_get_structure (msg);
	//if (st)
	//	g_message("name: %s\n", gst_structure_get_name (st));
	if (st && gst_structure_has_name (st, "image-done"))
		g_signal_emit_by_name (data, "image-captured", "/tmp/webcam_photo.jpg");
	else if (st && gst_structure_has_name (st, "preview-image"))
		g_message ("preview\n");
	return TRUE;

}

static void
button_clicked_cb (GtkWidget *widget, GstElement *camerabin) {
	GstElement *pngenc;
	pngenc = gst_element_factory_make ("pngenc", "png");
	if (!pngenc) {
		g_print ("Failed to create pngenc.\n");
		return;
	}
	g_object_set (G_OBJECT(camerabin), "location", "/tmp/webcam_photo.jpg", NULL);
	g_object_set (G_OBJECT(camerabin), "post-previews", FALSE, NULL);
	g_signal_emit_by_name (camerabin, "start-capture", NULL);

}

static void
window_destroy_cb (GtkWidget *win, GstElement *camerabin) {
	//gst_element_set_state (camerabin, GST_STATE_NULL);
	gtk_main_quit ();
}

static GstBusSyncReply
window_id_cb (GstBus *bus, GstMessage *msg, gpointer data) {

	if (GST_MESSAGE_TYPE (msg) != GST_MESSAGE_ELEMENT)
		return GST_BUS_PASS;

	if (!gst_structure_has_name (msg->structure, "prepare-xwindow-id"))
		return GST_BUS_PASS;

	g_object_set(G_OBJECT(msg->src), "force-aspect-ratio", TRUE, NULL);

	gst_x_overlay_set_xwindow_id (GST_X_OVERLAY (GST_MESSAGE_SRC(msg)),
								video_window_xid);
	gst_message_unref (msg);
	return GST_BUS_DROP;
}

int
main(int argc, char** argv) {
	GtkWidget *win;
	UbiquityWebcam *webcam;
	gtk_init(&argc, &argv);
	gst_init(&argc, &argv);

	win = gtk_window_new (GTK_WINDOW_TOPLEVEL);

	webcam = ubiquity_webcam_new ();
	gtk_container_add (GTK_CONTAINER (win), GTK_WIDGET (webcam));

	gtk_widget_show_all (win);
	ubiquity_webcam_play (webcam);
	if (!ubiquity_webcam_available ())
		ubiquity_webcam_test (webcam);

	g_assert (video_window_xid != 0);
	g_signal_connect (win, "destroy", G_CALLBACK (window_destroy_cb), NULL);
	gtk_main();
	return 0;
}
