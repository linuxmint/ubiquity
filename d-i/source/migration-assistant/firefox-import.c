/**
* Copyright (C) 2007 Evan Dandrea <evand@ubuntu.com> under the GPLv2
*/

 /*
 * This file should cover importing into all Firefox versions up to and
 * including Firefox 2.  Firefox 3.0 will introduce a new backend (finally) for
 * bookmarks and history using SQLite.
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <ctype.h>

#include <sys/types.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>

#include "utils.h"
#include "registry.h"

typedef struct folder {
    char* title;
    char* description;
    char* ptf;
} folder;

typedef struct hlink {
    char* title;
    char* url;
    char* icon;
    char* feed;
    char* description;
} hlink;

typedef enum { HREF, ICON, FEED, PTF } attr_type;
typedef enum { FOLDER, LINK, HR } item_type;

typedef struct element {
    void* attributes;
    item_type type;
    struct element* next;
    struct element* children;
} element;

char* read_tag(const char* line) {
    char* ret;
    const char* ptr = line;
    int count = 0;
    while(*ptr != '<') {
	if(*ptr == '\0') return NULL;
	ptr++;
    }

    line = ++ptr;

    while(*ptr != '>' && *ptr != ' ') {
	if(*ptr == '\0') return NULL;
	count++;
	ptr++;
    }

    ret = malloc(count+1);
    memcpy(ret,line,count);
    ret[count] = '\0';

    return ret;
}

char* getcontent(const char* string) {
    char* ret;
    const char* ptr = string;
    int count = 0;

    while(*ptr != '\0')
        ptr++;

    // Find the </TAG> >
    while(*ptr != '>') {
        if(ptr == string) return NULL;
        ptr--;
    }
    ptr--;
    // Find the <TAG> >
    if(*ptr != 'D') {
        while(*ptr != '>') {
            if(ptr == string) return NULL;
            ptr--;
        }
    } else ptr++;

    string = ++ptr;

    // DD ends in a newline
    while(*ptr != '<' && *ptr != '\n') {
	if(*ptr == '\0') return NULL;
	count++;
	ptr++;
    }

    ret = malloc(count+1);
    memcpy(ret,string,count);
    ret[count] = '\0';

    return ret;
}

char* getattrib(const char* string, attr_type attr) {
    const char* href;
    const char* end;
    char* ret = NULL;
    int count = 0;
    const char* temp;
    if(attr == HREF)
        temp = "HREF=";
    else if(attr == ICON)
        temp = "ICON=";
    else if(attr == FEED)
        temp = "FEEDURL=";
    else if(attr == PTF)
        temp = "PERSONAL_TOOLBAR_FOLDER=";

    href = strstr(string, temp);
    if(!href) return NULL;

    while(*href != '\"')
	href++;

    end = ++href;

    while(*end != '\"') {
	count++;
	end++;
    }

    ret = malloc(count+1);
    memcpy(ret,href,count);
    ret[count] = '\0';

    return ret;
}

int count_whitespace(const char* string) {
    int count = 0;
    while(isspace(*string)) {
	count++;
	string++;
    }

    return count;
}

element* current; // To avoid having to iterate the entire list on every addition.
element* new_element(element** lst, item_type t, void* attributes) {
    element* el;
    el = (element *)malloc(sizeof(element));
    el->next = NULL;
    el->children = NULL;
    el->type = t;
    el->attributes = attributes;
    if(current)
        current->next = el;
    if(!(*lst)) {
        *lst = el;
    }

    current = el;
    return el;
}
element* append_element(element* parent, item_type t, void* attributes) {
    element* el;
    el = (element *)malloc(sizeof(element));
    el->next = NULL;
    el->children = NULL;
    el->type = t;
    el->attributes = attributes;
    
    if(parent->children) {
        element* ptr = parent->children;
        while(ptr->next != NULL) {
            ptr = ptr->next;
        }

        ptr->next = el;

    } else {
        parent->children = el;
    }

    return el;
}
char* strip_whitespace(char* line) {
        char* start = line;
        char* end = NULL;
        while(*start == ' ' || *start == '\t') start++;
        end = start;
        while(*end != '\r' && *end != '\t') {
            if(*end == '\n') break;
            end++;
        }
        *end = '\0';
        if(start == end) return NULL;
        return start;
}

void opera_build(FILE* fp, element* parent, element** list) {
    char* title = NULL;
    char* line = NULL;
    char* sline = NULL;
    char* tmp = NULL;
    size_t len = 0;
    ssize_t read;
    bool reread = false;

    while (true) {
        if(!reread) {
            if((read = getline(&line, &len, fp)) == -1) return;
        } else {
            reread = false;
        }

        sline = strip_whitespace(line);
        if(!sline) continue;
        if(sline[0] == '-') return;
        if(sline[0] != '#') continue;

        if(strcmp(sline, "#FOLDER") == 0) {
            title = NULL;

            while ((read = getline(&line, &len, fp)) != -1) {
                sline = strip_whitespace(line);
                if(!sline) continue;

                if(sline[0] == '-') return;

                if(sline[0] == '#') {
                    reread = true;
                    break;
                }

                tmp = sline;
                while(tmp && *tmp != '=') {
                    tmp++;
                }
                if(!tmp) continue;
                *tmp = '\0';

                if(strcmp(sline, "NAME") == 0) {
                    title = malloc(strlen(tmp+1) + 1);
                    strcpy(title, tmp+1);

                    // For now we don't import the Trash folder.
                    if(strcmp(title,"Trash") == 0) {
                        free(title);
                        while ((read = getline(&line, &len, fp)) != -1) {
                            sline = strip_whitespace(line);
                            if(sline)
                                if(strcmp(sline, "-") == 0) break;
                        }
                        break;
                    }
                    
                    folder* f;
                    f = (folder *)malloc(sizeof(folder));
                    f->title = title;
                    f->description = NULL;
                    f->ptf = NULL;

                    element* p = NULL;
                    if(parent) {
                        p = append_element(parent, FOLDER, f);
                    } else {
                        p = new_element(list, FOLDER, f);
                    }
                    opera_build(fp, p, list);
                }

            }
        }
            
        else if(strcmp(sline, "#URL") == 0) {
            char* url = NULL;

            title = NULL;
            while ((read = getline(&line, &len, fp)) != -1) {
                sline = strip_whitespace(line);
                if(!sline) continue;
                
                if(*sline == '\r' || *sline == '\n') continue;
                if(sline[0] == '#' || sline[0] == '-') {
                    reread = true;
                    break;
                }

                tmp = sline;
                while(tmp && *tmp != '=') {
                    tmp++;
                }
                if(!tmp) continue;
                *tmp = '\0';

                if(strcmp(sline, "NAME") == 0) {
                    title = malloc(strlen(tmp+1) + 1);
                    strcpy(title, tmp+1);
                } else if(strcmp(sline, "URL") == 0) {
                    url = malloc(strlen(tmp+1) + 1);
                    strcpy(url, tmp+1);
                }

                if(title && url) {
                    hlink* l;
                    l = (hlink *)malloc(sizeof(hlink));
                    l->url = url;
                    l->title = title;
                    l->feed = NULL;
                    l->description = NULL;
                    l->icon = NULL;

                    if(parent) {
                        append_element(parent, LINK, l);
                    } else {
                        new_element(list, LINK, l);
                    }
                    break;
                }
            }
        }
    }
}
const char* blacklisted_urls[] = {
    "http://www.microsoft.com/isapi/redir.dll",
    "http://go.microsoft.com",
    NULL
};
bool url_blacklisted(const char* url) {
    int i = 0;
    while(blacklisted_urls[i] != NULL) {
        if(strncmp(url, blacklisted_urls[i], strlen(blacklisted_urls[i])) == 0)
            return true;
        i++;
    }
    return false;
}
void internet_explorer_build(const char* path, element* parent, element** list) {
    struct dirent *dp;
    struct stat statbuf;
    DIR *dfd;
    FILE* fp;
    
    char * line = NULL;
    size_t len = 0;
    ssize_t read;

    char* url = NULL;

    if(chdir(path) == -1) {
        fprintf(stderr, "Error: Could not chdir into %s\n", path);
        return;
    }
    dfd = opendir(".");
    if(dfd != NULL) {
        while((dp = readdir(dfd)) != NULL) {
            if((strcmp(dp->d_name,".") == 0) || (strcmp(dp->d_name,"..") == 0))
                continue;
            char* tmp = dp->d_name;
            while(*tmp != '\0') tmp++;
            while(tmp != dp->d_name && *tmp != '.') tmp--;
            if(tmp != dp->d_name) {
                if(strcmp(tmp,".url") == 0) {
                    fp = fopen(dp->d_name, "r");
                    while((read = getline(&line, &len, fp)) != -1) {
                        char utag[5];
                        strncpy(utag, line, 5);
                        utag[4] = '\0';
                        if(strcmp(utag,"URL=") == 0) {
                            url = malloc(strlen(line+4));
                            memcpy(url,line+4, strlen(line+4)-1);
                            url[strlen(line+4)-2] = '\0';
                        }
                    }
                    *tmp = '\0';
                    if(url && !url_blacklisted(url)) {
                        char* title = malloc(strlen(dp->d_name)+1);
                        strcpy(title, dp->d_name);
                        hlink* l;
                        l = (hlink *)malloc(sizeof(hlink));
                        l->url = url;
                        l->title = title;
                        l->feed = NULL;
                        l->description = NULL;
                        l->icon = NULL;
                        
                        if(parent) {
                            append_element(parent, LINK, l);
                        } else {
                            new_element(list, LINK, l);
                        }
                    }
                    fclose(fp);
                }
            } else {
                stat(dp->d_name,&statbuf);
                if((statbuf.st_mode & S_IFMT) == S_IFDIR) {
                    // is a directory
                    char* title = malloc(strlen(dp->d_name)+1);
                    strcpy(title, dp->d_name);
                    
                    folder* f;
                    f = (folder *)malloc(sizeof(folder));
                    f->title = title;
                    f->description = NULL;
                    f->ptf = NULL;

                    element* p;
                    if(parent) {
                        p = append_element(parent, FOLDER, f);
                    } else {
                        p = new_element(list, FOLDER, f);
                    }
                    internet_explorer_build(dp->d_name, p, list);

                }
            }
        }
        closedir(dfd);
    }
    chdir("..");
    return;
}
void firefox_build(FILE* fp, element* parent, element** list) {
    // if parent is set then we will descend into parent and look at that level.
    char * line = NULL;
    char* tag = NULL;
    size_t len = 0;
    ssize_t read;
    bool repeat = false;


    while (true) {
        if(!repeat) {
            if((read = getline(&line, &len, fp)) == -1) break;
        } else {
            repeat = false;
        }
        tag = read_tag(line);
        if(!tag)
            continue;

        if(strcmp(tag, "/DL") == 0) {
            return;
        }
        // Horizontal Rule
        else if(strcmp(tag, "HR") == 0) {
            if(parent) {
                append_element(parent, HR, NULL);
            } else {
                new_element(list, HR, NULL);
            }
        }
        // Either a bookmark or a folder.
        else if(strcmp(tag, "DT") == 0) {
            int offset = count_whitespace(line)+4;
            free(tag);
            tag = read_tag(line + offset);
            if(!tag) {
                fprintf(stderr, "Could not find a tag after DT in line: %s\n", line + offset);
                return;
            }
            // Bookmark
            if(strcmp(tag, "A") == 0) {
                char* url = getattrib(line+offset+2, HREF);
                char* title = getcontent(line+offset+2);
                char* icon = getattrib(line+offset+2, ICON);
                char* feed = getattrib(line+offset+2, FEED);
                char* description = NULL;
                
                if((read = getline(&line, &len, fp)) == -1) {
                    puts("Got an EOF after an H3 tag.  Corrupt file?");
                    return;
                }
                tag = read_tag(line);
                if(strcmp(tag, "DD") == 0) {
                    description = getcontent(line+1);
                } else
                    repeat = true;

                hlink* l;
                l = (hlink *)malloc(sizeof(hlink));
                l->url = url;
                l->title = title;
                l->icon = icon;
                l->feed = feed;
                l->description = description;
                
                if(parent) {
                    append_element(parent, LINK, l);
                } else {
                    new_element(list, LINK, l);
                }
            }
            // Folder
            else if(strcmp(tag, "H3") == 0) {
                char* title = getcontent(line+offset+3);
                char* description = NULL;
                char* ptf = getattrib(line+offset+3, PTF);
                if((read = getline(&line, &len, fp)) == -1) {
                    puts("Got an EOF after an H3 tag.  Corrupt file?");
                    return;
                }
                tag = read_tag(line);
                if(!tag)
                    continue;
                if(strcmp(tag, "DD") == 0 || strcmp(tag, "DL") == 0) {
                    description = getcontent(line+1);
                } else {
                    puts("Tag after H3 was not DD or DL.");
                    return;
                }
                
                folder* f;
                f = (folder *)malloc(sizeof(folder));
                f->title = title;
                f->description = description;
                f->ptf = ptf;

                element* p;
                if(parent) {
                    p = append_element(parent, FOLDER, f);
                } else {
                    p = new_element(list, FOLDER, f);
                }
                firefox_build(fp, p, list);
            }
        }
        free(tag);
    }
    if (line)
        free(line);

    return;
}
void firefox_format_worker(FILE* fp, const element* ptr) {

    char* title = NULL;
    char* description = NULL;
    char* url = NULL;
    char* feed = NULL;
    char* icon = NULL;
    char* ptf = NULL;

    char linkstr[64] = "\0";
    while(ptr) {
        switch(ptr->type) {
            case HR :
                fprintf(fp, "<HR>\n");
                break;
            case LINK :
                title = ((hlink *)ptr->attributes)->title;
                url = ((hlink *)ptr->attributes)->url;
                feed = ((hlink *)ptr->attributes)->feed;
                description = ((hlink *)ptr->attributes)->description;
                icon = ((hlink *)ptr->attributes)->icon;
                strcpy(linkstr, "<DT><A HREF=\"%s\"");

                if(feed) {
                    strcat(linkstr, " FEEDURL=\"%s\"");
                }
                if(icon) {
                    strcat(linkstr, " ICON=\"%s\"");
                }
                strcat(linkstr, ">%s</A>\n");

                if(icon && feed) fprintf(fp, linkstr, url, feed, icon, title);
                else if(icon) fprintf(fp, linkstr, url, icon, title);
                else if(feed) fprintf(fp, linkstr, url, feed, title);
                else fprintf(fp, linkstr, url, title);
                linkstr[0] = '\0';

                if(description)
                    fprintf(fp, "<DD>%s\n", description);
                break;

            case FOLDER :
                title = ((folder *)ptr->attributes)->title;
                description = ((folder *)ptr->attributes)->description;
                ptf = ((folder *)ptr->attributes)->ptf;
                
                if(ptf == NULL)
                    fprintf(fp, "<DT><H3>%s</H3>\n", title);
                else {
                    fprintf(fp, "<DT><H3 PERSONAL_TOOLBAR_FOLDER=\"true\">"
                                "%s</H3>\n", title);
                }
                if(description)
                    fprintf(fp, "<DD>%s\n", description);
                fprintf(fp, "<DL><p>\n");
                if(ptr->children)
                    firefox_format_worker(fp, ptr->children);
                fprintf(fp, "</DL><p>\n");
                break;
            default :
                puts("Error: Type not A, H3, or HR.");
                break;
        }
        ptr = ptr->next;
    }
    return;
}

void firefox_format(const element* ptr, const char* file) {
    FILE* fp;
    const char intro[] = "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
    "<!-- This is an automatically generated file.\n"
    "     It will be read and overwritten.\n"
    "     DO NOT EDIT! -->\n"
    "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">\n"
    "<TITLE>Bookmarks</TITLE>\n"
    "<H1>Bookmarks</H1>\n"
    "<DL><p>\n\n";

    fp = fopen(file, "w");
    if(fp) {
        fprintf(fp, intro);
        firefox_format_worker(fp, ptr);
        fprintf(fp, "</DL><p>\n");
        fclose(fp);
    } else {
        fprintf(stderr, "Could not open %s for writing.\n", file);
    }
}
#if 0
void firefox_format_test(element* curr) {
    while(curr) {
        switch(curr->type) {
            case HR :
                puts("Horizontal Rule");
                break;
            case LINK :
                printf("Link: %s (%s)\n",   ((hlink *)curr->attributes)->title,
                                            ((hlink *)curr->attributes)->url);
                /* printf("Link: %s (%s)\nFeed: %s\n%s\n",   ((hlink *)curr->attributes)->title,
                                                ((hlink *)curr->attributes)->url,
                                                ((hlink *)curr->attributes)->feed,
                                                ((hlink *)curr->attributes)->icon); */
                break;
            case FOLDER :
                printf("Folder: %s (%s)\n", ((folder *)curr->attributes)->title,
                                            ((folder *)curr->attributes)->description);
                
                if(curr->children) {
                    puts("Folder has children.");
                    firefox_format_test(curr->children);
                    puts("Done iterating children.");
                }
                break;
            default :
                puts("Unknown");
                break;
        }
        curr = curr->next;
    }
    puts("");
    return;

}
#endif
void merge(element** to, element* from) {
    element* t = *to;
    element* f = from;
    bool found = false;

    while(f) {
        while(t) {
            if(t->type == f->type) {
                int type = t->type;
                switch(type) {
                    case HR :
                        found = true;
                        break;
                    case LINK :
                        if(strcmp(((hlink *)t->attributes)->url,
                            ((hlink *)f->attributes)->url) == 0) {
                            found = true;
                        }
                        break;
                    case FOLDER :
                        if(strcmp(((folder *)t->attributes)->title,
                            ((folder *)f->attributes)->title) == 0) {

                            if(f->children && t->children) {
                                merge(&t->children, f->children);
                            }

                            found = true;
                        }
                        break;
                    default :
                        puts("Link type unknown.");
                        break;
                }
                if(found) break;
            }
            t = t->next;
        }
        if(!found) {
            element* ptr;
            element* temp = f;
            // Remove from its list
            if(from != f) {
                ptr = from;
                while(ptr->next != f)
                    ptr = ptr->next;
                ptr->next = f->next;
                f = ptr->next;
            } else {
                // It was the first element in the list
                from = f->next;
                f = from;
            }

            // Append to the other list
            ptr = *to;
            while(ptr->next)
                ptr = ptr->next;
            ptr->next = temp;
            temp->next = NULL;

        } else {
            f = f->next;
        }
        found = false;
        t = *to;
    }
}

