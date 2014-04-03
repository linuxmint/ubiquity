/*
 * Interface autoconfiguration functions for netcfg.
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
#include <sys/stat.h>
#include <unistd.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <debian-installer.h>

#define DHCP6C_PIDFILE "/var/run/dhcp6c.pid"
#define DHCP6C_FINISHED "/var/lib/netcfg/dhcp6c-finished"

static enum { DHCLIENT, DHCP6C } dhcpv6_client;
static int dhcpv6_pipe[2] = { -1, -1 };
static pid_t dhcpv6_pid = -1;
static int dhcpv6_exit_status = 1;

/* Signal handler for DHCPv6 client child
 *
 * When the child exits (either because it failed to obtain a
 * lease or because it succeeded and daemonized itself), this
 * gets the child's exit status and sets dhcpv6_pid to -1
 */
void cleanup_dhcpv6_client(void)
{
	if (dhcpv6_pid <= 0)
		/* Already cleaned up */
		return;

	if (waitpid(dhcpv6_pid, &dhcpv6_exit_status, WNOHANG) != dhcpv6_pid)
		/* Wasn't us */
		return;

	if (WIFEXITED(dhcpv6_exit_status) || WIFSIGNALED(dhcpv6_exit_status))
		dhcpv6_pid = -1;
}

/* Start whichever DHCPv6 client is available.
 *
 * The client's PID is stored in dhcpv6_pid.
 */
int start_dhcpv6_client(struct debconfclient *client, const struct netcfg_interface *interface)
{
	int dhcpv6_seconds = 0;

	if (access("/sbin/dhclient", F_OK) == 0)
		dhcpv6_client = DHCLIENT;
	else if (access("/usr/sbin/dhcp6c", F_OK) == 0)
		dhcpv6_client = DHCP6C;
	else {
		/* for now, fall back quietly (no debconf error) to IPv4 */
		di_error("No DHCPv6 client found");
		return 1;
	}

	if (pipe(dhcpv6_pipe) < 0) {
		di_error("Unable to create pipe: %s", strerror(errno));
		return 1;
	}

	if (dhcpv6_client == DHCP6C) {
		unlink(DHCP6C_FINISHED);

		if (!interface->v6_stateless_config) {
			/* So that poll_dhcpv6_client won't immediately give
			 * up:
			 */
			FILE *pidfile = fopen(DHCP6C_PIDFILE, "w");
			if (pidfile)
				fclose(pidfile);
		}
	}

	debconf_get(client, "netcfg/dhcpv6_timeout");
	dhcpv6_seconds = atoi(client->value);

	dhcpv6_pid = fork();
	if (dhcpv6_pid == 0) { /* child */
		FILE *dc;
		const char **arguments;
		int i = 0;

		/* disassociate from debconf */
		fclose(client->out);

		close(dhcpv6_pipe[0]);
		dup2(dhcpv6_pipe[1], 1);
		close(dhcpv6_pipe[1]);

		switch (dhcpv6_client) {
		    case DHCLIENT:
			dc = file_open(DHCLIENT6_FILE, "w");
			if (!dc)
				return 1;
			fprintf(dc, "send vendor-class-identifier \"d-i\";\n");
			fprintf(dc, "timeout %d;\n", dhcpv6_seconds);
			fclose(dc);

			arguments = malloc(10 * sizeof(*arguments));
			i = 0;
			arguments[i++] = "dhclient";
			arguments[i++] = "-6";
			if (interface->v6_stateless_config)
				arguments[i++] = "-S";
			arguments[i++] = "-cf";
			arguments[i++] = DHCLIENT6_FILE;
			arguments[i++] = "-sf";
			arguments[i++] = "/lib/netcfg/print-dhcpv6-info";
			arguments[i++] = interface->name;
			arguments[i++] = "-1";
			arguments[i] = NULL;
			execvp("dhclient", (char **)arguments);
			break;

		    case DHCP6C:
			if (!interface->v6_stateless_config) {
				/* In stateful mode, dhcp6c needs to stay
				 * running.  However, it daemonises itself
				 * in such a way as to throw away stdio,
				 * which interferes with our script
				 * communication.  To work around this,
				 * daemonise here without throwing away
				 * stdio and then run dhcp6c in foreground
				 * mode.
				 */
				if (daemon(0, 1) < 0) {
					di_error("daemon() failed: %s", strerror(errno));
					_exit(1);
				}
			}

			dc = file_open(DHCP6C_FILE, "w");
			if (!dc)
				return 1;
			fprintf(dc, "interface %s {\n", interface->name);
			if (interface->v6_stateless_config)
				fprintf(dc, "\tinformation-only;\n");
			else
				fprintf(dc, "\tsend ia-na 0;\n");
			fprintf(dc, "\trequest domain-name-servers;\n");
			fprintf(dc, "\trequest domain-name;\n");
			fprintf(dc, "\tscript \"/lib/netcfg/print-dhcp6c-info\";\n");
			fprintf(dc, "};\n");
			if (!interface->v6_stateless_config) {
				fprintf(dc, "id-assoc na 0 {\n");
				fprintf(dc, "};\n");
			}
			fclose(dc);

			arguments = malloc(6 * sizeof(*arguments));
			arguments[i++] = "dhcp6c";
			arguments[i++] = "-c";
			arguments[i++] = DHCP6C_FILE;
			arguments[i++] = "-f";
			arguments[i++] = interface->name;
			arguments[i] = NULL;
			execvp("dhcp6c", (char **)arguments);
			break;
		}

		if (errno)
			di_error("Could not exec DHCPv6 client: %s", strerror(errno));

		_exit(1); /* should never be reached */
	} else if (dhcpv6_pid == -1) {
		di_warning("DHCPv6 fork failed; this is unlikely to end well");
		close(dhcpv6_pipe[0]);
		close(dhcpv6_pipe[1]);
		dhcpv6_pipe[0] = dhcpv6_pipe[1] = -1;
		return 1;
	} else { /* parent */
		di_warning("Started DHCPv6 client; PID is %i", dhcpv6_pid);
		close(dhcpv6_pipe[1]);
		dhcpv6_pipe[1] = -1;
		signal(SIGCHLD, &sigchld_handler);
		return 0;
	}
}

