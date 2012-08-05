#include "srunner.h"
#include "netcfg.h"

START_TEST(test_netcfg_gateway_reachable_v4_24)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	
	strcpy(iface.ipaddress, "192.168.1.25");
	strcpy(iface.gateway, "192.168.1.254");
	iface.masklen = 24;
	iface.address_family = AF_INET;
	
	fail_unless (netcfg_gateway_reachable(&iface),
	             "Gateway erroneously unreachable");

	strcpy(iface.gateway, "192.168.2.254");
	
	fail_if (netcfg_gateway_reachable(&iface),
	         "Gateway erroneously reachable");
}
END_TEST

START_TEST(test_netcfg_gateway_reachable_v4_22)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	
	strcpy(iface.ipaddress, "192.168.1.25");
	strcpy(iface.gateway, "192.168.3.254");
	iface.masklen = 22;
	iface.address_family = AF_INET;
	
	fail_unless (netcfg_gateway_reachable(&iface),
	             "Gateway erroneously unreachable");

	strcpy(iface.gateway, "192.168.4.254");
	
	fail_if (netcfg_gateway_reachable(&iface),
	         "Gateway erroneously reachable");
}
END_TEST

START_TEST(test_netcfg_gateway_reachable_v6_64)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	
	strcpy(iface.ipaddress, "2001:3:5:7::71");
	strcpy(iface.gateway, "2001:3:5:7::1");
	iface.masklen = 64;
	iface.address_family = AF_INET6;
	
	fail_unless (netcfg_gateway_reachable(&iface),
	             "Gateway erroneously unreachable");

	strcpy(iface.gateway, "2001:3:5::1");
	
	fail_if (netcfg_gateway_reachable(&iface),
	         "Gateway erroneously reachable");
}
END_TEST

START_TEST(test_netcfg_gateway_reachable_v6_48)
{
	struct netcfg_interface iface;
	netcfg_interface_init(&iface);
	
	strcpy(iface.ipaddress, "2001:3:5:7::71");
	strcpy(iface.gateway, "2001:3:5::1");
	iface.masklen = 48;
	iface.address_family = AF_INET6;
	
	fail_unless (netcfg_gateway_reachable(&iface),
	             "Gateway erroneously unreachable");

	strcpy(iface.gateway, "2001:3:6::1");
	
	fail_if (netcfg_gateway_reachable(&iface),
	         "Gateway erroneously reachable");
}
END_TEST

Suite *test_netcfg_gateway_reachable_suite (void)
{
	Suite *s = suite_create ("netcfg_gateway_reachable");
	
	TCase *tc = tcase_create ("netcfg_gateway_reachable");
	tcase_add_test (tc, test_netcfg_gateway_reachable_v4_24);
	tcase_add_test (tc, test_netcfg_gateway_reachable_v4_22);
	tcase_add_test (tc, test_netcfg_gateway_reachable_v6_64);
	tcase_add_test (tc, test_netcfg_gateway_reachable_v6_48);
	
	suite_add_tcase (s, tc);
	
	return s;
}
