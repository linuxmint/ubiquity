/* MockResolver - a very stupid resolver used in test code
 *
 * This resolver always resolves a given hostname successfully, and returns
 * an error for anything else.  It only implements just enough of the API to
 * fool the usersetup plugin.
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

#ifndef _UBIQUITY_MOCK_RESOLVER_H
#define _UBIQUITY_MOCK_RESOLVER_H

#include <glib.h>
#include <glib-object.h>
#include <gio/gio.h>

G_BEGIN_DECLS

#define UBIQUITY_TYPE_MOCK_RESOLVER ubiquity_mock_resolver_get_type()

#define UBIQUITY_MOCK_RESOLVER(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST ((obj), \
  UBIQUITY_TYPE_MOCK_RESOLVER, UbiquityMockResolver))

#define UBIQUITY_MOCK_RESOLVER_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST ((klass), \
  UBIQUITY_TYPE_MOCK_RESOLVER, UbiquityMockResolverClass))

#define UBIQUITY_IS_MOCK_RESOLVER(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE ((obj), \
  UBIQUITY_TYPE_MOCK_RESOLVER))

#define UBIQUITY_IS_MOCK_RESOLVER_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE ((klass), \
  UBIQUITY_TYPE_MOCK_RESOLVER))

#define UBIQUITY_MOCK_RESOLVER_GET_CLASS(obj) \
  (G_TYPE_INSTANCE_GET_CLASS ((obj), \
  UBIQUITY_TYPE_MOCK_RESOLVER, UbiquityMockResolverClass))

typedef struct _UbiquityMockResolver UbiquityMockResolver;
typedef struct _UbiquityMockResolverClass UbiquityMockResolverClass;
typedef struct _UbiquityMockResolverPrivate UbiquityMockResolverPrivate;

struct _UbiquityMockResolver
{
  GResolver parent;

  UbiquityMockResolverPrivate *priv;
};

struct _UbiquityMockResolverClass
{
  GResolverClass parent_class;
};

GType ubiquity_mock_resolver_get_type (void) G_GNUC_CONST;

UbiquityMockResolver *ubiquity_mock_resolver_new (void);

G_END_DECLS

#endif /* _UBIQUITY_MOCK_RESOLVER_H */