/* Poll the started DHCP client for netcfg/dhcpv6_timeout seconds (def. 15)
 * and return true if a lease is known to have been acquired, 0 otherwise.
 *
 * The client should be run such that it exits once a lease is acquired
 * (although its child continues to run as a daemon).  Unfortunately, dhcp6c
 * can only daemonise immediately rather than waiting for a lease, so we
 * have to handle this for the stateful case.
 *
 * This function will NOT kill the child if time runs out.  This allows
 * the user to choose to wait longer for the lease to be acquired.
 */
static int poll_dhcpv6_client (struct debconfclient *client, const struct netcfg_interface *interface)
{
	int seconds_slept = 0;
	int dhcpv6_seconds;
	int got_lease = -1;
	int ret = 0;

	debconf_get(client, "netcfg/dhcpv6_timeout");

	dhcpv6_seconds = atoi(client->value);

	/* show progress bar */
	debconf_capb(client, "backup progresscancel");
	debconf_progress_start(client, 0, dhcpv6_seconds, "netcfg/dhcpv6_progress");
	if (debconf_progress_info(client, "netcfg/dhcp_progress_note") == 30)
		goto stop;

	for (;;) {
		struct stat st;

		switch (dhcpv6_client) {
		    case DHCLIENT:
			if (dhcpv6_pid <= 0)
				got_lease = (dhcpv6_exit_status == 0);
			break;

		    case DHCP6C:
			if (dhcpv6_pid <= 0 && dhcpv6_exit_status != 0) {
				got_lease = 0;
				break;
			}

			if (!interface->v6_stateless_config &&
			    dhcpv6_pid <= 0) {
				/* In stateful mode, we run dhcp6c as a
				 * daemon (because it doesn't wait for a
				 * lease before daemonising anyway, and this
				 * lets us set up its file descriptors
				 * properly), so dhcpv6_pid will exit fairly
				 * quickly.  We can check its pid file to
				 * find out whether it's really exited, in
				 * which case we'll have lost the lease.
				 */
				if (stat(DHCP6C_PIDFILE, &st) < 0) {
					got_lease = 0;
					break;
				}
			}

			/* We write a sentinel file at the end of
			 * print-dhcp6c-info, which is a solid indication
			 * that we got useful configuration.
			 */
			if (stat(DHCP6C_FINISHED, &st) == 0) {
				got_lease = 1;
				break;
			}
			break;
		}

		if (got_lease != -1 || seconds_slept++ >= dhcpv6_seconds)
			break;
		sleep(1);
		if (debconf_progress_step(client, 1) == 30)
			goto stop;
	}

	if (got_lease == 1) {
		ret = 1;

		debconf_capb(client, "backup"); /* stop displaying cancel button */
		if (debconf_progress_set(client, dhcpv6_seconds) == 30)
			goto stop;
		if (debconf_progress_info(client, "netcfg/dhcp_success_note") == 30)
			goto stop;
		sleep(1);
	}

stop:
	/* stop progress bar */
	debconf_progress_stop(client);
	debconf_capb(client, "backup");

	/* terminate dhcp6c if there's no lease or information yet */
	if (dhcpv6_client == DHCP6C && (got_lease != 1 || dhcpv6_pid > 0)) {
		FILE *pidfile = fopen(DHCP6C_PIDFILE, "r");
		if (pidfile) {
			char *line = NULL;
			size_t dummy;

			if (getline(&line, &dummy, pidfile) >= 0) {
				pid_t pid;

				errno = 0;
				pid = strtol(line, NULL, 10);
				if (errno == 0)
					kill(pid, SIGTERM);
			}

			free(line);
			fclose(pidfile);
		}
	}

	if (dhcpv6_client == DHCP6C)
		unlink(DHCP6C_FINISHED);

	return ret;
}

