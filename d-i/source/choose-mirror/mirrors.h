/*
 * Data structure for representing http, https, and ftp mirror information.
 * Contains essentially the same information as Mirrors.masterlist,
 * but only as much information as is necessary.
 */
struct mirror_t {
	char *site;
	char *country; /* NULL for GeoDNS */
	char *root;
};

#define DEBCONF_BASE "mirror/"

/*
 * The string defined below must match the string used in the templates
 * (http, https, and ftp) for this option.
 */
#define MANUAL_ENTRY "manual"

#define SUITE_LENGTH 32

/* Stack of suites */
static const char suites[][SUITE_LENGTH] = {
	/* higher preference */
	"trusty",
	/* lower preference */
};

/*
 * Allow for two more releases than the number of suites:
 * - all suites
 * - default release (if not in suites)
 * - NULL list terminator
 */
#define MAXRELEASES (sizeof(suites)/SUITE_LENGTH + 2)

/*
 * Data structure containing information on releases supported by a mirror
 */
struct release_t {
	char *name;
	char *suite;
	int status;
};

/* Values for status field in release_t */
#define IS_VALID	0x1
#define IS_DEFAULT	0x2
#define GET_SUITE	0x4
#define GET_CODENAME	0x8
