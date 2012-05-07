#include <debian-installer.h>
#include <cdebconf/debconfclient.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#include <ctype.h>
#include "mirrors.h"
#ifdef WITH_HTTP
#include "mirrors_http.h"
#endif
#ifdef WITH_FTP
#include "mirrors_ftp.h"
#endif

#if ! defined (WITH_HTTP) && ! defined (WITH_FTP)
#error Must compile with at least one of FTP or HTTP
#endif
#if defined (WITH_FTP) && defined (WITH_FTP_MANUAL)
#error Only one of WITH_FTP and WITH_FTP_MANUAL can be defined
#endif

static struct debconfclient *debconf;
static char *protocol = NULL;
static char *country  = NULL;
int show_progress = 1;

/* Are we installing from a CD that includes base system packages? */
static int base_on_cd = 0;

/* Available releases (suite/codename) on the mirror. */
static struct release_t releases[MAXRELEASES];

/*
 * Returns a string on the form "DEBCONF_BASE/protocol/supplied". The
 * calling function is responsible for freeing the string afterwards.
 */
static char *add_protocol(char *string) {
	char *ret;

	assert(protocol != NULL); /* Fetched by choose_protocol */
	asprintf(&ret, DEBCONF_BASE "%s/%s", protocol, string);
	return ret;
}

/*
 * Generates a list, suitable to be passed into debconf, from a
 * NULL-terminated string array.
 */
static char *debconf_list(char *list[]) {
	int len, i, size = 1;
	char *ret = 0;

	for (i = 0; list[i] != NULL; i++) {
		len = strlen(list[i]);
		size += len;
		ret = realloc(ret, size + 2);
		memcpy(ret + size - len - 1, list[i], len);
		if (list[i+1] != NULL) {
			ret[size++ - 1] = ',';
			ret[size++ - 1] = ' ';
		}
		ret[size -1] = '\0';
	}
	return ret;
}

/*
 * Returns the correct mirror list, depending on whether protocol is
 * set to http or ftp. Do NOT free the structure - it is a pointer to
 * the static list in mirrors_protocol.h
 */
static struct mirror_t *mirror_list(void) {
	assert(protocol != NULL);

#ifdef WITH_HTTP
	if (strcasecmp(protocol, "http") == 0)
		return mirrors_http;
#endif
#ifdef WITH_FTP
	if (strcasecmp(protocol, "ftp") == 0)
		return mirrors_ftp;
#endif
	return 0; // should never happen
}

/* Returns an array of hostnames of mirrors in the specified country
 * or using GeoDNS. */
static char **mirrors_in(char *country) {
	static char **ret;
	int i, j, num = 1;
	struct mirror_t *mirrors = mirror_list();

	ret = malloc(num * sizeof(char *));
	for (i = j = 0; mirrors[i].site != NULL; i++) {
		if (j == num - 1) {
			num *= 2;
			ret = realloc(ret, num * sizeof(char*));
		}
		if (! mirrors[i].country ||
		    strcmp(mirrors[i].country, country) == 0)
			ret[j++] = mirrors[i].site;
	}
	ret[j] = NULL;
	return ret;
}

/* returns true if there is a mirror in the specified country */
static inline int has_mirror(char *country) {
	char **mirrors;
	if (strcmp(country, MANUAL_ENTRY) == 0)
		return 1;
	mirrors = mirrors_in(country);
	return (mirrors[0] == NULL) ? 0 : 1;
}

/* Returns true if there is a mirror in the specified country, discounting
 * GeoDNS.
 */
static int has_real_mirror(const char *country) {
	int i;
	struct mirror_t *mirrors = mirror_list();

	for (i = 0; mirrors[i].site != NULL; i++) {
		if (mirrors[i].country &&
		    strcmp(mirrors[i].country, country) == 0)
			return 1;
	}
	return 0;
}

/* Returns the root of the mirror, given the hostname. */
static char *mirror_root(char *mirror) {
	int i;

	struct mirror_t *mirrors = mirror_list();

	for (i = 0; mirrors[i].site != NULL; i++)
		if (strcmp(mirrors[i].site, mirror) == 0)
			return mirrors[i].root;
	return NULL;
}