/* Configure the interface using DHCPv6. */
static int netcfg_dhcpv6(struct debconfclient *client, struct netcfg_interface *interface)
{
	FILE *dhcpv6_reader = NULL;
	char l[512], *p;
	int ns_idx, ntp_idx = 0;
	int rv;

	if (interface->v6_stateless_config)
		di_debug("Stateless DHCPv6 requested");
	else
		di_debug("Stateful DHCPv6 requested");

	/* Append any nameservers obtained via DHCP to the list of
	 * nameservers in the RA, rather than overwriting them
	 */
	ns_idx = nameserver_count(interface);

	if (start_dhcpv6_client(client, interface)) {
		di_warning("DHCPv6 client failed to start.  Aborting DHCPv6 configuration.");
		return 0;
	}

	rv = poll_dhcpv6_client(client, interface);

	dhcpv6_reader = fdopen(dhcpv6_pipe[0], "r");
	while (fgets(l, sizeof(l), dhcpv6_reader) != NULL) {
		rtrim(l);
		di_debug("DHCPv6 line: %s", l);

		if (!strncmp("nameserver[", l, 11) && ns_idx < NETCFG_NAMESERVERS_MAX) {
			p = strstr(l, "] ") + 2;
			strncpy(interface->nameservers[ns_idx], p, sizeof(interface->nameservers[ns_idx]));
			ns_idx++;
		} else if (!strncmp("NTP server[", l, 11) && ntp_idx < NETCFG_NTPSERVERS_MAX) {
			p = strstr(l, "] ") + 2;
			strncpy(interface->ntp_servers[ns_idx++], p, sizeof(interface->ntp_servers[ntp_idx]));
			ntp_idx++;
		} else if (!strncmp("Domain search list[0] ", l, 21)) {
			p = strstr(l, "] ") + 2;
			strncpy(domain, p, sizeof(domain));
			/* Strip trailing . */
			if (domain[strlen(domain)-1] == '.') {
				domain[strlen(domain)-1] = '\0';
			}
			have_domain = 1;
		} else if (!strcmp("end", l)) {
			/* The write end of the pipe won't necessarily be
			 * closed in the stateful case, so this hack lets us
			 * break out.
			 */
			break;
		}
	}
	fclose(dhcpv6_reader);
	dhcpv6_pipe[0] = -1;
	if (dhcpv6_client == DHCP6C &&
	    interface->v6_stateless_config && dhcpv6_pid > 0)
		/* dhcp6c doesn't exit after printing information unless in
		 * info-req (-i) mode, which is incompatible with supplying
		 * a configuration; so just kill the client now.
		 */
		kill(dhcpv6_pid, SIGTERM);

	/* Empty any other nameservers/NTP servers that might
	 * have been left over from a previous config run
	 */
	for (; ns_idx < NETCFG_NAMESERVERS_MAX; ns_idx++) {
		*(interface->nameservers[ns_idx]) = '\0';
	}
	for (; ntp_idx < NETCFG_NTPSERVERS_MAX; ntp_idx++) {
		*(interface->ntp_servers[ntp_idx]) = '\0';
	}

	return rv;
}

