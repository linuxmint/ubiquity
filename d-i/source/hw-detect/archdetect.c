#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <debian-installer/macros.h>
#include <debian-installer/system/subarch.h>

#if DI_GNUC_PREREQ(2,4)
#  define ATTRIBUTE_UNUSED __attribute__((__unused__))
#else
#  define ATTRIBUTE_UNUSED
#endif

int main(int argc ATTRIBUTE_UNUSED, char *argv[] ATTRIBUTE_UNUSED)
{
        const char *subarch;

	if (!(subarch = di_system_subarch_analyze()))
 		return EXIT_FAILURE;

	printf("%s/%s\n", CPU_TEXT, subarch);

	return 0;
}
