/* MockResolver - a very stupid resolver used in test code
 *
 * This resolver always resolves a given hostname successfully, and returns
 * an error for anything else.  It only implements just enough of the API to
 * fool the usersetup plugin.
 *
 * This is really gross overkill; it would be much quicker to do it in
 * Python, except that https://bugzilla.gnome.org/show_bug.cgi?id=669847
 * frustrates attempts to do so.
 *
 * Copyright (C) 2012 Canonical Ltd.
 * Author: Colin Watson <cjwatson@ubuntu.com>
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

#include <glib.h>
#include <glib-object.h>
#include <gio/gio.h>

#include "mockresolver.h"

struct _UbiquityMockResolverPrivate
{
	gchar *hostname;
};

enum {
	PROP_0,
	PROP_HOSTNAME
};

G_DEFINE_TYPE (UbiquityMockResolver, ubiquity_mock_resolver, G_TYPE_RESOLVER)

static void
ubiquity_mock_resolver_init (UbiquityMockResolver *self) {
	self->priv = G_TYPE_INSTANCE_GET_PRIVATE (self,
						  UBIQUITY_TYPE_MOCK_RESOLVER,
						  UbiquityMockResolverPrivate);
	self->priv->hostname = NULL;
}

static void
ubiquity_mock_resolver_finalize (GObject *object) {
	UbiquityMockResolver *self = UBIQUITY_MOCK_RESOLVER (object);

	g_free (self->priv->hostname);

	G_OBJECT_CLASS (ubiquity_mock_resolver_parent_class)->finalize
		(object);
}

UbiquityMockResolver *
ubiquity_mock_resolver_new (void) {
	return g_object_new (UBIQUITY_TYPE_MOCK_RESOLVER, NULL);
}

static void
ubiquity_mock_resolver_set_hostname (UbiquityMockResolver *self,
				     const gchar *hostname) {
	self->priv->hostname = g_strdup (hostname ? hostname : "");
}

static void
ubiquity_mock_resolver_set_property (GObject *object, guint prop_id,
				     const GValue *value, GParamSpec *pspec) {
	UbiquityMockResolver *self = UBIQUITY_MOCK_RESOLVER (object);

	switch (prop_id) {
		case PROP_HOSTNAME:
			ubiquity_mock_resolver_set_hostname
				(self, g_value_get_string (value));
			break;
		default:
			G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id,
							   pspec);
			break;
	}
}

static void
ubiquity_mock_resolver_get_property (GObject *object, guint prop_id,
				     GValue *value, GParamSpec *pspec) {
	UbiquityMockResolver *self = UBIQUITY_MOCK_RESOLVER (object);

	switch (prop_id) {
		case PROP_HOSTNAME:
			g_value_set_string (value, self->priv->hostname);
			break;
		default:
			G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id,
							   pspec);
			break;
	}
}

static void
ubiquity_mock_resolver_lookup_by_name_async (GResolver *resolver,
					     const gchar *hostname,
					     GCancellable *cancellable,
					     GAsyncReadyCallback callback,
					     gpointer user_data) {
	UbiquityMockResolver *self = UBIQUITY_MOCK_RESOLVER (resolver);
	GSimpleAsyncResult *result;

	result = g_simple_async_result_new
		(G_OBJECT (self), callback, user_data,
		 ubiquity_mock_resolver_lookup_by_name_async);
	if (g_strcmp0 (hostname, self->priv->hostname) == 0) {
		GInetAddress *addr;
		addr = g_inet_address_new_from_string ("127.0.0.1");
		g_simple_async_result_set_op_res_gpointer (result, addr,
							   g_object_unref);
	} else {
		GError *error;
		error = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_FAILED,
					     "Test error");
		g_simple_async_result_set_from_error (result, error);
	}
	g_simple_async_result_complete_in_idle (result);
	g_object_unref (result);
}

static GList *
ubiquity_mock_resolver_lookup_by_name_finish (GResolver *resolver,
					      GAsyncResult *result,
					      GError **error) {
	GInetAddress *addr;

	g_return_val_if_fail (g_simple_async_result_is_valid
		(result, G_OBJECT (resolver),
		 ubiquity_mock_resolver_lookup_by_name_async), NULL);

	addr = g_simple_async_result_get_op_res_gpointer
		(G_SIMPLE_ASYNC_RESULT (result));
	g_object_ref (addr);
	return g_list_append (NULL, addr);
}

static void
ubiquity_mock_resolver_class_init (UbiquityMockResolverClass *klass) {
	GResolverClass *resolver_class = G_RESOLVER_CLASS (klass);
	GObjectClass *object_class = G_OBJECT_CLASS (klass);

	g_type_class_add_private (klass, sizeof (UbiquityMockResolverPrivate));

	resolver_class->lookup_by_name_async =
		ubiquity_mock_resolver_lookup_by_name_async;
	resolver_class->lookup_by_name_finish =
		ubiquity_mock_resolver_lookup_by_name_finish;

	object_class->set_property = ubiquity_mock_resolver_set_property;
	object_class->get_property = ubiquity_mock_resolver_get_property;
	object_class->finalize = ubiquity_mock_resolver_finalize;

	g_object_class_install_property (
		object_class, PROP_HOSTNAME,
		g_param_spec_string (
			"hostname", "Local host name",
			"The host name to resolve to 127.0.0.1", "",
			G_PARAM_WRITABLE | G_PARAM_STATIC_NAME |
			G_PARAM_STATIC_NICK | G_PARAM_STATIC_BLURB));
}
