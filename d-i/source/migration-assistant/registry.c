/* The data structures for the Windows NT registry and some of the code within
 * this source file was written by Aaron D. Brooks for the BeeHive project
 * (http://sourceforge.net/project/?group_id=1987) and licensed under the GPL
 * v2.
 *
 * UTF-16 to UTF-8 conversion taken from VLC.
 */

#include <stdlib.h>
#include <stdio.h>
#include <fcntl.h>
#include <string.h>
#include <errno.h>
#include "registry.h"

/* MSB (big endian)/LSB (little endian) conversions - network order is always
 * MSB, and should be used for both network communications and files. Note that
 * byte orders other than little and big endians are not supported, but only
 * the VAX seems to have such exotic properties. */
static inline uint16_t U16_AT( void const * _p )
{
    uint8_t * p = (uint8_t *)_p;
    return ( ((uint16_t)p[0] << 8) | p[1] );
}

/**
 * UTF16toUTF8: converts UTF-16 (host byte order) to UTF-8
 *
 * @param src UTF-16 bytes sequence, aligned on a 16-bits boundary
 * @param len number of uint16_t to convert
 */
static char *
UTF16toUTF8( const uint16_t *in, size_t len, size_t *newlen )
{
    char *res, *out;

    /* allocate memory */
    out = res = (char *)malloc( 3 * len );
    if( res == NULL )
        return NULL;

    while( len > 0 )
    {
        uint32_t uv = *in;

        in++;
        len--;

        if( uv < 0x80 )
        {
            *out++ = uv;
            continue;
        }
        if( uv < 0x800 )
        {
            *out++ = (( uv >>  6)         | 0xc0);
            *out++ = (( uv        & 0x3f) | 0x80);
            continue;
        }
        if( (uv >= 0xd800) && (uv < 0xdbff) )
        {   /* surrogates */
            uint16_t low = U16_AT( in );
            in++;
            len--;

            if( (low < 0xdc00) || (low >= 0xdfff) )
            {
                *out++ = '?'; /* Malformed surrogate */
                continue;
            }
            else
                uv = ((uv - 0xd800) << 10) + (low - 0xdc00) + 0x10000;
        }
        if( uv < 0x10000 )
        {
            *out++ = (( uv >> 12)         | 0xe0);
            *out++ = (((uv >>  6) & 0x3f) | 0x80);
            *out++ = (( uv        & 0x3f) | 0x80);
            continue;
        }
        else
        {
            *out++ = (( uv >> 18)         | 0xf0);
            *out++ = (((uv >> 12) & 0x3f) | 0x80);
            *out++ = (((uv >>  6) & 0x3f) | 0x80);
            *out++ = (( uv        & 0x3f) | 0x80);
            continue;
        }
    }
    len = out - res;
    res = realloc( res, len );
    if( newlen != NULL )
        *newlen = len;
    return res;
}


/**
 * FromUTF16(): converts an UTF-16 string to UTF-8.
 *
 * @param src UTF-16 bytes sequence, aligned on a 16-bits boundary.
 *
 * @return the result of the conversion (must be free()'d),
 * or NULL in case of error.
 */
char *FromUTF16( const uint16_t *src )
{
    const uint16_t *in;
    size_t len;

    /* determine the size of the string */
    for( len = 1, in = src; *in; len++ )
        in++;

    return UTF16toUTF8( src, len, NULL );
}