/*
 * Get the default suite (can be a codename) to use; this is either a
 * preseeded value or a value set at build time.
 */
static char *get_default_suite(void) {
	char *suite = NULL;
	FILE *f = NULL;
	char buf[SUITE_LENGTH];

	debconf_get(debconf, DEBCONF_BASE "suite");
	if (strlen(debconf->value) > 0) {
		/* Use preseeded or previously selected value. */
		suite = strdup(debconf->value);
	} else {
		/* Check for default suite/codename set at build time. */
		f = fopen("/etc/default-release", "r");
		if (f != NULL) {
			if (fgets(buf, SUITE_LENGTH - 1, f)) {
				if (buf[strlen(buf) - 1] == '\n')
					buf[strlen(buf) - 1] = '\0';
				suite = strdup(buf);
			}
			fclose(f);
		}
	}
	return suite;
}

/*
 * Unset most relevant seen flags to allow to correct preseeded values
 * when mirror is bad.
 */
void unset_seen_flags(void) {
	char *hostname, *directory;

	hostname = add_protocol("hostname");
	debconf_fset(debconf, hostname, "seen", "false");
	free(hostname);
	directory = add_protocol("directory");
	debconf_fset(debconf, directory, "seen", "false");
	free(directory);
	debconf_fset(debconf, DEBCONF_BASE "country", "seen", "false");
	debconf_fset(debconf, DEBCONF_BASE "suite", "seen", "false");
}

void log_invalid_release(const char *name, const char *field) {
	di_log(DI_LOG_LEVEL_WARNING,
		"broken mirror: invalid %s in Release file for %s", field, name);
}

static int get_release(struct release_t *release, const char *name);

/*
 * Cross-validate Release file by checking if it can also be accessed using
 * its codename if we got it using a suite and vice versa; if successful,
 * check that it really matches the earlier Release file.
 * Returns false only if an invalid Release file was found.
 */
static int cross_validate_release(struct release_t *release) {
	struct release_t t_release;
	int ret = 1;

	memset(&t_release, 0, sizeof(t_release));

	/* Preset status field to prevent endless recursion. */
	t_release.status = (release->status & (GET_SUITE | GET_CODENAME));

	/* Only one of the two following conditions can trigger. */
	if (release->suite != NULL && !(release->status & GET_SUITE)) {
		/* Cross-validate the suite */
		if (get_release(&t_release, release->suite)) {
			if ((t_release.status & IS_VALID) &&
			    strcmp(t_release.name, release->name) == 0) {
				release->status |= (t_release.status & GET_SUITE);
			} else {
				release->status &= ~IS_VALID;
				ret = 0;
			}
		}
	}
	if (release->name != NULL && !(release->status & GET_CODENAME)) {
		/* Cross-validate the codename (release->name) */
		if (get_release(&t_release, release->name)) {
			if ((t_release.status & IS_VALID) &&
			    strcmp(t_release.suite, release->suite) == 0) {
				release->status |= (t_release.status & GET_CODENAME);
			} else {
				release->status &= ~IS_VALID;
				ret = 0;
			}
		}
	}

	free(t_release.name);
	free(t_release.suite);

	return ret;
}

static int manual_entry;

/*
 * Fetch a Release file, extract its Suite and Codename and check its valitity.
 */