void setup_import(char** fullpath, element** to_bookmarks) {
    struct dirent *dp;
    struct stat statbuf;
    DIR *dfd;
    char* to_firefoxdir = NULL;
    char* d_name;
    FILE* fp;
    char* path = NULL;
    char bookmarksfile[32];
    *bookmarksfile = '\0';

    char random[] = "abcdefghijklmnopqrstuvwxyz0123456789"; //26
    asprintf(&to_firefoxdir, "%s/home/%s/.mozilla/firefox", to_location, to_user);
    char* mkdir = NULL;
    // This might be dangerous.
    asprintf(&mkdir, "mkdir -p %s", to_firefoxdir);
    system(mkdir);
    free(mkdir);

    if(chdir(to_firefoxdir) == -1) {
        fprintf(stderr, "Could not change directory to %s\n", to_firefoxdir);
        return;
    }

    dfd = opendir(".");
    if(dfd == NULL) {
        fprintf(stderr, "Could not open directory.");
        return;
    }
    
    while((dp = readdir(dfd)) != NULL) {
        if((strcmp(dp->d_name,".") == 0) || (strcmp(dp->d_name,"..") == 0))
            continue;
        stat(dp->d_name,&statbuf);
        if(!S_ISDIR(statbuf.st_mode)) continue;

        // Make sure we're looking at the default profile.
        d_name = malloc(strlen(dp->d_name)+1);
        strcpy(d_name,dp->d_name);
        char* d_nameptr = d_name;
        while(*d_nameptr != '\0') d_nameptr++;
        while(*d_nameptr != '.' && d_nameptr != dp->d_name) d_nameptr--;
        if(strcmp(d_nameptr,".default") == 0) {
            strcpy(bookmarksfile, dp->d_name);
            strcat(bookmarksfile, "/bookmarks.html");
            break;
        }
        free(d_name);

    }
    closedir(dfd);
    if(bookmarksfile[0] != '\0') {
        fp = fopen(bookmarksfile, "r");
        if(fp == NULL) {
            fprintf(stderr, "Could not open file, %s\n", bookmarksfile);
            return;
        }
        firefox_build(fp, NULL, to_bookmarks);
        fclose(fp);
        asprintf(fullpath, "%s/%s", to_firefoxdir, bookmarksfile);
    } else {
        int r, i;
        char b[17];
        for(i=0; i<8; i++) {
            r = (int)((double)rand() / ((double)RAND_MAX + 1) * 26);
            b[i] = random[r];
        }
        b[8] = '\0';
        strcat(b, ".default");
        
        asprintf(&path, "%s/profiles.ini", to_firefoxdir);
        fp = fopen(path, "a");
        free(path);
        fprintf(fp, "[General]\nStartWithLastProfile=1\n\n[Profile0]\n"
                    "Name=default\nIsRelative=1\nPath=%s\n\n", b);
        fclose(fp);

        asprintf(&path, "%s/%s", to_firefoxdir, b);
        asprintf(&mkdir, "mkdir -p %s", path);
        system(mkdir);
        free(mkdir);
        asprintf(fullpath, "%s/bookmarks.html", path);
        free(path);
    }
    free(to_firefoxdir);

}

