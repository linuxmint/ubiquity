#define _GNU_SOURCE
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

char *
xasprintf(const char *format, ...)
{
    va_list args;
    char *result;

    va_start(args, format);
    if (vasprintf(&result, format, args) < 0) {
        if (errno == ENOMEM) {
            fputs("Out of memory!\n", stderr);
            abort();
        }
        return NULL;
    }

    return result;
}
