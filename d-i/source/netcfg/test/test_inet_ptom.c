#include "srunner.h"
#include "netcfg.h"

START_TEST(test_inet_ptom_v4_24)
{
	unsigned int masklen;
	
	inet_ptom(AF_INET, "255.255.255.0", &masklen);
	
	fail_unless (24 == masklen, "Expected masklen == 24, masklen was %i", masklen);
}
END_TEST

START_TEST(test_inet_ptom_v4_22)
{
	unsigned int masklen;
	
	inet_ptom(AF_INET, "255.255.252.0", &masklen);
	
	fail_unless (22 == masklen, "Expected masklen == 22, masklen was %i", masklen);
}
END_TEST

START_TEST(test_inet_ptom_v6_64)
{
	unsigned int masklen;
	
	inet_ptom(AF_INET6, "ffff:ffff:ffff:ffff::", &masklen);
	
	fail_unless (64 == masklen, "Expected masklen == 64, masklen was %i", masklen);
}
END_TEST

START_TEST(test_inet_ptom_v6_60)
{
	unsigned int masklen;
	
	inet_ptom(AF_INET6, "ffff:ffff:ffff:fff0::", &masklen);
	
	fail_unless (60 == masklen, "Expected masklen == 60, masklen was %i", masklen);
}
END_TEST

START_TEST(test_inet_ptom_v6_60_with_scraps)
{
	unsigned int masklen;
	
	/* This is an address with multiple separate 32 bit integers which all
	 * have 1s in MSB, but the mask should still only be 60 bits.  I also
	 * know this is an illegal netmask.
	 */
	inet_ptom(AF_INET6, "ffff:ffff:ffff:fff0:ffff::", &masklen);
	
	fail_unless (60 == masklen, "Expected masklen == 60, masklen was %i", masklen);
}
END_TEST

Suite *test_inet_ptom_suite (void)
{
	Suite *s = suite_create ("inet_ptom");
	
	TCase *tc = tcase_create ("inet_ptom");
	tcase_add_test (tc, test_inet_ptom_v4_24);
	tcase_add_test (tc, test_inet_ptom_v4_22);
	tcase_add_test (tc, test_inet_ptom_v6_64);
	tcase_add_test (tc, test_inet_ptom_v6_60);
	tcase_add_test (tc, test_inet_ptom_v6_60_with_scraps);
	
	suite_add_tcase (s, tc);
	
	return s;
}
