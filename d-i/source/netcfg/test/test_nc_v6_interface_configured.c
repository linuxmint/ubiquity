#include "srunner.h"
#include "netcfg.h"

#include <stdlib.h>

START_TEST(test_nc_v6_interface_configured_simple)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	int rv;
	
	iface.name = "eth0";
	
	srunner_mock_path(__func__);
	
	rv = nc_v6_interface_configured(&iface, 0);
	
	fail_unless(rv == 1, "Didn't find SLAAC");
	
	srunner_reset_path();
}
END_TEST

Suite *test_nc_v6_interface_configured_suite (void)
{
	Suite *s = suite_create ("nc_v6_interface_configured");
	
	TCase *tc = tcase_create ("nc_v6_interface_configured");
	tcase_add_test (tc, test_nc_v6_interface_configured_simple);
	
	suite_add_tcase (s, tc);
	
	return s;
}