void firefox_import_firefox(void) {
    struct dirent *dp, *dp2;
    struct stat statbuf;
    DIR *dfd, *dfd2;
    char bookmarksfile[32] = "\0";
    FILE* fp;
    element* from_bookmarks = NULL;
    element* to_bookmarks = NULL;

    char* from_firefoxdir = NULL;
    char* fullpath = NULL;
    bool found = false;

    setup_import(&fullpath, &to_bookmarks);

    // Build a tree of the bookmarks file(s) we're importing from, then merge it
    // with the new bookmarks tree.
    if(os_type == LINUX) {
        asprintf(&from_firefoxdir, "%s/home/%s/.mozilla/firefox",
            from_location, from_user);
    }
    else if(os_type == WINDOWSXP) {
        char* appdata = NULL;
        char* path;
        appdata = findkey(user_key_file, "\\Software\\Microsoft\\Windows\\"
            "CurrentVersion\\Explorer\\Shell Folders\\Local AppData");
        if(!appdata) {
            printf("Couldn't find %s\n", appdata);
            return;
        }
        path = reformat_path(appdata);
        free(appdata);
        asprintf(&from_firefoxdir, "%s/%s/Mozilla/Firefox/Profiles", from_location,
            path);
        free(path);
    }
    if(chdir(from_firefoxdir) == -1) {
        fprintf(stderr, "Could not change directory to %s.\n", from_firefoxdir);
        return;
    }
    free(from_firefoxdir);

    dfd = opendir(".");
    if(dfd != NULL) {
        while((dp = readdir(dfd)) != NULL) {
            if((strcmp(dp->d_name,".") == 0) || (strcmp(dp->d_name,"..") == 0))
                continue;
            stat(dp->d_name,&statbuf);
            if(!S_ISDIR(statbuf.st_mode)) continue;
            
            dfd2 = opendir(dp->d_name);
            if(dfd != NULL) {
                while((dp2 = readdir(dfd2)) != NULL) {
                    if(strcmp(dp2->d_name,"bookmarks.html") == 0)
                        found = true;
                }
            }
            closedir(dfd2);
            if(found) {
                found = false;
                strcpy(bookmarksfile,dp->d_name);
                strcat(bookmarksfile,"/bookmarks.html");
                fp = fopen(bookmarksfile,"r");
                if(fp == NULL) {
                    fprintf(stderr, "Could not open file, %s.\n", bookmarksfile);
                    continue;
                }
                // TODO: get rid of current.
                current = NULL;
                firefox_build(fp, NULL, &from_bookmarks);
                fclose(fp);
                if(to_bookmarks)
                    merge(&to_bookmarks, from_bookmarks);
                else
                    to_bookmarks = from_bookmarks;
            }
        }
    closedir(dfd);
    }

    // Now we translate the tree into a bookmarks.html file.
    firefox_format(to_bookmarks, fullpath);
    free(fullpath);
}