char* findkey(const char* location, const char* path)
{

    FILE *hive;
    int numread;
    REGF myregf;
    char* hbinptr;

    char* ret = NULL;
    // FIXME
    char* arr;
    arr = strdup(path);

    hive = fopen(location,"r");
    if(hive)
    {		      
	    numread = fread(&myregf,sizeof(char),sizeof(REGF),hive);

	    char* key;
	    if((key = strrchr(arr, '\\')) != NULL){
		*key++ = '\0';
	    }

	    hbinptr = (char*)malloc(myregf.hivesize);
	    if(hbinptr)
	    {
		    numread = fread(hbinptr,sizeof(char),myregf.hivesize,hive);
		    
		    NK* back = getkey(hbinptr,(NK*)&(hbinptr[myregf.firstkey]), &arr);
		    if(back != NULL) {
			ret = printk(hbinptr, back, key);
		    }
		    free(hbinptr);
		//    if(key)
		//	free(key);
	    }

    } else {
	fprintf(stderr, "Unable to open the registry file at '%s'\n%d: %s\n",
	    location, errno, strerror(errno));
	return NULL;
    }
    fclose(hive);

    if(ret)
	return ret;
    else
	return NULL;
}
char* expand_string(const char *string) {
    if(strcmp(string, "%SystemDrive%") == 0) {
        // FIXME:
        return strdup("C:");
    } else {
        fprintf(stderr, "Unable to expand '%s'.\n", string);
        exit(EXIT_FAILURE);
    }
}
char* printk(char* base, NK* thisnk, char* key) {
    int i;
    int* valptr;
	if(thisnk->numvalues > 0)
	{
		valptr=(int*) &(base[thisnk->myvallist]);
		for(i=1; i<thisnk->numvalues+1; i++)
		{
			if(valptr[i]>0)
			{
			    	VK* thisvk = (VK*) &(base[valptr[i]]);
				char* szname;
				//int vksize=sizeof(VK)+thisvk->namesize;

				szname = (char*) malloc (thisvk->namesize+1);
				strncpy(szname,(char*)(thisvk+1),thisvk->namesize+1);
				szname[thisvk->namesize]= 0;
				if(strcmp(szname,key) == 0){
				    if(thisvk->flag && 0x0000000000000001){
					    // FIXME: Handle REG_EXPAND_SZ
                                            // better
                                            if (thisvk->valtype == REG_SZ || thisvk->valtype == REG_EXPAND_SZ){
						char* tmp = NULL;
                                                // Emtpy string.
                                                if((base+4+(thisvk->mydata))[0] == 0)
                                                    return NULL;
						
						// Convert to UTF-8.
						tmp = FromUTF16((uint16_t*)(base+4+(thisvk->mydata)));

                                                if(thisvk->valtype == REG_EXPAND_SZ) {
                                                    char *start, *end;
                                                    int startc = 0;
                                                    int endc = 0;
                                                    start = tmp;
                                                    while(*start != '\0') {
                                                        if(*start == '%') {
                                                            end = start+1;
                                                            endc = startc+1;
                                                            while(*end != '%') {
                                                                if(*end == '\0') {
                                                                    fprintf(stderr, "Unmatched '%%' in %s.\n", tmp);
                                                                    exit(EXIT_FAILURE);
                                                                }
                                                                end++;
                                                                endc++;
                                                            }
                                                            //printf("endc: %d end: %s\n", endc, end);
                                                            //printf("startc: %d start: %s\n", startc, start);
                                                            char* toexpand = malloc((endc-startc+1)+1);
                                                            memcpy(toexpand, start, (endc-startc+1));
                                                            toexpand[endc-startc+1] = '\0';
                                                            //printf("toexpand: %s\n", toexpand);
                                                            char* expanded = expand_string(toexpand);
                                                            free(toexpand);
                                                            //printf("expanded: %s\n", expanded);
                                                            int linelen = strlen(tmp) -
                                                                (endc-startc+1) + strlen(expanded) + 1;
                                                            //printf("linelen: %d\n", linelen);
                                                            char* newtmp = calloc(linelen, 1);
                                                            strncpy(newtmp, tmp, startc);
                                                            strcat(newtmp, expanded);
                                                            strcat(newtmp, end+1);
                                                            //printf("newtmp: %s\n", newtmp);
                                                            free(tmp);
                                                            free(expanded);
                                                            tmp = newtmp;
                                                            endc = 0;
                                                            startc = 0;
                                                            start=tmp;
                                                        } else {
                                                            start++;
                                                            startc++;
                                                        }
                                                    }
                                                }
						return tmp;

					    } else if(thisvk->valtype == REG_DWORD) {
                                                char* tmp;
                                                tmp = malloc(8);
                                                sprintf(tmp, "%d",thisvk->mydata);
                                                return tmp;
                                            }
				    }
				}
				free(szname);

			}
		}
	}
	return NULL;
}

NK* getkey(char* base, NK* thisnk, char** path) {
    NK* tmp;
    LF* lfrec = (LF*) &(base[thisnk->mylfrec]);
    HASH* hasharray = (HASH*) lfrec +1;
    int i;
    char* element;

    if((element = str_token(path, "\\")) != NULL) {

            if(thisnk->numchildren > 0) {
                for(i=0; i<thisnk->numchildren; i++) {
                        tmp = (NK*)&(base[(hasharray+i)->nkrec]);

                        char* szname;
                        szname = (char*) malloc (tmp->namesize+1);
                        strncpy(szname,(char*)(tmp+1),tmp->namesize+1);
                        szname[tmp->namesize]= 0;

                        if(strcmp(szname,element) == 0){
                            thisnk = getkey(base, tmp, path);
                            free(szname);
                            return thisnk;
                        }
                        free(szname);
                }
                return NULL;

            }

    }
    return thisnk;
}

/* Reentrant strtok, taken from a Usenet post:
 * http://groups.google.com/group/comp.lang.c/msg/9e92ba098baa55ac?dmode=source
 */
char *str_token( char **string, char *delimiters ) {

    char *rv, *wrk, empty[] = "";

    /******************************************************************/
    /* Beware the NULL pointer !                                      */
    /******************************************************************/

    if ( delimiters == NULL )
        delimiters = empty;

    if ( string == NULL || *string == NULL || **string == '\0' )
        rv = NULL;

    /******************************************************************/
    /* If there are no delimiters the string is the token.            */
    /******************************************************************/

    else if ( ( wrk = strpbrk( *string, delimiters ) ) == NULL ) {
        rv = *string;
        *string += strlen( rv );
    }

    /******************************************************************/
    /* Skip past any delimiters at the beginning of the string.       */
    /******************************************************************/

    else if ( wrk == *string ) {
        *string += strspn( wrk, delimiters );
        rv = str_token( string, delimiters );
    }

    /******************************************************************/
    /* Got a token! Null terminate it and prep for the next call.     */
    /******************************************************************/

    else {
        *wrk++ = '\0';
        rv = *string;
        *string = wrk + strspn( wrk, delimiters );
    }
    return rv;

}
// vim:ai:et:sts=4:tw=80:sw=4:
