#include <stdio.h>
#include <libxml/parser.h>
#include <libxml/tree.h>
#include <stdbool.h>
#include <string.h>

#include <time.h>
#include <unistd.h>

#include <libgen.h>

#include "registry.h"
#include "utils.h"

#if 0
int indent = 0;
void print(xmlNode* node) {
    while(node != NULL) {
        int i = 0;
        while(i < indent) {
            printf(" ");
            i++;
        }
        if(node->children && node->children->content)
            printf("node: %s (%s)\n", node->name, node->children->content);
        else
            printf("node: %s\n", node->name);

        if(node->children) {
            indent++;
            print(node->children);
            indent--;
        }

        node = node->next;
    }

}
#endif
bool accounts_are_equal(xmlNode* first, xmlNode* second) {
// FIXME: uid will not work as we are talking about different systems, they'll
// always be different.  Use a combination of the server name and username
// instead.
    xmlChar* firsturl = NULL;
    xmlChar* secondurl = NULL;

    if(!(first && second))
        return false;

    first = first->children;
    while(xmlStrcmp(first->name, BAD_CAST "transport") != 0)
        first = first->next;
    first = first->children;
    while(xmlStrcmp(first->name, BAD_CAST "url") != 0)
        first = first->next;
    firsturl = first->children->content;

    second = second->children;
    while(xmlStrcmp(second->name, BAD_CAST "transport") != 0)
        second = second->next;
    second = second->children;
    while(xmlStrcmp(second->name, BAD_CAST "url") != 0)
        second = second->next;
    secondurl = second->children->content;
    
    if(!(firsturl && secondurl))
        return false;

    if(xmlStrcmp(firsturl, secondurl) == 0)
        return true;
    else
        return false;
}

xmlNode* get_account_data(xmlNode* node){
// Expects <li>
        xmlChar* account = NULL;
        
        if(xmlStrcmp(node->name, BAD_CAST "li") == 0) {
            node = node->children;
            if(xmlStrcmp(node->name, BAD_CAST "stringvalue") == 0) {
                node = node->children;
                if(node && node->content)
                    account = node->content;
            }
        }

        if(account) {
            node = xmlDocGetRootElement(xmlReadDoc(account, NULL, NULL, XML_PARSE_NOBLANKS));
        }
        return node;
}
void evolution_merge(xmlNode** into, xmlNode* from) {
// expects <entry name="accounts">
    xmlNode* in = *into;
    xmlNode* indata = NULL;
    xmlNode* fromdata = NULL;
    bool exists = false;
    
    if(in == from) return;
    if(!(in && from) || !(in->children && from->children)) {
        fprintf(stderr, "merge called with invalid poiners: %p %p\n", in, from);
        return;
    }
    in = in->children;
    from = from->children;
    while(from) {
        fromdata = get_account_data(from);
        while(in) {
            indata = get_account_data(in);
            if(accounts_are_equal(indata, fromdata)) {
                exists = true;
                break;
            }
            xmlFreeDoc(indata->doc);
            in = in->next;
        }
        in = (*into)->children;
        if(!exists) {
            xmlAddChild(in->parent, from);
        } else {
            exists = false;
        }
        xmlFreeDoc(fromdata->doc);
        from = from->next;
    }
}
xmlNode* evolution_setup(const char* file) {
    FILE* fd = fopen(file, "r");
    if(fd) {
        puts("File exists.");
        fclose(fd);
        xmlDoc* d = xmlReadFile(file, NULL, XML_PARSE_NOBLANKS);
        xmlNode* node = xmlDocGetRootElement(d);
        while(xmlStrcmp(node->name, BAD_CAST "gconf") != 0)
            node = node->next;

        node = node->children;
        while(node) {
            // FIXME foreach property.
            if(xmlStrcmp(node->properties->children->content, BAD_CAST "accounts") == 0) {
                break;
            }
            node = node->next;
        }
        return node;
    } else {
        char* dir = strdup(file);
        makegconfdirs(dirname(dir));
        free(dir);
        return NULL;
    }
}
typedef enum { IMAP, POP3 } server_type;
typedef struct account {
    server_type type;
    char* accountname;
    char* fullname;
    char* email;
    char* incominguser;
    char* incomingserver;
    char* incomingport;
    char* incomingssl;
    char* smtpuser;
    char* smtpserver;
    char* smtpport;
    char* smtpssl;
    char* uid;
} account;

