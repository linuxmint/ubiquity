#include "srunner.h"
#include "netcfg.h"

START_TEST(test_inet_mton_v4_24)
{
	struct in_addr addr;
	uint8_t expected[] = { 0xff, 0xff, 0xff, 0 };
	
	inet_mton(AF_INET, 24, &addr);
	
	fail_unless (memcmp(expected, &(addr.s_addr), 4) == 0,
	             "Mask address wasn't 24 bits");
}
END_TEST

START_TEST(test_inet_mton_v4_22)
{
	struct in_addr addr;
	uint8_t expected[] = { 0xff, 0xff, 0xfc, 0 };
	
	inet_mton(AF_INET, 22, &addr);
	
	fail_unless (memcmp(expected, &(addr.s_addr), 4) == 0,
	             "Mask address wasn't 22 bits");
}
END_TEST

START_TEST(test_inet_mton_v6_64)
{
	struct in6_addr addr;
	uint8_t expected[] = { 0xff, 0xff, 0xff, 0xff,
	                       0xff, 0xff, 0xff, 0xff,
	                       0, 0, 0, 0, 0, 0, 0, 0 };
	
	inet_mton(AF_INET6, 64, &addr);
	
	fail_unless (memcmp(expected, addr.s6_addr, 16) == 0,
	             "Mask address wasn't 64 bits");
}
END_TEST

START_TEST(test_inet_mton_v6_60)
{
	struct in6_addr addr;
	uint8_t expected[] = { 0xff, 0xff, 0xff, 0xff,
	                       0xff, 0xff, 0xff, 0xf0,
	                       0, 0, 0, 0, 0, 0, 0, 0 };
	
	inet_mton(AF_INET6, 60, &addr);

	fail_unless (memcmp(expected, addr.s6_addr, 16) == 0,
	             "Mask address wasn't 60 bits");
}
END_TEST

Suite *test_inet_mton_suite (void)
{
	Suite *s = suite_create ("inet_mton");
	
	TCase *tc = tcase_create ("inet_mton");
	tcase_add_test (tc, test_inet_mton_v4_24);
	tcase_add_test (tc, test_inet_mton_v4_22);
	tcase_add_test (tc, test_inet_mton_v6_64);
	tcase_add_test (tc, test_inet_mton_v6_60);
	
	suite_add_tcase (s, tc);
	
	return s;
}