static int get_release(struct release_t *release, const char *name) {
	char *command;
	FILE *f = NULL;
	char *hostname, *directory;
	char line[80];
	char buf[SUITE_LENGTH];

	if (base_on_cd && ! manual_entry) {
		/* We have the base system on the CD, so instead of trying
		 * to contact the mirror (which might take some time to time
		 * out if there's no network connection), let's just assume
		 * that the CD will be sufficient to get a basic system up,
		 * setting codename = suite.  Note that this is an
		 * Ubuntu-specific change since (a) Debian netinst CDs etc.
		 * may not be able to install a complete system from the
		 * network and (b) codename != suite in Debian.
		 *
		 * We only do this for mirrors in our mirror list, since we
		 * assume that those have a good chance of not being typoed.
		 * For manually-entered mirrors, we still do full mirror
		 * validation.
		 */
		di_log(DI_LOG_LEVEL_INFO, "base system installable from CD; skipping mirror check");
		release->name = strdup(name);
		release->suite = strdup(name);
		release->status = IS_VALID | GET_CODENAME;
		return 1;
	}

	hostname = add_protocol("hostname");
	debconf_get(debconf, hostname);
	free(hostname);
	hostname = strdup(debconf->value);
	directory = add_protocol("directory");
	debconf_get(debconf, directory);
	free(directory);
	directory = strdup(debconf->value);

	asprintf(&command, "wget -q %s://%s%s/dists/%s/Release -O - | grep -E '^(Suite|Codename):'",
		 protocol, hostname, directory, name);
	di_log(DI_LOG_LEVEL_DEBUG, "command: %s", command);
	f = popen(command, "r");
	free(command);
	free(hostname);
	free(directory);

	if (f != NULL) {
		while (fgets(line, sizeof(line), f) != NULL) {
			char *value;

			if (line[strlen(line) - 1] == '\n')
				line[strlen(line) - 1] = '\0';
			if ((value = strstr(line, ": ")) != NULL) {
				strncpy(buf, value + 2, SUITE_LENGTH - 1);
				buf[SUITE_LENGTH - 1] = '\0';
				if (strncmp(line, "Codename:", 9) == 0)
					release->name = strdup(buf);
				if (strncmp(line, "Suite:", 6) == 0)
					release->suite = strdup(buf);
			}
		}
		if (release->name != NULL && strcmp(release->name, name) == 0)
			release->status |= IS_VALID | GET_CODENAME;
		if (release->suite != NULL && strcmp(release->suite, name) == 0)
			release->status |= IS_VALID | GET_SUITE;

		if ((release->name != NULL || release->suite != NULL) &&
		    !(release->status & IS_VALID))
			log_invalid_release(name, "Suite or Codename");

		/* Cross-validate the Release file */
		if (release->status & IS_VALID)
			if (! cross_validate_release(release))
				log_invalid_release(name, (release->status & GET_SUITE) ? "Codename" : "Suite");

		/* In case there is no Codename field */
		if ((release->status & IS_VALID) && release->name == NULL)
			release->name = strdup(name);

		// di_log(DI_LOG_LEVEL_DEBUG, "get_release(): %s -> %s:%s (0x%x)",
		//	name, release->suite, release->name, release->status);
	}

	pclose(f);

	if (release->name != NULL) {
		return 1;
	} else {
		free(release->suite);
		return 0;
	}
}

