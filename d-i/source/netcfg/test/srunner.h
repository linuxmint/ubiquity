#include <check.h>

Suite *test_inet_mton_suite (void);
Suite *test_inet_ptom_suite (void);
Suite *test_netcfg_parse_cidr_address_suite (void);
Suite *test_netcfg_network_address_suite (void);
Suite *test_netcfg_gateway_reachable_suite (void);
Suite *test_nc_v6_interface_configured_suite (void);

/* Helper functions */

/* Change the system path so that the given directory,
 * relative to $PROJECT_ROOT/test/mock_paths, is the first element.  This
 * allows you to insert your own mock binaries to act in a consistent way
 * for you to test against.
 */
void srunner_mock_path(const char *testcase);

/* You must run this at the end of your test case after calling
 * srunner_mock_path, to reset the path back to normal.
 */
void srunner_reset_path();
