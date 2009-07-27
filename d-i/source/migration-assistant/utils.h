// Move into globals.h for readability.
char* from_location;
char* from_user;
char* to_location;
char* to_user;
char* software_key_file;
char* user_key_file;
typedef enum { WINDOWSXP, LINUX } ostypes;
ostypes os_type;

char *strrep(const char *str, const char *old, const char *new);
char* reformat_path(const char* from);
void copyfile(const char* from, const char* to);
void rcopy(const char* from, const char* to);
void makedirs(const char*);
void create_file(const char*);
typedef enum { GCONF_BOOLEAN, GCONF_STRING, GCONF_LIST_STRING } gconf_type;
void set_gconf_key (const char*, const char*, gconf_type, const char*);
void add_wallpaper (const char*);
void makegconfdirs(const char *dir);
void initialize_registry_paths();
void initialize_software_registry_path();
void initialize_user_registry_path();
char* get_profiles_dir(const char *mountpoint);
// struct target_t {
//  const char* option;
//  const char* name;
//  void (*search)();
//  void (*import)();
// }
//
// // option name from to
// struct targets_t targets[] = {
//  { "gaim", "Gaim IM", windowsxp_gaim, gaim_import_gaim },
//  { "yahoo", "Yahoo IM", windowsxp_yahoo, gaim_import_yahoo },
//  { "gaim", "Gaim IM", linux_gaim, gaim_import_gaim },
//  { NULL, 0, NULL, 0 }
// };
