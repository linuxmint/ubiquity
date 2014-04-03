/*
 * Management of the rdnssd instance that we use to get DNS info out of
 * RAs.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
 */

#include "netcfg.h"
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <sys/types.h>
#include <signal.h>
#include <debian-installer.h>

static pid_t rdnssd_pid;

/* Spawn an rdnssd child process.
 *
 * Returns 1 on a successful start, and 0 on error.  Stores the child pid in
 * a module-internal global variable, as this is easier than trying to pass
 * it around everywhere (given that we'll need to get at it in a signal
 * handler...)
 */
int start_rdnssd(struct debconfclient *client)
{
	if ((rdnssd_pid = fork()) == 0) {   /* Child */
		/* Dissociate from debconf */
		fclose(client->out);
		
		/* Kick things off */
		execlp("rdnssd", "rdnssd", "-f", "-u", "root", "-r", "/tmp/rdnssd_resolv", NULL);
		
		/* If we get here, something went wrong */
		di_error("Could not exec dnssd: %s", strerror(errno));
		
		exit(1);
	} else if (rdnssd_pid == -1) {
		di_warning("rdnssd fork failed: %s", strerror(errno));
		return 0;
	} else {
		di_debug("rdnssd started; PID: %i", rdnssd_pid);
		return 1;
	}
}

/* Cleanup after the rdnssd process if/when it exits
 *
 * This gets called from the SIGCHLD handler to see if it was rdnssd that
 * exited, and if so, perform whatever cleanup tasks were necessary.
 */
void cleanup_rdnssd()
{
	int exit_status;
	
	if (rdnssd_pid == -1)
		/* Definitely wasn't us */
		return;
	
	if (waitpid(rdnssd_pid, &exit_status, WNOHANG) != rdnssd_pid)
		/* Not us either */
		return;

	if (WIFEXITED(exit_status))
		/* Yep, that was me */
		rdnssd_pid = -1;
}

/* Read the nameserver entries that rdnssd may have written out into the
 * interface struct.
 */
void read_rdnssd_nameservers(struct netcfg_interface *interface)
{
	read_resolv_conf_nameservers("/tmp/rdnssd_resolv", interface);
}

/* Stop the rdnssd client process.
 */
void stop_rdnssd()
{
	if (rdnssd_pid == -1) {
		/* We're not running... that would be bad */
		return;
	}
	di_debug("Stopping rdnssd, PID %i", rdnssd_pid);
	kill(rdnssd_pid, SIGTERM);
}