void firefox_import_opera(void) {
    FILE* fp;
    char* bookmarksfile, *path;
    element* to_bookmarks = NULL;
    element* from_bookmarks = NULL;
    char* fullpath = NULL;
    char* appdata = NULL;

    setup_import(&fullpath, &to_bookmarks);
    appdata = findkey(user_key_file, "\\Software\\Microsoft\\Windows\\"
        "CurrentVersion\\Explorer\\Shell Folders\\Local AppData");
    if(!appdata) {
        printf("Couldn't find %s\n", appdata);
        return;
    }
    path = reformat_path(appdata);
    free(appdata);
    asprintf(&bookmarksfile, "%s/%s/Opera/Opera/profile/opera6.adr",
        from_location, path);
    free(path);
    fp = fopen(bookmarksfile, "r");
    if(fp == NULL) {
        fprintf(stderr, "Could not open file, %s.\n", bookmarksfile);
        return;
    }
    free(bookmarksfile);

    current = NULL;
    opera_build(fp, NULL, &from_bookmarks);
    fclose(fp);
    
    if(to_bookmarks)
        merge(&to_bookmarks, from_bookmarks);
    else
        to_bookmarks = from_bookmarks;
    
    firefox_format(to_bookmarks, fullpath);
    free(fullpath);
}



void firefox_import_internetexplorer(void) {
    char* from_iedir = NULL;
    element* to_bookmarks = NULL;
    element* from_bookmarks = NULL;
    char* fullpath = NULL;

    char* path;
    char* favorites = NULL;

    setup_import(&fullpath, &to_bookmarks);

    favorites = findkey(user_key_file, "\\Software\\Microsoft\\Windows\\"
        "CurrentVersion\\Explorer\\Shell Folders\\Favorites");
    if(!favorites) {
        printf("Couldn't find %s\n", favorites);
        return;
    }
    path = reformat_path(favorites);
    free(favorites);
    asprintf(&from_iedir, "%s/%s", from_location, path);
    free(path);

    current = NULL;
    internet_explorer_build(from_iedir, NULL, &from_bookmarks);
    free(from_iedir);
    if(to_bookmarks)
        merge(&to_bookmarks, from_bookmarks);
    else
        to_bookmarks = from_bookmarks;
    
    firefox_format(to_bookmarks, fullpath);
    free(fullpath);
}

// vim:ai:et:sts=4:tw=80:sw=4:
