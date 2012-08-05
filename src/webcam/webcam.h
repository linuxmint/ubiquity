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

#ifndef _UBIQUITY_WEBCAM_H
#define _UBIQUITY_WEBCAM_H

#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <gst/gst.h>
#include <gst/interfaces/xoverlay.h>


G_BEGIN_DECLS

#define UBIQUITY_TYPE_WEBCAM ubiquity_webcam_get_type()

#define UBIQUITY_WEBCAM(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST ((obj), \
  UBIQUITY_TYPE_WEBCAM, UbiquityWebcam))

#define UBIQUITY_WEBCAM_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST ((klass), \
  UBIQUITY_TYPE_WEBCAM, UbiquityWebcamClass))

#define UBIQUITY_IS_WEBCAM(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE ((obj), \
  UBIQUITY_TYPE_WEBCAM))

#define UBIQUITY_IS_WEBCAM_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE ((klass), \
  UBIQUITY_TYPE_WEBCAM))

#define UBIQUITY_WEBCAM_GET_CLASS(obj) \
  (G_TYPE_INSTANCE_GET_CLASS ((obj), \
  UBIQUITY_TYPE_WEBCAM, UbiquityWebcamClass))

typedef struct _UbiquityWebcam UbiquityWebcam;
typedef struct _UbiquityWebcamClass UbiquityWebcamClass;
typedef struct _UbiquityWebcamPrivate UbiquityWebcamPrivate;

struct _UbiquityWebcam
{
  GtkBox parent;

  UbiquityWebcamPrivate *priv;
};

struct _UbiquityWebcamClass
{
  GtkBoxClass parent_class;
};

GType ubiquity_webcam_get_type (void) G_GNUC_CONST;

UbiquityWebcam *ubiquity_webcam_new (void);
void ubiquity_webcam_play (UbiquityWebcam *webcam);
void ubiquity_webcam_stop (UbiquityWebcam *webcam);
gboolean ubiquity_webcam_available (void);
void ubiquity_webcam_test (UbiquityWebcam *webcam);

G_END_DECLS

#endif /* _UBIQUITY_WEBCAM_H */