static int find_releases(void) {
	int nbr_suites = sizeof(suites)/SUITE_LENGTH;
	int i, r = 0;
	int bad_mirror = 0, have_default = 0;
	struct release_t release;
	char *default_suite;

	default_suite = get_default_suite();
	if (default_suite == NULL)
		di_log(DI_LOG_LEVEL_ERROR, "no default release specified");

	if (show_progress) {
		debconf_progress_start(debconf, 0, nbr_suites,
				       DEBCONF_BASE "checking_title");
		debconf_progress_info(debconf,
				      DEBCONF_BASE "checking_download");
	}

	/* Initialize releases; also ensures NULL termination of the array */
	memset(&releases, 0, sizeof(releases));

	/* Try to get Release files for all suites. */
	if (! base_on_cd) {
		for (i=0; i < nbr_suites && r < MAXRELEASES; i++) {
			memset(&release, 0, sizeof(release));
			if (get_release(&release, suites[i])) {
				if (release.status & IS_VALID) {
					if (strcmp(release.name, default_suite) == 0 ||
					    strcmp(release.suite, default_suite) == 0) {
						release.status |= IS_DEFAULT;
						have_default = 1;
					}
					/* Only list oldstable if it's the default */
					if (strcmp(suites[i], "oldstable") != 0 ||
					    (release.status & IS_DEFAULT))
						releases[r++] = release;
				} else {
					bad_mirror = 1;
					break;
				}
			}

			if (show_progress)
				debconf_progress_step(debconf, 1);
		}
		if (r == MAXRELEASES)
			di_log(DI_LOG_LEVEL_ERROR, "array overflow: more releases than allowed by MAXRELEASES");
		if (! bad_mirror && r == 0)
			di_log(DI_LOG_LEVEL_INFO, "mirror does not have any suite symlinks");
	}

	/* Try to get Release file using the default "suite". */
	if (! bad_mirror && (base_on_cd || ! have_default)) {
		memset(&release, 0, sizeof(release));
		if (get_release(&release, default_suite)) {
			if (release.status & IS_VALID) {
				release.status |= IS_DEFAULT;
				releases[r++] = release;
				have_default = 1;
			} else {
				bad_mirror = 1;
			}
		} else {
			di_log(DI_LOG_LEVEL_WARNING,
				"mirror does not support the specified release (%s)",
				default_suite);
		}
		if (r == MAXRELEASES)
			di_log(DI_LOG_LEVEL_ERROR, "array overflow: more releases than allowed by MAXRELEASES");
	}

	if (show_progress) {
		debconf_progress_set(debconf, nbr_suites);
		debconf_progress_stop(debconf);
	}

	if (r == 0 || bad_mirror) {
		unset_seen_flags();
		free(default_suite);
		free(release.name);
		free(release.suite);

		debconf_input(debconf, "critical", DEBCONF_BASE "bad");
		if (debconf_go(debconf) == 30)
			exit(10); /* back up to menu */
		else
			return 1; /* back to beginning of questions */
	}

	if (! base_on_cd && ! have_default) {
		unset_seen_flags();

		debconf_subst(debconf, DEBCONF_BASE "no-default",
			"RELEASE", default_suite);
		free(default_suite);

		debconf_input(debconf, "critical", DEBCONF_BASE "no-default");
		if (debconf_go(debconf) == 30) {
			exit(10); /* back up to menu */
		} else {
			debconf_get(debconf, DEBCONF_BASE "no-default");
			if (strcmp(debconf->value, "false"))
				return 1; /* back to beginning of questions */
		}
	} else {
		free(default_suite);
	}

	return 0;
}

/* Try to get translation for suite names */
static char *l10n_suite(const char *name) {
	char *template, *l10n_name;

	asprintf(&template, "%ssuites/%s", DEBCONF_BASE, name);
	if (! debconf_metaget(debconf, template, "description") &&
	    strlen(debconf->value))
		l10n_name = strdup(debconf->value);
	else
		l10n_name = strdup(name);

	free(template);
	return l10n_name;
}

static int check_base_on_cd(void) {
	FILE *fp;
	if ((fp = fopen("/cdrom/.disk/base_installable", "r"))) {
		base_on_cd = 1;
		fclose(fp);
	}
	else if (getenv("OVERRIDE_BASE_INSTALLABLE") != NULL)
		base_on_cd = 1;
	return 0;
}

static int choose_protocol(void) {
#if defined (WITH_HTTP) && (defined (WITH_FTP) || defined (WITH_FTP_MANUAL))
	/* Both are supported, so ask. */
	debconf_subst(debconf, DEBCONF_BASE "protocol", "protocols", "http, ftp");
	debconf_input(debconf, "medium", DEBCONF_BASE "protocol");
#endif
	return 0;
}

static int get_protocol(void) {
#if defined (WITH_HTTP) && (defined (WITH_FTP) || defined (WITH_FTP_MANUAL))
	debconf_get(debconf, DEBCONF_BASE "protocol");
	protocol = strdup(debconf->value);
#else
#ifdef WITH_HTTP
	debconf_set(debconf, DEBCONF_BASE "protocol", "http");
	protocol = "http";
#endif
#ifdef WITH_FTP
	debconf_set(debconf, DEBCONF_BASE "protocol", "ftp");
	protocol = "ftp";
#endif
#endif /* WITH_HTTP && WITH_FTP */
	return 0;
}

