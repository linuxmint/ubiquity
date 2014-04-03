#include <limits.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdio.h>

#include "test/srunner.h"

static char *test_run_root;
static char *original_path;

int main(int argc, char *argv[])
{
	int number_failed;
	SRunner *sr;
	char *buf, *p;
	(void)argc;

	/* Put the absolute directory in which the binary resides into
	 * test_run_root, so that srunner_mock_path can find it again.
	 */
	if (argv[0][0] == '/') {
		buf = argv[0];
	} else {
		char *cwd = getcwd(NULL, 0);
		buf = malloc(strlen(cwd) + 1 + strlen(argv[0]) + 1);
		strcpy(buf, cwd);
		strcat(buf, "/");
		strcat(buf, argv[0]);
		free(cwd);
	}
	test_run_root = realpath(buf, NULL);
	p = strrchr(test_run_root, '/');
	*p = '\0';

	sr = srunner_create(test_inet_mton_suite());
	/* Test suite list starts here */
	srunner_add_suite(sr, test_inet_ptom_suite());
	srunner_add_suite(sr, test_netcfg_parse_cidr_address_suite());
	srunner_add_suite(sr, test_netcfg_network_address_suite());
	srunner_add_suite(sr, test_netcfg_gateway_reachable_suite());
	srunner_add_suite(sr, test_nc_v6_interface_configured_suite());
	
	srunner_run_all (sr, CK_NORMAL);
	number_failed = srunner_ntests_failed (sr);
	srunner_free (sr);
	return (number_failed == 0) ? 0 : 1;
}

void srunner_mock_path(const char *testcase)
{
	char *new_path;
	unsigned int new_path_len;
	
	original_path = strdup(getenv("PATH"));
	
	new_path_len = strlen(test_run_root)
	               + 12 /* /mock_paths/ */
	               + strlen(testcase) + 1 /* : */
	               + strlen(original_path) + 1 /* \0 */;
	
	new_path = malloc(new_path_len);
	
	snprintf(new_path, new_path_len, "%s/mock_paths/%s:%s", test_run_root, testcase, original_path);
	
	setenv("PATH", new_path, 1);
	
	free(new_path);
}

void srunner_reset_path()
{
	setenv("PATH", original_path, 1);
	free(original_path);
}