void evolution_import_other(account* a) {
    char* file = NULL;
    asprintf(&file, "%s/%s/%s/%s", to_location, "home", to_user,
        ".gconf/apps/evolution/mail/\%gconf.xml");

    char* smtpurl = NULL;
    char* incomingurl = NULL;
    if(a->incominguser != NULL) {
            // Need to replace ' ' with %20
            // Need to replace '@' with %40
            char* temp = NULL;
            temp = strrep(a->incominguser, " ", "\%20");
            free(a->incominguser);
            a->incominguser = temp;

            temp = strrep(a->incominguser, "@", "\%40");
            free(a->incominguser);
            a->incominguser = temp;
    }
    if(a->type == IMAP) {
        if(a->incominguser != NULL) {
            asprintf(&incomingurl, "imap://%s@%s",
                a->incominguser, a->incomingserver);
        } else {
            asprintf(&incomingurl, "imap://%s", a->incomingserver);
        }
    } else {
        if(a->incominguser != NULL) {
            asprintf(&incomingurl, "pop://%s@%s",
                a->incominguser, a->incomingserver);
        } else {
            asprintf(&incomingurl, "pop://%s", a->incomingserver);
        }
    }
    if(a->incomingport != NULL) {
        char* temp;
        asprintf(&temp, "%s:%s", incomingurl, a->incomingport);
        incomingurl = temp;
    }
    if(a->incomingssl != NULL) {
        char* temp;
        asprintf(&temp, "%s/%s", incomingurl, a->incomingssl);
        incomingurl = temp;
    }

    if(a->smtpuser != NULL) {
        // Need to replace ' ' with %20
        // Need to replace '@' with %40
        char* temp = NULL;
        temp = strrep(a->smtpuser, " ", "\%20");
        free(a->smtpuser);
        a->smtpuser = temp;

        temp = strrep(a->smtpuser, "@", "\%40");
        free(a->smtpuser);
        a->smtpuser = temp;
        asprintf(&smtpurl, "smtp://%s@%s", a->smtpuser, a->smtpserver);
    } else {
        asprintf(&smtpurl, "smtp://%s", a->smtpserver);
    }
    if(a->smtpport != NULL) {
        char* temp;
        asprintf(&temp, "%s:%s", smtpurl, a->smtpport);
        smtpurl = temp;
    }
    if(a->smtpssl != NULL) {
        char* temp;
        asprintf(&temp, "%s/%s", smtpurl, a->smtpssl);
        smtpurl = temp;
    }

    const char* acct = "<account name=\"%s\" uid=\"%s\" enabled=\"true\">"
        "<identity><name>%s</name><addr-spec>%s</addr-spec></identity>"
        "<source save-passwd=\"false\" keep-on-server=\"false\">"
        "<url>%s</url></source>"
        "<transport save-passwd=\"false\"><url>%s</url></transport>"
        "</account>";

    char* accountstring = NULL;
    asprintf(&accountstring, acct, a->accountname, a->uid, a->fullname,
        a->email, incomingurl, smtpurl);
    xmlDoc* doc = xmlNewDoc(BAD_CAST "1.0");
    xmlNode* gconf = xmlNewNode(NULL, BAD_CAST "gconf");
    xmlNode* entry = xmlNewChild(gconf, NULL, BAD_CAST "entry", NULL);
    xmlNewProp(entry, BAD_CAST "name", BAD_CAST "accounts");
    xmlNewProp(entry, BAD_CAST "type", BAD_CAST "list");
    xmlNewProp(entry, BAD_CAST "ltype", BAD_CAST "string");
    xmlNode* li = xmlNewChild(entry, NULL, BAD_CAST "li", NULL);
    xmlNewProp(li, BAD_CAST "type", BAD_CAST "string");
    xmlNewChild(li, NULL, BAD_CAST "stringvalue", BAD_CAST accountstring);
    xmlDocSetRootElement(doc, gconf);

    xmlNode* to = evolution_setup(file);
    if(to) {
        evolution_merge(&to, entry);
        xmlSaveFormatFile(file, to->doc, 1);
    } else
        xmlSaveFormatFile(file, doc, 1);

}
void evolution_import_evolution(void) {
    char* file = NULL;
    asprintf(&file, "%s/%s/%s/%s", from_location, "home", from_user,
        ".gconf/apps/evolution/mail/\%gconf.xml");
    
    xmlDoc* d = xmlReadFile(file, NULL, XML_PARSE_NOBLANKS);
    free(file);
    xmlNode* node = xmlDocGetRootElement(d);
    while(xmlStrcmp(node->name, BAD_CAST "gconf") != 0)
        node = node->next;

    node = node->children;
    while(node) {
        // FIXME foreach property.
        if(xmlStrcmp(node->properties->children->content, BAD_CAST "accounts") == 0) {
            break;
        }
        node = node->next;
    }
    asprintf(&file, "%s/%s/%s/%s", to_location, "home", to_user,
        ".gconf/apps/evolution/mail/\%gconf.xml");
    xmlNode* to = evolution_setup(file);
    if(to) {
        evolution_merge(&to, node);
        xmlSaveFormatFile(file, to->doc, 1);
    } else
        xmlSaveFormatFile(file, d, 1);
    free(file);
}
void evolution_import_outlookexpress(void) {
    char* account_key = NULL;
    char* temp_key = NULL;

    int i = 1;
    static int serial;
    static char *hostname;
    account* a;

    while(true) {
        a = (account *)malloc(sizeof(account));
        a->accountname = NULL;
        a->fullname = NULL;
        a->email = NULL;
        a->incominguser = NULL;
        a->incomingserver = NULL;
        a->incomingport = NULL;
        a->incomingssl = NULL;
        a->smtpuser = NULL;
        a->smtpserver = NULL;
        a->smtpport = NULL;
        a->smtpssl = NULL;
        a->uid = NULL;

        asprintf(&account_key, "\\Software\\Microsoft\\"
        "Internet Account Manager\\Accounts\\%.8d\\", i);
        asprintf(&temp_key, "%s%s", account_key, "Account Name");
        a->accountname = findkey(user_key_file, temp_key);
        free(temp_key);
        if(!a->accountname) {
            if(a) free(a);
            break;
        }

        // Taken from libedataserver/e-uid.c
        char buffer [512];

        if ((gethostname (buffer, sizeof (buffer) - 1) == 0) &&
            (buffer [0] != 0))
                hostname = buffer;
        else
                hostname = "localhost";

        asprintf (&a->uid, "%lu.%lu.%d@%s",
                                (unsigned long) time (NULL),
                                (unsigned long) getpid (),
                                serial++,
                                hostname);

        asprintf(&temp_key, "%s%s", account_key, "SMTP Display Name");
        a->fullname = findkey(user_key_file, temp_key);
        free(temp_key);

        asprintf(&temp_key, "%s%s", account_key, "SMTP Email Address");
        a->email = findkey(user_key_file, temp_key);
        free(temp_key);

        asprintf(&temp_key, "%s%s", account_key, "IMAP User Name");
        a->incominguser = findkey(user_key_file, temp_key);
        free(temp_key);

        if(a->incominguser) {
            a->type = IMAP;
            asprintf(&temp_key, "%s%s", account_key, "IMAP Server");
            a->incomingserver = findkey(user_key_file, temp_key);
            free(temp_key);
            
            asprintf(&temp_key, "%s%s", account_key, "IMAP Port");
            a->incomingport = findkey(user_key_file, temp_key);
            free(temp_key);
            
            asprintf(&temp_key, "%s%s", account_key, "IMAP Secure Connection");
            a->incomingssl = findkey(user_key_file, temp_key);
            free(temp_key);
        } else {
            a->type = POP3;
            asprintf(&temp_key, "%s%s", account_key, "POP3 User Name");
            a->incominguser = findkey(user_key_file, temp_key);
            free(temp_key);

            asprintf(&temp_key, "%s%s", account_key, "POP3 Server");
            a->incomingserver = findkey(user_key_file, temp_key);
            free(temp_key);
            
            asprintf(&temp_key, "%s%s", account_key, "POP3 Port");
            a->incomingport = findkey(user_key_file, temp_key);
            free(temp_key);
            
            asprintf(&temp_key, "%s%s", account_key, "POP3 Secure Connection");
            a->incomingssl = findkey(user_key_file, temp_key);
            free(temp_key);
        }
        if(a->incomingssl && strcmp(a->incomingssl, "1") == 0) {
            free(a->incomingssl);
            a->incomingssl = ";use_ssl=always";
        } else {
            free(a->incomingssl);
            a->incomingssl = NULL;
        }


        asprintf(&temp_key, "%s%s", account_key, "SMTP User Name");
        a->smtpuser = findkey(user_key_file, temp_key);
        free(temp_key);

        asprintf(&temp_key, "%s%s", account_key, "SMTP Server");
        a->smtpserver = findkey(user_key_file, temp_key);
        free(temp_key);
        
        asprintf(&temp_key, "%s%s", account_key, "SMTP Port");
        a->smtpport = findkey(user_key_file, temp_key);
        free(temp_key);
            
        asprintf(&temp_key, "%s%s", account_key, "SMTP Secure Connection");
        a->smtpssl = findkey(user_key_file, temp_key);
        free(temp_key);
        if(a->smtpssl && strcmp(a->smtpssl, "1") == 0) {
            free(a->smtpssl);
            a->smtpssl = ";use_ssl=always";
        } else {
            free(a->smtpssl);
            a->smtpssl = NULL;
        }

        free(account_key);

        printf("accountname: %s\n", a->accountname);
        printf("fullname: %s\n", a->fullname);
        printf("email: %s\n", a->email);
        printf("incominguser: %s\n", a->incominguser);
        printf("incomingserver: %s\n", a->incomingserver);
        printf("incomingport: %s\n", a->incomingport);
        printf("incomingssl: %s\n", a->incomingssl);
        printf("smtpuser: %s\n", a->smtpuser);
        printf("smtpserver: %s\n", a->smtpserver);
        printf("smtpport: %s\n", a->smtpport);
        printf("smtpssl: %s\n", a->smtpssl);
        printf("uid: %s\n", a->uid);
        printf("test: %s\n", findkey(user_key_file, "\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders\\Local AppData"));
        puts("");

        evolution_import_other(a);
        i++;
        if(a->accountname)
            free(a->accountname);
        if(a->fullname)
            free(a->fullname);
        if(a->email)
            free(a->email);
        if(a->incominguser);
            free(a->incominguser);
        if(a->incomingserver)
            free(a->incomingserver);
        if(a->incomingport);
            free(a->incomingport);
        if(a->smtpuser)
            free(a->smtpuser);
        if(a->smtpserver)
            free(a->smtpserver);
        if(a->smtpport)
            free(a->smtpport);
        free(a);
    }
}
// vim:ai:et:sts=4:tw=80:sw=4:
