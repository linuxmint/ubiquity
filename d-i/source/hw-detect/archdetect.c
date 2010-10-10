#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>

#include <debian-installer/system/subarch.h>

static struct option long_options[] =
{
	{"guess", 0, 0, 0},
	{0, 0, 0, 0}
};

int main(int argc, char *argv[])
{
        const char *subarch;
        int guess = 0;

	while (1)
	{
		int option_index = 0;
		int c;

		c = getopt_long (argc, argv, "g", long_options,
				 &option_index);
		if (c == -1) break;

		switch (c)
		{
			case 'g':
				guess = 1;
				break;
			default:
				continue;
		}
	}

	if (guess)
		subarch = di_system_subarch_analyze_guess();
	else
		subarch = di_system_subarch_analyze();
	if (!subarch)
 		return EXIT_FAILURE;

	printf("%s/%s\n", CPU_TEXT, subarch);

	return 0;
}