static int choose_country(void) {
	if (country)
		free(country);
	country = NULL;

#if defined (WITH_FTP_MANUAL)
	assert(protocol != NULL);
	if (strcasecmp(protocol, "ftp") == 0)
		return 0;
#endif

	debconf_get(debconf, DEBCONF_BASE "country");
	if (! strlen(debconf->value)) {
		/* Not set yet. Seed with a default value. */
		if ((debconf_get(debconf, "debian-installer/country") == 0) &&
		    (debconf->value != NULL) &&
		    has_real_mirror(debconf->value)) {
			country = strdup (debconf->value);
			debconf_set(debconf, DEBCONF_BASE "country", country);
		}
	} else {
		country = strdup(debconf->value);
	}

	/* Ensure 'country' is set to something. */
	if (country == NULL || *country == 0 ||
	    (strcmp(country, MANUAL_ENTRY) != 0 &&
	     !has_real_mirror(country))) {
		free(country);
		country = strdup("GB");
	}

	char *countries;
	countries = add_protocol("countries");
	if (has_mirror(country)) {
		debconf_set(debconf, countries, country);
		debconf_fget(debconf, DEBCONF_BASE "country", "seen");
		debconf_fset(debconf, countries, "seen", debconf->value);
	}
	debconf_input(debconf, base_on_cd ? "medium" : "high", countries);

	free (countries);
	return 0;
}

static int set_country(void) {
	char *countries;

#if defined (WITH_FTP_MANUAL)
	assert(protocol != NULL);
	if (strcasecmp(protocol, "ftp") == 0)
		return 0;
#endif

	countries = add_protocol("countries");
	debconf_get(debconf, countries);
	country = strdup(debconf->value);
	debconf_set(debconf, DEBCONF_BASE "country", country);

	free (countries);
	return 0;
}

static int choose_mirror(void) {
	char *list;
	char *countryarchive;
	int i;

	debconf_get(debconf, DEBCONF_BASE "country");
#ifndef WITH_FTP_MANUAL
	manual_entry = ! strcmp(debconf->value, MANUAL_ENTRY);
#else
	if (! strcasecmp(protocol, "ftp") == 0)
		manual_entry = ! strcmp(debconf->value, MANUAL_ENTRY);
	else
		manual_entry = 1;
#endif

	if (! manual_entry) {
		char *mir = add_protocol("mirror");

		countryarchive=malloc(strlen(country) +
				      strlen(".archive.ubuntu.com") + 1);
		if (debconf_get(debconf, "debian-installer/locale") == 0 &&
		    debconf->value != NULL && strcmp(debconf->value, "C") == 0)
			strcpy(countryarchive, "archive.ubuntu.com");
		else {
			for (i = 0; country[i]; ++i)
				countryarchive[i] = tolower((unsigned char) country[i]);
			strcpy(countryarchive + i, ".archive.ubuntu.com");
		}

		/* Prompt for mirror in selected country. */
		list = debconf_list(mirrors_in(country));
		debconf_subst(debconf, mir, "mirrors", list);
		if ((debconf_get(debconf, mir) == 0 &&
		     strcmp(debconf->value, "CC.archive.ubuntu.com") == 0) ||
		    debconf_fget(debconf, mir, "seen") != 0 ||
		    strcmp(debconf->value, "true") != 0)
			if (mirror_root(countryarchive))
				debconf_set(debconf, mir, countryarchive);
		free(list);
		free(countryarchive);

		debconf_input(debconf, base_on_cd ? "medium" : "high", mir);
		free(mir);
	} else {
		char *host = add_protocol("hostname");
		char *dir = add_protocol("directory");

		/* Manual entry. */
		debconf_input(debconf, "critical", host);
		debconf_input(debconf, "critical", dir);

		free(host);
		free(dir);
	}

	return 0;
}

