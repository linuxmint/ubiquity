#include <libxml/parser.h>
#include <libxml/tree.h>
#include <stdio.h>
#include <string.h>

#include <sys/types.h>
#include <sys/stat.h>
#include <dirent.h>

#include "gaim-import.h"
#include "registry.h"
#include "utils.h"

xmlDoc* gaim_new_accounts_file(void) {
    static xmlDoc* doc = NULL;
    xmlNode* node = NULL;
    char* accounts_file;
    int opts = XML_PARSE_NOBLANKS | XML_PARSE_NOERROR | XML_PARSE_RECOVER;

    if(!doc) {
	asprintf(&accounts_file, "%s/%s/%s/%s", to_location,
	    "home", to_user,
	    ".purple/accounts.xml");

	create_file(accounts_file);
	doc = xmlReadFile(accounts_file, NULL, opts);
	free(accounts_file);
	
	node = xmlDocGetRootElement(doc);
	if(!node) {
	    node = xmlNewNode(NULL, (xmlChar*) "accounts");
	    xmlNewProp(node, (xmlChar*) "version", (xmlChar*) "1.0");
	    xmlDocSetRootElement(doc, node);
	}
    }
    return doc;
}

void gaim_save_accounts_file(void) {
    xmlDoc* doc = gaim_new_accounts_file();
    char* accounts_file;
    asprintf(&accounts_file, "%s/%s/%s/%s", to_location,
	    "home", to_user,
	    ".purple/accounts.xml");
    xmlSaveFormatFile(accounts_file, doc, 1);
}

int gaim_account_exists(xmlNode* node) {
    xmlNode* ptr = NULL;
    xmlDoc* doc = NULL;
    xmlChar* username = NULL;
    xmlChar* protocol = NULL;

    node = node->children;

    while(node != NULL) {
       if(xmlStrcmp(node->name, (xmlChar*) "name") == 0)
	   username = node->children->content;
       else if(xmlStrcmp(node->name, (xmlChar*) "protocol") == 0)
	   protocol = node->children->content;

       node = node->next;
    }

    doc = gaim_new_accounts_file();
    node = xmlDocGetRootElement(doc);

    node = node->children;
    int found = 0;

    // For each account.
    while(node) {
       if(node->type == XML_ELEMENT_NODE &&
	(xmlStrcmp(node->name, (xmlChar*) "account") == 0)) {

	   ptr = node->children;

	   // For each account property.
	   while(ptr != NULL) {
	       if(xmlStrcmp(ptr->name, (xmlChar*) "name") == 0) {
		   if(xmlStrcmp(ptr->children->content,
			       (xmlChar*) username) == 0) {
		       found++;
		   }
	       }
	       if(xmlStrcmp(ptr->name, (xmlChar*) "protocol") == 0) {
		   if(xmlStrcmp(ptr->children->content,
			       (xmlChar*) protocol) == 0) {
		       found++;
		   }
	       }
	       ptr = ptr->next;
	   }

	   if(found == 2) return 1;
	   found = 0;
       }
       node = node->next;
    }
    return 0;
}

void gaim_add_account(xmlNode* node) {
    xmlDoc* doc = gaim_new_accounts_file();
    xmlNode* top = xmlDocGetRootElement(doc);
    xmlAddChild(top, node);
}

void gaim_import_gaim(void) {
    xmlDoc* doc = NULL;
    xmlNode* node, *node_copy = NULL;
    char* accounts_file;

    char* path;
    char* appdata = NULL;
	FILE* fp;

    if(os_type == LINUX) {
		asprintf(&accounts_file, "%s/%s/%s/%s", from_location,
			"home", from_user,
			".gaim/accounts.xml");
		fp = fopen(accounts_file, "r");
		if(fp == NULL) {
			free(accounts_file);
			asprintf(&accounts_file, "%s/%s/%s/%s", from_location,
				"home", from_user,
				".purple/accounts.xml");
		} else
			fclose(fp);
	}
    else if(os_type == WINDOWSXP) {
        appdata = findkey(user_key_file, "\\Software\\Microsoft\\Windows\\"
            "CurrentVersion\\Explorer\\Shell Folders\\Local AppData");
        if(!appdata) {
            printf("Couldn't find %s\n", appdata);
            return;
        }
        path = reformat_path(appdata);
        free(appdata);
	    asprintf(&accounts_file, "%s/%s/%s", from_location, path,
    		"/.gaim/accounts.xml");
		fp = fopen(accounts_file, "r");
		if(fp == NULL) {
			free(accounts_file);
			asprintf(&accounts_file, "%s/%s/%s", from_location, path,
				"/.purple/accounts.xml");
		} else
			fclose(fp);
        free(path);
    }
    
    if(!accounts_file) return;

    doc = xmlReadFile(accounts_file, NULL, XML_PARSE_NOBLANKS);
    free(accounts_file);
    if(!doc) return;
    node = xmlDocGetRootElement(doc);

    node = node->children;

    while(node) {
       if(node->type == XML_ELEMENT_NODE &&
	(xmlStrcmp(node->name, (xmlChar*) "account") == 0)) {

	   if(!gaim_account_exists(node)) {
		node_copy = xmlCopyNode(node, 1);
		gaim_add_account(node_copy);
	   }
       }
       node = node->next;
    }
    gaim_save_accounts_file();
}

