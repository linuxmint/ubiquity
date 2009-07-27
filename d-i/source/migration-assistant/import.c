#include <stdio.h>
#include <string.h>
#include <getopt.h>
#include <stdlib.h>

// For dropping to user
#include <sys/types.h>
#include <pwd.h>
#include <unistd.h>

// For directory manipulation
#include <dirent.h>
#include <fcntl.h>

// For umask
#include <sys/stat.h>

#include "utils.h"
#include "gaim-import.h"
#include "firefox-import.h"
#include "windows-import.h"
#include "firefox-import.h"
#include "evolution-import.h"

void usage(char** argv) {
    printf("USAGE: %s --ostype=TYPE --fromuser=USER --frompath=PATH"
	    " --touser=USER --topath=PATH --target=TARGET\n\n",
	    argv[0]);
    exit(EXIT_FAILURE);
}
int main(int argc, char** argv) {

    void (*target)();

    static struct option long_options[] = {
	{ "ostype", required_argument, NULL, 'o' },
	{ "fromuser", required_argument, NULL, 'f' },
	{ "frompath", required_argument, NULL, 'l' },
	{ "touser", required_argument, NULL, 't' },
	{ "topath", required_argument, NULL, 'p' },
	{ "target", required_argument, NULL, 'a' },
	{ NULL, 0, NULL, 0 }
    };

    while(1) {
	int c = getopt_long(argc, argv, "", long_options, NULL);
	if(c == -1) break;
	switch(c) {
	    case 'o' :
		if(strcmp(optarg, "linux") == 0) os_type = LINUX;
		else if(strcmp(optarg, "windowsxp") == 0)
		    os_type = WINDOWSXP;
		else
		    usage(argv);
		break;
	    case 'f' :
		from_user = strdup(optarg);
		break;
	    case 'l' :
		from_location = strdup(optarg);
		break;
	    case 't' :
		to_user = strdup(optarg);
		break;
	    case 'p' :
		to_location = strdup(optarg);
		break;
	    case 'a' :
		// FIXME: Clearly we need to do something about this mess.
		if(strcmp(optarg,"yahoo") == 0)
		    target = gaim_import_yahoo;
		else if(strcmp(optarg,"aimtriton") == 0)
		    target = gaim_import_aimtriton;
		else if(strcmp(optarg,"pidgin") == 0)
		    target = gaim_import_gaim;
		else if(strcmp(optarg,"firefox") == 0)
		    target = firefox_import_firefox;
		else if(strcmp(optarg,"mydocuments") == 0)
		    target = windowsxp_import_mydocuments;
		else if(strcmp(optarg,"mypictures") == 0)
		    target = windowsxp_import_mypictures;
		else if(strcmp(optarg,"mymusic") == 0)
		    target = windowsxp_import_mymusic;
		else if(strcmp(optarg, "proxy") == 0)
		    target = windowsxp_import_proxy;
		else if(strcmp(optarg, "userpicture") == 0)
		    target = windowsxp_import_userpicture;
		else if(strcmp(optarg, "wallpaper") == 0)
		    target = windowsxp_import_wallpaper;
        else if(strcmp(optarg, "mozillafirefox") == 0)
            target = firefox_import_firefox;
        else if(strcmp(optarg, "internetexplorer") == 0)
            target = firefox_import_internetexplorer;
        else if(strcmp(optarg, "opera") == 0)
            target = firefox_import_opera;
        else if(strcmp(optarg, "outlookexpress") == 0)
            target = evolution_import_outlookexpress;
        else if(strcmp(optarg, "evolution") == 0)
            target = evolution_import_evolution;
		else
		    usage(argv);
		break;
	    default:
		usage(argv);
		break;
	}
    }
    
    if((from_user && to_user) && (from_location && to_location)) {
        struct passwd *p;
        char* passwd_file;
        FILE* fp = NULL;
        
        
        // Instead of chowning everything we create, we just drop to the user
        // we're working with.  Not entirely sure if this is a good/bad idea.
        asprintf(&passwd_file, "%s/etc/passwd", to_location);
        fp = fopen(passwd_file, "r");
        
        if(fp) {
            while((p = fgetpwent(fp)) != NULL) {
                if(strcmp(p->pw_name, to_user) == 0) {
                    setgid(p->pw_gid);
                    setuid(p->pw_uid);
                }
            }
            endpwent();
            fclose(fp);
        } else {
            fprintf(stderr, "Unable to open %s\n", passwd_file);
            exit(EXIT_FAILURE);
        }
        free(passwd_file);
        
        if(os_type == WINDOWSXP) initialize_registry_paths();
        target();
    } else
	usage(argv);
    
    return 0;
}
// vim:ai:et:sts=4:tw=80:sw=4:
