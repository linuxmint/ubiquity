/* autodown.c - Allow triggering of gdm options.

   Written by Rob Taylor.

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 2, or (at your option)
   any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA
   02111-1307, USA.  */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <glib.h>
#include <gtk/gtk.h>
#include "gdm-logout-action.h"

static int do_hibernate = FALSE;
static int do_suspend = FALSE;
static int do_halt = FALSE;
static int do_reboot = FALSE;
GOptionEntry entries[] = {
  {
    "hibernate",
    'z',
    0,
    G_OPTION_ARG_NONE,
    &do_hibernate,
    "Hibernate the machine",
    NULL
  },
  {
    "halt",
    'h',
    0,
    G_OPTION_ARG_NONE,
    &do_halt,
    "Halt the machine",
    NULL
  },
  {
    "suspend",
    's',
    0,
    G_OPTION_ARG_NONE,
    &do_suspend,
    "Suspend the machine",
    NULL
  },
  {
    "reboot",
    'r',
    0,
    G_OPTION_ARG_NONE,
    &do_reboot,
    "Reboot the machine",
    NULL
  },
  { NULL }
};


int main(int argc, char **argv)
{
  gboolean halt_supported, suspend_supported, hibernate_supported, reboot_supported;

  GdmLogoutAction suspend_action;
  GError *error=NULL;

  GOptionContext* context = g_option_context_new ("- make the machine sleep in some way");
  g_option_context_add_main_entries (context, entries, NULL);
  g_option_context_add_group (context, gtk_get_option_group (TRUE));
  if (!g_option_context_parse (context, &argc, &argv, &error)) {
    fprintf (stderr, "gdm-signal: %s\n", error->message);
    g_error_free (error);
    return 1;
  }

  g_option_context_free(context);



  halt_supported   = gdm_supports_logout_action (GDM_LOGOUT_ACTION_SHUTDOWN);
  suspend_supported = gdm_supports_logout_action (GDM_LOGOUT_ACTION_SUSPEND);
  hibernate_supported = gdm_supports_logout_action (GDM_LOGOUT_ACTION_HIBERNATE);
  reboot_supported = gdm_supports_logout_action (GDM_LOGOUT_ACTION_REBOOT);
  if (halt_supported && do_halt)
    suspend_action = GDM_LOGOUT_ACTION_SHUTDOWN;
  else if (suspend_supported && do_suspend) 
    suspend_action = GDM_LOGOUT_ACTION_SUSPEND;
  else if (hibernate_supported && do_hibernate) 
    suspend_action = GDM_LOGOUT_ACTION_HIBERNATE;
  else if (reboot_supported && do_reboot)
    suspend_action = GDM_LOGOUT_ACTION_REBOOT;

  gdm_set_logout_action (suspend_action);

  return 0;
}