void gaim_import_other(const char* proto, const char* username,
	const char* password) {
    
    xmlNode *account, *name, *protocol;
    account = xmlNewNode(NULL, (xmlChar*) "account");
    
    // protocol must come before name in the accounts file otherwise Gaim will
    // have a bad time.
    protocol = xmlNewChild(account, NULL, (xmlChar*) "protocol", (xmlChar*) proto);
    name = xmlNewChild(account, NULL, (xmlChar*) "name", (xmlChar*) username);
    
    if(!gaim_account_exists(account))
	gaim_add_account(account);
}

void gaim_import_yahoo(void) {
    char* username;

    username = findkey(user_key_file,
	    "\\Software\\Yahoo\\pager\\Yahoo! User ID");

    if(username) {
	gaim_import_other("prpl-yahoo", username, NULL);
	free(username);
	gaim_save_accounts_file();
    } else {
	puts("could not get yahoo ID from registry.");
	exit(EXIT_FAILURE);
    }
}

// FIXME: This is a terrible test.  If the user has an AIM account with the
// same username as the one they use for Windows, the test will fail.
void gaim_import_aimtriton(void) {
    DIR *dir, *dir2;
    struct dirent *entry, *entry2;
    struct stat buf;
    struct stat st;
    char* dirname, *uprofile, *cls, *path;
    char* appdata = NULL;
    char* profile = NULL;

    appdata = findkey(user_key_file, "\\Software\\Microsoft\\Windows\\"
        "CurrentVersion\\Explorer\\Shell Folders\\Local AppData");
    if(!appdata) {
        printf("Couldn't find %s\n", appdata);
        return;
    }
    path = reformat_path(appdata);
    free(appdata);
    asprintf(&dirname, "%s/%s/%s", from_location, path, "AOL/UserProfiles");
    free(path);

    dir = opendir(dirname);
    if(!dir) {
	    printf("Could not open AIM profile root directory: %s\n", dirname);
	    free(dirname);
	    return;
    }

    while((entry = readdir(dir)) != NULL) {
        asprintf(&profile, "%s/%s", dirname, entry->d_name);
        if( -1 == stat(profile, &st)) {
            fprintf(stderr, "Unable to stat %s.\n", profile);
            free(profile);
        } else if(!(S_ISDIR(st.st_mode))) {
            free(profile);
            continue;
        } else if(strcmp(entry->d_name,"All Users") == 0 ||
            (strcmp(entry->d_name,".") == 0 ||
             strcmp(entry->d_name,"..") == 0)) {
            free(profile);
            continue;
        }
        free(profile);

        asprintf(&uprofile, "%s/%s", dirname, entry->d_name);
        dir2 = opendir(uprofile);
        if(!dir2) {
            printf("Could not open user's AIM profile directory: %s\n", uprofile);
            free(uprofile);
            return;
        }

        while((entry2 = readdir(dir2)) != NULL) {
            if((strcmp(entry2->d_name,from_user) != 0) &&
                ((strcmp(entry2->d_name,".") != 0) &&
                 (strcmp(entry2->d_name,"..") != 0))) {
            asprintf(&cls, "%s/%s/cls", uprofile, entry2->d_name);
            
            if(stat(cls, &buf) == 0)
                gaim_import_other("prpl-oscar", entry2->d_name, NULL);

            free(cls);
            }
        }
        closedir(dir2);
        free(uprofile);

    }
    free(dirname);
    closedir(dir);
    gaim_save_accounts_file();
}
