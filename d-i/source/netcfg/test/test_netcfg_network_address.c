#include "srunner.h"
#include "netcfg.h"

START_TEST(test_netcfg_network_address_v4_24)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	char network[NETCFG_ADDRSTRLEN];
	
	strcpy(iface.ipaddress, "192.168.1.25");
	iface.masklen = 24;
	iface.address_family = AF_INET;
	
	netcfg_network_address(&iface, network);
	
	fail_unless (strcmp("192.168.1.0", network) == 0,
	             "Network address wrong; expected 192.168.1.0, got %s");
}
END_TEST

START_TEST(test_netcfg_network_address_v4_22)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	char network[NETCFG_ADDRSTRLEN];
	
	strcpy(iface.ipaddress, "192.168.17.25");
	iface.masklen = 22;
	iface.address_family = AF_INET;
	
	netcfg_network_address(&iface, network);
	
	fail_unless (strcmp("192.168.16.0", network) == 0,
	             "Network address wrong; expected 192.168.16.0, got %s");
}
END_TEST

START_TEST(test_netcfg_network_address_v6_64)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	char network[NETCFG_ADDRSTRLEN];
	
	strcpy(iface.ipaddress, "2001:3:5:7::79");
	iface.masklen = 64;
	iface.address_family = AF_INET6;
	
	netcfg_network_address(&iface, network);
	
	fail_unless (strcmp("2001:3:5:7::", network) == 0,
	             "Network address wrong; expected 2001:3:5:7::, got %s");
}
END_TEST

START_TEST(test_netcfg_network_address_v6_48)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	char network[NETCFG_ADDRSTRLEN];
	
	strcpy(iface.ipaddress, "2001:3:5:7::79");
	iface.masklen = 48;
	iface.address_family = AF_INET6;
	
	netcfg_network_address(&iface, network);
	
	fail_unless (strcmp("2001:3:5::", network) == 0,
	             "Network address wrong; expected 2001:3:5::, got %s");
}
END_TEST

Suite *test_netcfg_network_address_suite (void)
{
	Suite *s = suite_create ("netcfg_network_address");
	
	TCase *tc = tcase_create ("netcfg_network_address");
	tcase_add_test (tc, test_netcfg_network_address_v4_24);
	tcase_add_test (tc, test_netcfg_network_address_v4_22);
	tcase_add_test (tc, test_netcfg_network_address_v6_64);
	tcase_add_test (tc, test_netcfg_network_address_v6_48);
	
	suite_add_tcase (s, tc);
	
	return s;
}