/* Check basic validity of the selected/entered mirror. */
static int validate_mirror(void) {
	char *mir;
	char *host;
	char *dir;
	int valid = 1;

	mir = add_protocol("mirror");
	host = add_protocol("hostname");
	dir = add_protocol("directory");

	if (! manual_entry) {
		char *mirror;
		char *root;

		/*
		 * Copy information about the selected
		 * mirror into mirror/{protocol}/{hostname,directory},
		 * which is the standard location other
		 * tools can look at.
		 */
		debconf_get(debconf, mir);
		mirror = strdup(debconf->value);
		debconf_set(debconf, host, mirror);
		root = mirror_root(mirror);
		free(mirror);
		if (root == NULL)
			valid = 0;
		else
			debconf_set(debconf, dir, root);
	} else {
		/* check if manually entered mirror is basically ok */
		debconf_get(debconf, host);
		if (debconf->value == NULL || strcmp(debconf->value, "") == 0 ||
		    strchr(debconf->value, '/') != NULL)
			valid = 0;
		debconf_get(debconf, dir);
		if (debconf->value == NULL || strcmp(debconf->value, "") == 0)
			valid = 0;
	}

	free(mir);
	free(host);
	free(dir);

	if (valid) {
		return 0;
	} else {
		unset_seen_flags();
		debconf_input(debconf, "critical", DEBCONF_BASE "bad");
		if (debconf_go(debconf) == 30)
			exit(10); /* back up to menu */
		else
			return 9; /* back up to choose_mirror */
	}
}

static int choose_proxy(void) {
	char *px = add_protocol("proxy");

	/* This is a nasty way to check whether we ought to have a network
	 * connection; if we don't, it isn't worthwhile to ask for a proxy.
	 * We should really change netcfg to write out a flag somewhere.
	 */
	if (debconf_get(debconf, "netcfg/dhcp_options") == 0 && debconf->value != NULL && strncmp(debconf->value, "Do not configure", strlen("Do not configure")) == 0)
		debconf_input(debconf, "low", px);
	else
		debconf_input(debconf, "high", px);

	free(px);
	return 0;
}

static int set_proxy(void) {
	char *px = add_protocol("proxy");
	char *proxy_var;

	asprintf(&proxy_var, "%s_proxy", protocol);

	debconf_get(debconf, px);
	if (debconf->value != NULL && strlen(debconf->value)) {
		if (strstr(debconf->value, "://")) {
			setenv(proxy_var, debconf->value, 1);
		} else {
			char *proxy_value;
			asprintf(&proxy_value, "http://%s", debconf->value);
			setenv(proxy_var, proxy_value, 1);
			free(proxy_value);
		}
	} else {
		unsetenv(proxy_var);
	}

	free(proxy_var);
	free(px);

	return 0;
}

static int choose_suite(void) {
	char *choices_c[MAXRELEASES], *choices[MAXRELEASES], *list;
	int i, ret;
	int have_default = 0;

	ret = find_releases();
	if (ret)
		return ret;

	/* Also ensures NULL termination */
	memset(choices, 0, sizeof(choices));
	memset(choices_c, 0, sizeof(choices_c));

	/* Arrays can never overflow as we've already checked releases */
	for (i=0; releases[i].name != NULL; i++) {
		char *name;

		if (releases[i].status & GET_SUITE)
			name = releases[i].suite;
		else
			name = releases[i].name;

		choices_c[i] = name;
		if (strcmp(name, releases[i].name) != 0)
			asprintf(&choices[i], "%s${!TAB}-${!TAB}%s", releases[i].name,
				 l10n_suite(name));
		else
			choices[i] = l10n_suite(name);
		if (releases[i].status & IS_DEFAULT) {
			debconf_set(debconf, DEBCONF_BASE "suite", name);
			have_default = 1;
		}
	}

	list = debconf_list(choices_c);
	debconf_subst(debconf, DEBCONF_BASE "suite", "CHOICES-C", list);
	free(list);
	list = debconf_list(choices);
	debconf_subst(debconf, DEBCONF_BASE "suite", "CHOICES", list);
	free(list);

	/* If the base system can be installed from CD, don't allow to
	 * select a different suite
	 */
	if (! have_default)
		debconf_fset(debconf, DEBCONF_BASE "suite", "seen", "false");

	return 0;
}

