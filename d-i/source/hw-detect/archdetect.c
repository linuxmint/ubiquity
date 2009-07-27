#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <debian-installer/system/subarch.h>

int main(int argc, char *argv[])
{
        const char *subarch;

	if (!(subarch = di_system_subarch_analyze()))
 		return EXIT_FAILURE;

	printf("%s/%s\n", CPU_TEXT, subarch);

	return 0;
}
