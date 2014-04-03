# List of test files
TESTS = test/test_inet_mton.o						\
        test/test_inet_ptom.o						\
        test/test_netcfg_parse_cidr_address.o				\
        test/test_netcfg_network_address.o				\
        test/test_netcfg_gateway_reachable.o				\
        test/test_nc_v6_interface_configured.o

# List of other objects that we need to pull in to make the tests work
OBJECTS = netcfg-common.o wireless.o ethtool-lite.o ipv6.o write_interface.o

test/run: $(TESTS) $(OBJECTS) test/srunner.o
	$(CC) -o $@ $^ $(LDOPTS) -lcheck -lm -lpthread -lrt

test: test/run
	@echo "----------------------------------------"
	@echo
	@echo
	@test/run

.PHONY: test