/* Set the codename for the selected suite. */
int set_codename (void) {
	char *suite;
	int i;

	/* If preseed specifies codename, omit the codename check */
	debconf_get(debconf, DEBCONF_BASE "codename");
	if (! strlen(debconf->value)) {
		/* As suite has been determined previously, this should not fail */
		debconf_get(debconf, DEBCONF_BASE "suite");
		if (strlen(debconf->value) > 0) {
			suite = strdup(debconf->value);

			for (i=0; releases[i].name != NULL; i++) {
				if (strcmp(releases[i].name, suite) == 0 ||
				    strcmp(releases[i].suite, suite) == 0) {
					char *codename;

					if (releases[i].status & GET_CODENAME)
						codename = releases[i].name;
					else
						codename = releases[i].suite;
					debconf_set(debconf, DEBCONF_BASE "codename", codename);
					di_log(DI_LOG_LEVEL_INFO,
						"suite/codename set to: %s/%s",
						suite, codename);
					break;
				}
			}

			free(suite);
		}
	}

	return 0;
}

/* Check if the mirror carries the architecture that's being installed. */
int check_arch (void) {
	char *command;
	FILE *f = NULL;
	char *hostname, *directory, *codename = NULL;
	int valid = 0;

	if (base_on_cd && ! manual_entry) {
		/* See comment in get_release. */
		di_log(DI_LOG_LEVEL_INFO, "base system installable from CD; skipping architecture check");
		return 0;
	}

	hostname = add_protocol("hostname");
	debconf_get(debconf, hostname);
	free(hostname);
	hostname = strdup(debconf->value);
	directory = add_protocol("directory");
	debconf_get(debconf, directory);
	free(directory);
	directory = strdup(debconf->value);

	/* As codename has been determined previously, this should not fail */
	debconf_get(debconf, DEBCONF_BASE "codename");
	if (strlen(debconf->value) > 0) {
		codename = strdup(debconf->value);

		asprintf(&command, "wget -q %s://%s%s/dists/%s/main/binary-%s/Release -O - | grep ^Architecture:",
			 protocol, hostname, directory, codename, ARCH_TEXT);
		di_log(DI_LOG_LEVEL_DEBUG, "command: %s", command);
		f = popen(command, "r");
		free(command);

		if (f != NULL) {
			char buf[SUITE_LENGTH];
			if (fgets(buf, SUITE_LENGTH - 1, f))
				if (strlen(buf) > 1)
					valid = 1;
		}
		pclose(f);
	}

	free(hostname);
	free(directory);
	free(codename);

	if (valid) {
		return 0;
	} else {
		unset_seen_flags();
		di_log(DI_LOG_LEVEL_DEBUG, "architecture not supported by selected mirror");
		debconf_input(debconf, "critical", DEBCONF_BASE "noarch");
		if (debconf_go(debconf) == 30)
			exit(10); /* back up to menu */
		else
			return 1; /* back to beginning of questions */
	}
}

int main (int argc, char **argv) {
	int i;
	/* Use a state machine with a function to run in each state */
	int state = 0;
	int (*states[])() = {
		check_base_on_cd,
		choose_protocol,
		get_protocol,
		choose_country,
		set_country,
		choose_mirror,
		validate_mirror,
		choose_proxy,
		set_proxy,
		choose_suite,
		set_codename,
		check_arch,
		NULL,
	};

	if (argc > 1 && strcmp(argv[1], "-n") == 0)
		show_progress = 0;

	debconf = debconfclient_new();
	debconf_capb(debconf, "backup align");
	debconf_version(debconf, 2);

	di_system_init("choose-mirror");

	while (state >= 0 && states[state]) {
		int res;

		res = states[state]();
		if (res == 9) /* back up */
			state--;
		else if (res) /* back up to start */
			state = 0;
		else if (debconf_go(debconf)) /* back up */
			state--;
		else
			state++;
	}

	for (i=0; releases[i].name != NULL; i++) {
		free(releases[i].name);
		free(releases[i].suite);
	}

	return (state >= 0) ? 0 : 10; /* backed all the way out */
}
