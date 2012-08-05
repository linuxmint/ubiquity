/*
 * Copyright (c) 2009 Frans Pop <fjp@debian.org>
 * Licence: GPL version 2 or later
 */

/*
 * set-date-epoch.c:
 * Set the system date to the epoch if the current date is before the epoch.
 */

#include <sys/time.h>
#include <err.h>
#include <time.h>
#include <stdio.h>

#define EPOCH	70
#define DEBUG	0

int
main(int argc, char **argv)
{
	struct timeval tp;
	struct timezone tzp;
	struct tm *now;

	if (gettimeofday(&tp, &tzp) == -1)
		err(1, "Failed to get time of day");
	now = gmtime(&tp.tv_sec);

#if DEBUG
	printf("The current year is %i.\n", 1900 + now->tm_year);
#endif

	if (now->tm_year < EPOCH) {
		printf("System date is before 1-1-1970; correcting...\n");
		tp.tv_sec = 0;
		tp.tv_usec = 0;
		if (settimeofday(&tp, NULL) == -1)
			err(1, "Could not set time of day");
		printf("System date has been set to 1-1-1970.\n");
	}

	return 0;
}
