#include "srunner.h"
#include "netcfg.h"

START_TEST(test_parse_standalone_v4_address)
{
	struct netcfg_interface interface;
	netcfg_interface_init(&interface);
	int rv;

	interface.masklen = 7;
	rv = netcfg_parse_cidr_address("192.0.2.12", &interface);

	fail_unless (rv,
	             "parsing failed, rv = %i", rv);
	
	fail_unless (interface.masklen == 0,
	             "masklen was %i, should have been 0",
	             interface.masklen);

	fail_unless (strcmp("192.0.2.12", interface.ipaddress) == 0,
	             "IP address was %s, should have been 192.10.2.12",
	             interface.ipaddress);

	fail_unless (interface.address_family == AF_INET,
	             "Address family should have been AF_INET");
}
END_TEST

START_TEST(test_parse_cidr_v4_address)
{
	struct netcfg_interface interface;
	netcfg_interface_init(&interface);
	int rv;

	interface.masklen = 7;
	rv = netcfg_parse_cidr_address("192.0.2.12/24", &interface);

	fail_unless (rv,
	             "parsing failed, rv = %i", rv);
	
	fail_unless (interface.masklen == 24,
	             "masklen was %i, should have been 24",
	             interface.masklen);

	fail_unless (strcmp("192.0.2.12", interface.ipaddress) == 0,
	             "IP address was %s, should have been 192.10.2.12",
	             interface.ipaddress);

	fail_unless (interface.address_family == AF_INET,
	             "Address family should have been AF_INET");
}
END_TEST

START_TEST(test_parse_standalone_v6_address)
{
	struct netcfg_interface interface;
	netcfg_interface_init(&interface);
	int rv;

	interface.masklen = 7;
	rv = netcfg_parse_cidr_address("fd80:0:0::2", &interface);

	fail_unless (rv,
	             "parsing failed, rv = %i", rv);
	
	fail_unless (interface.masklen == 0,
	             "masklen was %i, should have been 0",
	             interface.masklen);

	fail_unless (strcmp("fd80::2", interface.ipaddress) == 0,
	             "IP address was %s, should have been fd80::2",
	             interface.ipaddress);

	fail_unless (interface.address_family == AF_INET6,
	             "Address family should have been AF_INET6");
}
END_TEST

START_TEST(test_parse_cidr_v6_address)
{
	struct netcfg_interface interface;
	netcfg_interface_init(&interface);
	int rv;

	interface.masklen = 7;
	rv = netcfg_parse_cidr_address("fd80:0::4/64", &interface);

	fail_unless (rv,
	             "parsing failed, rv = %i", rv);
	
	fail_unless (interface.masklen == 64,
	             "masklen was %i, should have been 26",
	             interface.masklen);

	fail_unless (strcmp("fd80::4", interface.ipaddress) == 0,
	             "IP address was %s, should have been fd80::4",
	             interface.ipaddress);

	fail_unless (interface.address_family == AF_INET6,
	             "Address family should have been AF_INET6");
}
END_TEST

Suite *test_netcfg_parse_cidr_address_suite (void)
{
	Suite *s = suite_create ("netcfg_parse_cidr_address");
	
	TCase *tc = tcase_create ("netcfg_parse_cidr_address");
	tcase_add_test (tc, test_parse_standalone_v4_address);
	tcase_add_test (tc, test_parse_cidr_v4_address);
	tcase_add_test (tc, test_parse_standalone_v6_address);
	tcase_add_test (tc, test_parse_cidr_v6_address);
	
	suite_add_tcase (s, tc);
	
	return s;
}