/* Configure the network using IPv6 router advertisements, and possibly
 * stateless DHCPv6 announcements (if appropriate).  Return 1 if all
 * went well, and 0 otherwise.
 */
static int netcfg_slaac(struct debconfclient *client, struct netcfg_interface *interface)
{
	const int SLAAC_MAX_WAIT = 5;  /* seconds */
	int count, rv = 0;
	
	/* STEP 1: Ensure the interface has finished configuring itself */

	/* Progress bar... fun! */
	debconf_capb(client, "progresscancel");
	debconf_progress_start(client, 0, SLAAC_MAX_WAIT * 4, "netcfg/slaac_wait_title");
	
	for (count = 0; count < SLAAC_MAX_WAIT * 4; count++) {
		usleep(250000);
		if (debconf_progress_step(client, 1) == 30) {
			/* User cancel */
			rv = 0;
			break;
		}
		if (nc_v6_interface_configured(interface, 0)) {
			debconf_progress_set(client, SLAAC_MAX_WAIT * 4);
			rv = 1;
			break;
		}
	}
	debconf_progress_stop(client);
	
	/* STEP 2: Stateless DHCP? */
	if (interface->v6_stateless_config)
		netcfg_dhcpv6(client, interface);

	return rv;
}

/* This function handles all of the autoconfiguration for the given interface.
 *
 * Autoconfiguration of an interface in netcfg has grown significantly
 * in recent times.  From humble beginnings that started with "yeah, just
 * fire up udhcpc and see what happens", the scope has expanded to
 * include all manner of IPv6 gubbins.
 *
 * Hence, this function exists to wrap all of that into a single neat
 * package.  If you want to autoconfigure an interface, just run it through
 * this, and if autoconfiguration was successful to at least the point of
 * assigning an IP address, we will return a healthy bouncing baby '1' to
 * you.  Otherwise, we'll give you the bad news with a '0' -- and you'll
 * either have to try another interface, or manually configure it.
 *
 * Note that we only guarantee that you'll have an IP address as a result
 * of successful completion.  You'll need to check what else has been
 * configured (gateway, hostname, etc) and respond to the user appropriately.
 * Also, the fields in +interface+ that deal directly with IP address,
 * gateway, etc will *not* be populated -- just the flags that talk about
 * what sort of autoconfiguration was completed.
 */
int netcfg_autoconfig(struct debconfclient *client, struct netcfg_interface *interface)
{
	int ipv6;

	di_debug("Want link on %s", interface->name);
	netcfg_detect_link(client, interface);

	di_debug("Commencing network autoconfiguration on %s", interface->name);
	interface->dhcp = interface->slaac = interface->dhcpv6 = 0;

	/* We need to start rdnssd before anything else, because it never
	 * sends it's own ND packets, it just watches for ones already
	 * on the wire.  Thankfully, the use of rdisc6 in
	 * nc_v6_get_config_flags() will send NDs for us.
	 */
	start_rdnssd(client);

	/* Now we prod the network to see what is available */
	ipv6 = nc_v6_get_config_flags(client, interface);

	/* And now we cleanup from rdnssd */
	if (ipv6) {
		read_rdnssd_nameservers(interface);
		if (nameserver_count(interface) > 0) {
			di_exec_shell_log("apt-install rdnssd");
		}
	}
	
	stop_rdnssd();

	if (ipv6) {
		di_debug("IPv6 found");
		if (interface->v6_stateful_config == 1) {
			di_debug("IPv6 stateful autoconfig requested");
			if (netcfg_dhcpv6(client, interface))
				interface->dhcpv6 = 1;
		} else {
			di_debug("IPv6 stateless autoconfig requested");
			if (netcfg_slaac(client, interface))
				interface->slaac = 1;
		}
	}

	if (ipv6)
		di_debug("Trying IPv4 autoconfig as well");
	else
		/* No RA was received; assuming that IPv6 is not available
		 * on this network and falling back to IPv4
		 */
		di_debug("No RA received; attempting IPv4 autoconfig");
	if (netcfg_dhcp(client, interface))
		interface->dhcp = 1;

	return interface->dhcp || interface->slaac || interface->dhcpv6;
}
