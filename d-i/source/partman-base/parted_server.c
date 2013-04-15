#include <parted/parted.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>
#include <stdbool.h>
#include <ctype.h>
#include <signal.h>
#include <stdarg.h>

/**********************************************************************
   Logging
**********************************************************************/

/* This file is used as pid-file. */
char pidfile_name[] = "/var/run/parted_server.pid";

/* These are the communication fifos */
char infifo_name[] = "/var/lib/partman/infifo";
char outfifo_name[] = "/var/lib/partman/outfifo";
char stopfifo_name[] = "/var/lib/partman/stopfifo";

/* This file is used as log-file. */
char logfile_name[] = "/var/log/partman";

/* main() opens the logfile */
FILE *logfile;

/* This string is used to prepend the messages written in the log file */
char const program_name[] = "parted_server";

/* Write a message to the log-file.  Arguments are the same as in printf.
 * Note that this deliberately uses asprintf, not xasprintf; if it fails,
 * there's nothing useful we can do, and we might be about to exit anyway.
 */
/* log(const char *format, ...) */
#define log(...) \
	({ \
                char *msg_log; \
                if (asprintf(&msg_log, __VA_ARGS__) >= 0) { \
                        fprintf(logfile, "%s: %s\n", program_name, msg_log); \
                        fflush(logfile); \
                        free(msg_log); \
                } \
        })

/* Write a line to the log-file and exit. */
/* critical_error(const char *format, ...) */
#define critical_error(...) \
        ({ \
                log(__VA_ARGS__); \
                log("Line %i. CRITICAL ERROR!!!  EXITING.", __LINE__); \
                exit(1); \
        })

/* For debugging purposes */
#define traceline() log("Line: %i", __LINE__)

#define assert(x) \
        if(!(x)) \
                critical_error("Assertion failed at line %i.", __LINE__)

#define log_partitions(dev, disk) \
        (dump_info(logfile, dev, disk), fflush(logfile))

char *
xasprintf(const char *format, ...)
{
        va_list args;
        char *result;

        va_start(args, format);
        if (vasprintf(&result, format, args) < 0) {
                if (errno == ENOMEM)
                        critical_error("Cannot allocate memory.");
                return NULL;
        }

        return result;
}

enum alignment {
        ALIGNMENT_CYLINDER,
        ALIGNMENT_MINIMAL,
        ALIGNMENT_OPTIMAL
} alignment = ALIGNMENT_OPTIMAL;

/**********************************************************************
   Reading from infifo and writing to outfifo
**********************************************************************/

/* This directory contains infifo and outfifo */
char my_directory[] = "/var/lib/partman";

/* The output FIFO.  We write to it, the clients read. */
FILE *outfifo = NULL;

/* Open the output FIFO.  After this function the global variable
   outfifo can be used for writing. */
void
open_out()
{
        char *str;
        log("Opening outfifo");
        str = xasprintf("%s/outfifo", my_directory);
        outfifo = fopen(str, "w");
        if (outfifo == NULL)
                critical_error("Can't open outfifo");
        free(str);
}

/* Write to the output FIFO.  The arguments are the same as in
   printf. */
#define oprintf(...) \
        ({ \
                char *msg_oprintf; \
                fprintf(outfifo,__VA_ARGS__); \
                fflush(outfifo); \
                msg_oprintf = xasprintf(__VA_ARGS__); \
                log("OUT: %s\n", msg_oprintf); \
                free(msg_oprintf); \
        })

/* The input FIFO.  We read from it, the clients write. */
FILE *infifo = NULL;

/* Open the input FIFO.  After this function the global variable
   infifo can be used for reading */
void
open_in()
{
        char *str;
        log("Opening infifo");
        str = xasprintf("%s/infifo", my_directory);
        infifo = fopen(str, "r");
        if (infifo == NULL)
                critical_error("Can't open infifo");
        free(str);
}

/* Do fscanf from the input FIFO.  The arguments are the same as in
   the function `scanf' */
#define iscanf(...) fscanf(infifo,__VA_ARGS__)

/* Read the remainder of this line from the input FIFO, skipping leading
 * whitespace. Sets *str to NULL if there was no data left in the FIFO (as
 * opposed to merely optional leading whitespace followed by a newline,
 * indicating an empty argument following the whitespace; in that case, set
 * *str to the empty string). Caller is expected to free *str.
 */
void
iscan_line(char **str, int expect_leading_newline)
{
        int c;

        *str = NULL;

        c = fgetc(infifo);
        if (c == EOF)
                return;
        if (c == '\n' && expect_leading_newline) {
                c = fgetc(infifo);
                if (c == EOF)
                        return;
        }
        while (c != EOF && c != '\n') {
                if (isspace((unsigned char) c))
                        c = fgetc(infifo);
                else {
                        ungetc(c, infifo);
                        break;
                }
        }

        if (c == EOF || c == '\n')
                *str = calloc(1, 1);
        else
                iscanf("%a[^\n]", str);
}

void
synchronise_with_client()
{
        char *str;
        FILE *stopfifo;
        str = xasprintf("%s/stopfifo", my_directory);
        stopfifo = fopen(str, "r");
        if (stopfifo == NULL)
                critical_error("Can't open stopfifo for synchronisation");
        free(str);
        fclose(stopfifo);
}

/* This function closes infifo and outfifo.  Then in order to
   synchronise with the clients it opens and closes first outfifo and
   afterwards infifo but in oposite direction -- outfifo for reading
   and infifo for writing. */
void
close_fifos_and_synchronise()
{
        char *str;
        int c;
        log("Closing infifo and outfifo");
        fclose(infifo);
        fclose(outfifo);
        synchronise_with_client();
        str = xasprintf("%s/outfifo", my_directory);
        outfifo = fopen(str, "r");
        if (outfifo == NULL)
                critical_error("Can't open outfifo for synchronisation");
        free(str);
        while (EOF != (c = fgetc(outfifo))) {
        }
        fclose(outfifo);
        synchronise_with_client();
        str = xasprintf("%s/infifo", my_directory);
        infifo = fopen(str, "w");
        if (infifo == NULL)
                critical_error("Can't open infifo for synchronisation");
        free(str);
        fclose(infifo);
        synchronise_with_client();
}

/**********************************************************************
   Timer
**********************************************************************/

bool timer_started = false;

/* Tell the client to open a progress bar. */
void
start_timer()
{
        assert(!timer_started);
        oprintf("Timer\n");
        timer_started = true;
}

/* Tell the client to close the progress bar. */
void
stop_timer()
{
        assert(timer_started);
        oprintf("ready\n");
        timer_started = false;
}

/* Tell the client the fraction of operation done (in permiles). */
void
timer_handler(PedTimer *timer, void *context)
{
        assert(timer_started);
        oprintf("%.0f %s\n", 1000 * timer->frac, timer->state_name);
}

/* Like ped_file_system_create but automaticaly creates PedTimer */
PedFileSystem *
timered_file_system_create(PedGeometry *geom, PedFileSystemType *type)
{
        PedFileSystem *result;
        PedTimer *timer;
        start_timer();
        timer = ped_timer_new(&timer_handler, NULL);
        result = ped_file_system_create(geom, type, timer);
        stop_timer();
        ped_timer_destroy(timer);
        return result;
}

/* Like ped_file_system_check but automaticaly creates PedTimer */
int
timered_file_system_check(PedFileSystem *fs)
{
        int result;
        PedTimer *timer;
        start_timer();
        timer = ped_timer_new(&timer_handler, NULL);
        result = ped_file_system_check(fs, timer);
        stop_timer();
        ped_timer_destroy(timer);
        return result;
}

/* Like ped_file_system_copy but automaticaly creates PedTimer */
PedFileSystem *
timered_file_system_copy(PedFileSystem *fs, PedGeometry *geom)
{
        PedFileSystem *result;
        PedTimer *timer;
        start_timer();
        timer = ped_timer_new(&timer_handler, NULL);
        result = ped_file_system_copy(fs, geom, timer);
        stop_timer();
        ped_timer_destroy(timer);
        return result;
}

/* Like ped_file_system_resize but automaticaly creates PedTimer */
int
timered_file_system_resize(PedFileSystem *fs, PedGeometry *geom)
{
        int result;
        PedTimer *timer;
        start_timer();
        timer = ped_timer_new(&timer_handler, NULL);
        result = ped_file_system_resize(fs, geom, timer);
        stop_timer();
        ped_timer_destroy(timer);
        return result;
}

/**********************************************************************
   Exception handler
**********************************************************************/

/* Generate for the client an exception using the following scenario: */
/*    1. Print `type' in outfifo */
/*    2. Print `message' to be presented to the user. */
/*    3. Print newline to mark the end of the message. */
/*    4. Print the options for the user, one per line and end with an
 *       empty line. */
/*    5. Read from infifo the user response.  This is either
 *       "unhandled" or one of the options from 4. */
/* Arguments: `type' is a string such as "information", "warning",
 * "error", etc., `message' is the text to be presented to the user
 * and `options' is an array of pointers to strings such "Yes", "No",
 * "Cancel", etc.; the last pointer is NULL.  The function returns the
 * index of the option chosen by the user or -1 if the option read in
 * 5. was "unhandled".  The client responses with "unhandled" when the
 * user cancels the debconf dialog or when the dialog was not
 * presented to the user because of the debconf priority. */
int
pseudo_exception(char *type, char *message, char **options)
{
        int i;
        char *str;
        bool timer_was_started = timer_started;
        if (timer_was_started)
                stop_timer();
        oprintf("%s\n", type);
        oprintf("%s\n", message);
        oprintf("\n");
        for (i = 0; options[i] != NULL; i++) {
                oprintf("%s\n", options[i]);
        }
        oprintf("\n");
        if (timer_was_started)
                start_timer();
        iscan_line(&str, 1);
        if (!str)
                critical_error("No data in infifo.");
        if (!strcmp(str, "unhandled")) {
                log("User canceled exception handler");
                return -1;
        }
        for (i = 0; options[i] != NULL; i++)
                if (!strcasecmp(str, options[i])) {
                        free(str);
                        return i;
                }
        critical_error("exception_handler: Bad option: \"%s\"", str);
}

/* The maximal meaningful bit in PedExceptionOption.  In the current
   version of libparted (1.6) this is 7, but let us be safer. */
#define MAXIMAL_OPTION 10
#define POWER_MAXIMAL_OPTION 1024       /* 2 to the MAXIMAL_OPTION */

/* The exception handler for ped_exception_set_handler(). */
PedExceptionOption
exception_handler(PedException *ex)
{
        char *options[MAXIMAL_OPTION + 1];
        int i;
        unsigned bit;
        int response;
        i = 0;
        for (bit = 1; bit <= POWER_MAXIMAL_OPTION; bit = bit << 1) {
                if (bit & ex->options) {
                        options[i] = ped_exception_get_option_string(bit);
                        i++;
                }
        }
        options[i] = NULL;
        response =
            pseudo_exception(ped_exception_get_type_string(ex->type),
                             ex->message, options);
        if (response == -1) {
                log("User canceled exception handler");
                return PED_EXCEPTION_UNHANDLED;
        }
        for (bit = 1; bit <= POWER_MAXIMAL_OPTION; bit = bit << 1) {
                if (bit & ex->options) {
                        char *option;
                        option = ped_exception_get_option_string(bit);
                        if (!strcasecmp(options[response], option)) {
                                return bit;
                        }
                }
        }
        critical_error("exception_handler: Bad option: <%s>",
                       options[response]);
}

/* If we want to temporarily disable the exception handler for some
   commands, we use deactivate_exception_handler() before them and
   activate_exception_handler after them. */

unsigned handler_deactivation_counter = 0;

void
deactivate_exception_handler()
{
        if (handler_deactivation_counter == 0)
                ped_exception_fetch_all();
        handler_deactivation_counter++;
}

void
activate_exception_handler()
{
        assert(handler_deactivation_counter > 0);
        handler_deactivation_counter--;
        if (handler_deactivation_counter == 0)
                ped_exception_leave_all();
}

/**********************************************************************
   Registry of the opened devices
**********************************************************************/

struct devdisk {
        char *name;
        PedDevice *dev;
        PedDisk *disk;
        bool changed;
        PedGeometry *geometries;
        int number_geometries;
        enum alignment alignment;
};

/* We store the accessed devices from `devices[0]' to
   `devices[number_devices - 1]'.  `number_devices' is a small number
   so there is no need to use a hash table or some more advanced data
   structure.  Moreover a version of parted_server using the hash
   implementation from libdebian-installer was 200 bytes longer. */

unsigned number_devices = 0;
struct devdisk *devices = NULL;

/* The size of the array `devices' */
unsigned allocated_devices = 0;

/* index = index_of_name(name);
 * 0 == strcmp(devices[index].name, name)
 *
 * Be careful not to write code like devices[index_of_name(name)].
 * This function may change devices, so a sequence point is required.
 */
int
index_of_name(const char *name)
{
        int i;
        assert(name != NULL);
        for (i = 0; i < number_devices; i++)
                if (0 == strcmp(name, devices[i].name))
                        return i;
        if (number_devices == allocated_devices) {
                allocated_devices = 1 + 2 * allocated_devices;
                devices = realloc(devices,
                                  sizeof(struct devdisk[allocated_devices]));
                if (devices == NULL)
                        critical_error("Cannot allocate memory.");
        }
        number_devices++;
        devices[i].name = strdup(name);
        if (NULL == devices[i].name)
                critical_error("Cannot allocate memory.");
        devices[i].dev = NULL;
        devices[i].disk = NULL;
        devices[i].changed = false;
        devices[i].geometries = NULL;
        devices[i].number_geometries = 0;
        devices[i].alignment = alignment;
        return i;
}

int
index_of_device(const PedDevice *dev)
{
        int i;
        assert(dev != NULL);
        for (i = 0; i < number_devices; i++)
                if (dev == devices[i].dev)
                        return i;
        return -1;
}

/* Mangle fstype to abstract changes in parted code */
void
mangle_fstype_name(char **fstype)
{
        if (!strcasecmp(*fstype, "linux-swap")) {
                free(*fstype);
                *fstype = strdup("linux-swap(v1)");
        }
}

/* Return the PedDevice of `name'. */
PedDevice *
device_named(const char *name)
{
        int index = index_of_name(name);
        return devices[index].dev;
}


/* Return the PedDisk of `name'. */
PedDisk *
disk_named(const char *name)
{
        int index = index_of_name(name);
        return devices[index].disk;
}

/* True iff the PedDevice of `name' is not NULL. */
bool
device_opened(const char *name)
{
        return NULL != device_named(name);
}

/* Set the PedDevice of `name' to be `dev'.  The old PedDevice of
   `name' (if any) will be ped_device_destroy-ed. */
void
set_device_named(const char *name, PedDevice *dev)
{
        PedDevice *old_dev;
        int index = index_of_name(name);
        assert(disk_named(name) == NULL);
        old_dev = device_named(name);
        if (NULL != old_dev)
                ped_device_destroy(old_dev);
        devices[index].dev = dev;
}

void
remember_geometries_named(const char *name)
{
        static unsigned const max_partition = 50;
        PedGeometry *geometries;
        PedDisk *disk;
        int last;
        PedPartition *part;
        int index = index_of_name(name);
        geometries = devices[index].geometries;
        if (NULL != geometries)
                free(geometries);
        disk = disk_named(name);
        if (disk == NULL) {
                devices[index].geometries = NULL;
                devices[index].number_geometries = 0;
        } else {
                geometries = malloc(sizeof(PedGeometry[max_partition]));
                last = 0;
                for (part = NULL;
                     NULL != (part = ped_disk_next_partition(disk, part));) {
                        if (PED_PARTITION_EXTENDED & part->type)
                                continue;
                        if (PED_PARTITION_METADATA & part->type)
                                continue;
                        if (PED_PARTITION_FREESPACE & part->type)
                                continue;
                        ped_geometry_init(geometries + last,
                                          disk->dev,
                                          part->geom.start, part->geom.length);
                        last = last + 1;
                        if (last >= max_partition)
                                critical_error("Too many partitions");
                }
                geometries = realloc(geometries, sizeof(PedGeometry[last]));
                if (last != 0 && geometries == NULL)
                        critical_error("Cannot allocate memory");
                devices[index].geometries = geometries;
                devices[index].number_geometries = last;
        }
}

/* Set the PedDisk of `name' to be `disk'.  The old PedDisk of `name'
   (if any) will be ped_disk_destroy-ed. */
void
set_disk_named(const char *name, PedDisk *disk)
{
        PedDisk *old_disk;
        int index = index_of_name(name);
        assert(device_opened(name));
        old_disk = disk_named(name);
        if (NULL != old_disk)
                ped_disk_destroy(old_disk);
        devices[index].disk = disk;
        if (disk) {
                if (ped_disk_is_flag_available(disk,
                                               PED_DISK_CYLINDER_ALIGNMENT))
                        ped_disk_set_flag(disk, PED_DISK_CYLINDER_ALIGNMENT,
                                          devices[index].alignment ==
                                                ALIGNMENT_CYLINDER);
                else if (0 != strcmp(disk->type->name, "gpt"))
                        /* If the PED_DISK_CYLINDER_ALIGNMENT flag isn't
                           available, then there are two alternatives:
                           either the disk label format is too old to know
                           about modern alignment (#579948), or it's too new
                           to care about cylinder alignment (#674894).  The
                           only format currently known to fall into the
                           latter category is GPT; for the others, we should
                           assume that *only* cylinder alignment is
                           available. */
                        devices[index].alignment = ALIGNMENT_CYLINDER;
        }
}

/* True if the partition doesn't exist on the storage device */
bool
named_partition_is_virtual(const char *name, PedSector start, PedSector end)
{
        PedGeometry *geometries;
        int i;
        int last;
        int index = index_of_name(name);
        log("named_partition_is_virtual(%s,%lli,%lli)", name, start, end);
        geometries = devices[index].geometries;
        last = devices[index].number_geometries;
        if (NULL == geometries) {
                log("yes");
                return true;
        }
        for (i = 0; i < last; i++) {
                if (start == geometries[i].start && end == geometries[i].end) {
                        log("no");
                        return false;
                }
        }
        log("yes");
        return true;
}

/* True iff the partition table of `name' has been changed. */
bool
named_is_changed(const char *name)
{
        int index = index_of_name(name);
        return devices[index].changed;
}

/* Note the partition table of `name' as having been changed. */
void
change_named(const char *name)
{
        int index = index_of_name(name);
        log("Note %s as changed", name);
        devices[index].changed = true;
}

/* Note the partition table of `name' as unchanged. */
void
unchange_named(const char *name)
{
        int index = index_of_name(name);
        log("Note %s as unchanged", name);
        devices[index].changed = false;
        remember_geometries_named(name);
}

/* Return the desired alignment for dev. */
enum alignment
alignment_of_device(const PedDevice *dev)
{
        int index = index_of_device(dev);
        if (index >= 0)
                return devices[index].alignment;
        else
                return ALIGNMENT_CYLINDER;
}


/**********************************************************************
   Partition creation
**********************************************************************/

/* True if `disk' has already an extended partition. */
bool
has_extended_partition(PedDisk *disk)
{
        assert(disk != NULL);
        return ped_disk_extended_partition(disk) != NULL;
}

void
set_alignment(void)
{
        const char *align_env = getenv("PARTMAN_ALIGNMENT");

        if (align_env && !strcmp(align_env, "cylinder"))
                alignment = ALIGNMENT_CYLINDER;
        else if (align_env && !strcmp(align_env, "minimal"))
                alignment = ALIGNMENT_MINIMAL;
        else
                alignment = ALIGNMENT_OPTIMAL;
}

/* Get a constraint suitable for partition creation on this disk. */
PedConstraint *
partition_creation_constraint(const PedDevice *cdev)
{
        PedSector md_grain_size;
        PedConstraint *aligned, *gap_at_end, *combined;
        PedGeometry gap_at_end_geom;
        enum alignment cdev_alignment = alignment_of_device(cdev);

        if (cdev_alignment == ALIGNMENT_OPTIMAL)
                aligned = ped_device_get_optimal_aligned_constraint(cdev);
        else if (cdev_alignment == ALIGNMENT_MINIMAL)
                aligned = ped_device_get_minimal_aligned_constraint(cdev);
        else
                aligned = ped_device_get_constraint(cdev);
        if (cdev->type == PED_DEVICE_DM)
                return aligned;

        /* We must ensure that there's a small gap at the end, since
         * otherwise MD 0.90 metadata at the end of a partition may confuse
         * mdadm into believing that both the disk and the partition
         * represent the same RAID physical volume.  0.90 metadata is
         * located by rounding the device size down to a 64K boundary and
         * subtracting 64K (1.x metadata is either between 8K and 12K from
         * the end, or at or near the start), so we round down to 64K and
         * subtract one more sector.
         */
        md_grain_size = 65536 / cdev->sector_size;
        if (md_grain_size == 0)
                md_grain_size = 1;
        ped_geometry_init(&gap_at_end_geom, cdev, 0,
                          ped_round_down_to(cdev->length, md_grain_size) - 1);
        gap_at_end = ped_constraint_new(ped_alignment_any, ped_alignment_any,
                                        &gap_at_end_geom, &gap_at_end_geom,
                                        1, cdev->length);

        combined = ped_constraint_intersect(aligned, gap_at_end);

        ped_constraint_destroy(gap_at_end);
        ped_constraint_destroy(aligned);
        return combined;
}

/* Add to `disk' a new extended partition starting at `start' and
   ending at `end' */
PedPartition *
add_extended_partition(PedDisk *disk, PedSector start, PedSector end)
{
        PedPartition *extended;
        assert(disk != NULL);
        assert(!has_extended_partition(disk));
        /* ext2 has no sense, but parted requires some argument */
        extended = ped_partition_new(disk, PED_PARTITION_EXTENDED,
                                     ped_file_system_type_get("ext2"),
                                     start, end);
        if (!extended) {
                return NULL;
        }
        if (!ped_disk_add_partition(disk, extended,
                                    ped_constraint_any(disk->dev))) {
                ped_partition_destroy(extended);
                return NULL;
        }
        return extended;
}

/* Makes the extended partition as large as possible. */
void
maximize_extended_partition(PedDisk *disk)
{
        PedPartition *extended;
        assert(disk != NULL);
        assert(has_extended_partition(disk));
        extended = ped_disk_extended_partition(disk);
        ped_disk_maximize_partition(disk, extended,
                                    ped_constraint_any(disk->dev));
}

/* Makes the extended partition as small as possible or removes it if
   there are no logical partitions. */
void
minimize_extended_partition(PedDisk *disk)
{
        assert(disk != NULL);
        if (0 != strcmp(disk->type->name, "dvh"))
                ped_disk_minimize_extended_partition(disk);
}

/* Add to `disk' a new primary partition with file system `fs_type'
   starting at `start' and ending at `end'.  Note: The partition is
   not formatted, but only created. */
PedPartition *
add_primary_partition(PedDisk *disk, PedFileSystemType *fs_type,
                      PedSector start, PedSector end)
{
        PedPartition *part;
        assert(disk != NULL);
        log("add_primary_partition(disk(%lli),%lli-%lli)",
            disk->dev->length, start, end);
        if (has_extended_partition(disk)) {
                /* Minimise the extended partition.  If there is an
                   extended partition, but no logical partitions, this
                   command removes the extended partition. */
                log("Minimizing extended partition.");
                minimize_extended_partition(disk);
        }
        part = ped_partition_new(disk, 0, fs_type, start, end);
        if (part == NULL) {
                log("Cannot create new primary partition.");
                return NULL;
        }
        if (!ped_disk_add_partition(disk, part, partition_creation_constraint(disk->dev))) {
                log("Cannot add the primary partition to partition table.");
                ped_partition_destroy(part);
                return NULL;
        }
        return part;
}

/* Add to `disk' a new logical partition with file system `fs_type'
   starting at `start' and ending at `end'.  Note: The partition is
   not formatted, but only created. */
PedPartition *
add_logical_partition(PedDisk *disk, PedFileSystemType *fs_type,
                      PedSector start, PedSector end)
{
        PedPartition *part;
        assert(disk != NULL && fs_type != NULL);
        if (!has_extended_partition(disk))
                if (!add_extended_partition(disk, start, end))
                        return NULL;
        maximize_extended_partition(disk);
        part = ped_partition_new(disk, PED_PARTITION_LOGICAL, fs_type,
                                 start, end);
        if (part == NULL) {
                minimize_extended_partition(disk);
                return NULL;
        }
        if (!ped_disk_add_partition(disk, part, partition_creation_constraint(disk->dev))) {
                ped_partition_destroy(part);
                minimize_extended_partition(disk);
                return NULL;
        }
        minimize_extended_partition(disk);
        return part;
}

/* Resizes `part' from `disk' to start from `start' and end at `end'.
   If `open_filesystem' is true and `disk' contains some file system
   then it is also resized.  Returns true on success. */
bool
resize_partition(PedDisk *disk, PedPartition *part,
                 PedSector start, PedSector end, bool open_filesystem)
{
        PedFileSystem *fs;
        PedConstraint *constraint;
        PedSector old_start, old_end;
        bool result;
        log("resize_partition(openfs=%s)", open_filesystem ? "true" : "false");
        old_start = (part->geom).start;
        old_end = (part->geom).end;
        if (old_start == start && old_end == end)
                return true;
        if (open_filesystem) {
                deactivate_exception_handler();
                fs = ped_file_system_open(&(part->geom));
                activate_exception_handler();
                log("opened file system: %s", NULL != fs ? "yes" : "no");
                if (NULL != fs && (fs->geom->start < (part->geom).start
                                   || fs->geom->end > (part->geom).end)) {
                        ped_file_system_close(fs);
                        fs = NULL;
                }
                if (NULL == fs && NULL != ped_file_system_probe(&(part->geom)))
                        return false;
                if (NULL != fs)
                        constraint = ped_file_system_get_resize_constraint(fs);
                else
                        constraint = ped_constraint_any(disk->dev);
        } else {
                PedFileSystemType *fs_type;
                PedGeometry *fs_geom;
                PedAlignment start_align;
                PedGeometry full_dev;
                fs = NULL;
                fs_type = ped_file_system_probe(&(part->geom));
                log("probed file system: %s", NULL != fs_type ? "yes" : "no");
                if (NULL != fs_type)
                        fs_geom = ped_file_system_probe_specific(fs_type,
                                                                 &part->geom);
                else
                        fs_geom = NULL;
                if (NULL != fs_geom && (fs_geom->start < (part->geom).start
                                        || fs_geom->end > (part->geom).end)) {
                        log("broken filesystem detected");
                        ped_geometry_destroy(fs_geom);
                        fs_geom = NULL;
                }
                if (NULL == fs_geom && NULL != fs_type)
                        return false;
                if (NULL != fs_geom) {
                        /* We cannot resize or move the fs but we can
                         * move the end of the partition so long as it
                         * contains the whole fs.
                         */
                        if (ped_alignment_init(&start_align, fs_geom->start, 0)
                            && ped_geometry_init(&full_dev, disk->dev,
                                                 0, disk->dev->length - 1)) {
                                constraint = ped_constraint_new(
                                        &start_align,
                                        ped_alignment_any,
                                        &full_dev, &full_dev,
                                        fs_geom->length,
                                        disk->dev->length);
                        } else {
                                constraint = NULL;
                        }
                        ped_geometry_destroy(fs_geom);
                } else {
                        constraint = ped_constraint_any(disk->dev);
                }
        }
        if (NULL == constraint) {
                log("failed to get resize constraint");
                if (NULL != fs)
                        ped_file_system_close(fs);
                return false;
        }
        log("try to check the file system for errors");
        if (NULL != fs && !timered_file_system_check(fs)) {
                /* TODO: inform the user. */
                log("uncorrected errors");
                ped_file_system_close(fs);
                return false;
        }
        log("successfully checked");
        if (part->type & PED_PARTITION_LOGICAL)
                maximize_extended_partition(disk);
        if (!ped_disk_set_partition_geom(disk, part, constraint, start, end))
                result = false;
        else if (NULL == fs)
                result = true;
        else if (timered_file_system_resize(fs, &(part->geom))) {
                result = true;
        } else {
                ped_disk_set_partition_geom(disk, part,
                                            ped_constraint_any(disk->dev),
                                            old_start, old_end);
                result = false;
        }
        if (fs != NULL)
                ped_file_system_close(fs);
        if (part->type & PED_PARTITION_LOGICAL)
                minimize_extended_partition(disk);
        return result;
        /* TODO: not sure if constraints here should be
           ped_constraint_destroy-ed.  Let's be safe. */
}

/**********************************************************************
   Getting info
**********************************************************************/

/* true when it is possible to create a primary partition in `space'.
   `space' must be a free space in `disk'. */
bool
possible_primary_partition(PedDisk *disk, PedPartition *space)
{
        bool result;
        assert(disk != NULL);
        assert(space != NULL && PED_PARTITION_FREESPACE & space->type);
        deactivate_exception_handler();
        result = (!(PED_PARTITION_LOGICAL & space->type)
                  && (ped_disk_get_primary_partition_count(disk)
                      < ped_disk_get_max_primary_partition_count(disk)));
        activate_exception_handler();
        return result;
}

/* true when it is possible to create an extended partition in `space'.
   `space' must be a free space in `disk'. */
bool
possible_extended_partition(PedDisk *disk, PedPartition *space)
{
        bool result;
        assert(disk != NULL);
        assert(space != NULL && PED_PARTITION_FREESPACE & space->type);
        deactivate_exception_handler();
        result = (ped_disk_type_check_feature(disk->type,
                                              PED_DISK_TYPE_EXTENDED)
                  && !has_extended_partition(disk)
                  && possible_primary_partition(disk, space));
        activate_exception_handler();
        return result;
}

/* true if the last sector of `part1' is phisicaly before the first
   sector of `part2'. */
inline bool
partition_before(PedPartition *part1, PedPartition *part2)
{
        return (part1->geom).end < (part2->geom).start;
}

/* true when it is possible to create a logical partition in `space'.
   `space' must be a free space in `disk'. */
bool
possible_logical_partition(PedDisk *disk, PedPartition *space)
{
        PedPartition *extended, *part;
        bool result;
        assert(disk != NULL);
        assert(space != NULL && (PED_PARTITION_FREESPACE & space->type));
        deactivate_exception_handler();
        if (!has_extended_partition(disk))
                result = possible_extended_partition(disk, space);
        else {
                extended = ped_disk_extended_partition(disk);
                result = true;
                part = ped_disk_next_partition(disk, NULL);
                while (result && NULL != part) {
                        if (ped_partition_is_active(part)
                            && ((partition_before(space, part)
                                 && partition_before(part, extended))
                                || (partition_before(extended, part)
                                    && partition_before(part, space)))) {
                                /* There is a primary partition between us
                                   and the extended partition. */
                                assert(!(PED_PARTITION_LOGICAL & part->type));
                                result = false;
                        }
                        part = ped_disk_next_partition(disk, part);
                }
        }
        activate_exception_handler();
        return result;
}

/* Finds in `disk' a partition with id `id' and returns it. */
PedPartition *
partition_with_id(PedDisk *disk, char *id)
{
        PedPartition *part;
        long long start, end;
        long long start_sector, end_sector;
        assert(id != NULL);
        log("partition_with_id(%s)", id);
        if (2 != sscanf(id, "%lli-%lli", &start, &end))
                critical_error("Bad id %s", id);
        start_sector = start / disk->dev->sector_size;
        end_sector = (end - disk->dev->sector_size + 1) / disk->dev->sector_size;
        if (disk == NULL)
                return NULL;
        for (part = NULL;
             NULL != (part = ped_disk_next_partition(disk, part));)
                if ((part->geom).start == start_sector
                    && (part->geom).end == end_sector)
                        return part;
        return NULL;
}

/* Returns informational string about `part' from `disk'.  Format:*/
/* Number<TAB>id<TAB>length<TAB>type<TAB>fs<TAB>path<TAB>name */
char *
partition_info(PedDisk *disk, PedPartition *part)
{
        char const *type;
        char const *fs;
        char *path;
        char const *name;
        char *result;
        assert(disk != NULL && part != NULL);
        if (PED_PARTITION_FREESPACE & part->type) {
                bool possible_primary = possible_primary_partition(disk, part);
                bool possible_logical = possible_logical_partition(disk, part);
                if (possible_primary)
                        if (possible_logical)
                                type = "pri/log";
                        else
                                type = "primary";
                else if (possible_logical)
                        type = "logical";
                else
                        type = "unusable";
        } else if (PED_PARTITION_LOGICAL & part->type)
                type = "logical";
        else
                type = "primary";

        if (PED_PARTITION_FREESPACE & part->type)
                fs = "free";
        else if (PED_PARTITION_METADATA & part->type)
                fs = "label";
        else if (PED_PARTITION_EXTENDED & part->type)
                fs = "extended";
        else if (NULL == (part->fs_type))
                fs = "unknown";
        else if (0 == strncmp(part->fs_type->name, "linux-swap", 10))
                fs = "linux-swap";
        else
                fs = part->fs_type->name;

        if (0 == strcmp(disk->type->name, "loop")) {
                path = strdup(disk->dev->path);
/*         } else if (0 == strcmp(disk->type->name, "dvh")) { */
/*                 PedPartition *p; */
/*                 int count = 1; */
/*                 int number_offset; */
/*                 for (p = NULL; */
/*                      NULL != (p = ped_disk_next_partition(disk, p));) { */
/*                         if (PED_PARTITION_METADATA & p->type) */
/*                                 continue; */
/*                         if (PED_PARTITION_FREESPACE & p->type) */
/*                                 continue; */
/*                         if (PED_PARTITION_LOGICAL & p->type) */
/*                                 continue; */
/*                         if (part->num > p->num) */
/*                                 count++; */
/*                 } */
/*                 path = ped_partition_get_path(part); */
/*                 number_offset = strlen(path); */
/*                 while (number_offset > 0 && isdigit(path[number_offset-1])) */
/*                         number_offset--; */
/*                 sprintf(path + number_offset, "%i", count); */
        } else {
                path = ped_partition_get_path(part);
        }
        if (ped_disk_type_check_feature(part->disk->type,
                                        PED_DISK_TYPE_PARTITION_NAME)
            && ped_partition_is_active(part))
                name = ped_partition_get_name(part);
        else
                name = "";
        result = xasprintf("%i\t%lli-%lli\t%lli\t%s\t%s\t%s\t%s",
                           part->num,
                           (part->geom).start * disk->dev->sector_size,
                           (part->geom).end * disk->dev->sector_size + disk->dev->sector_size - 1,
                           (part->geom).length * disk->dev->sector_size, type, fs, path, name);
        free(path);
        return result;
}

/* Print in `dumpfile' information about the `dev', `disk' and the
   partitions in `disk'. */
void
dump_info(FILE *dumpfile, PedDevice *dev, PedDisk *disk)
{
        PedPartition *part;
        deactivate_exception_handler();
        if (dev == NULL) {
                fprintf(dumpfile, "Device: no");
                activate_exception_handler();
                return;
        }
        fprintf(dumpfile, "Device: yes\n");
        fprintf(dumpfile, "Model: %s\n", dev->model);
        fprintf(dumpfile, "Path: %s\n", dev->path);
        fprintf(dumpfile, "Sector size: %lli\n", dev->sector_size);
        fprintf(dumpfile, "Sectors: %lli\n", dev->length);
        fprintf(dumpfile, "Sectors/track: %i\n", dev->bios_geom.sectors);
        fprintf(dumpfile, "Heads: %i\n", dev->bios_geom.heads);
        fprintf(dumpfile, "Cylinders: %i\n", dev->bios_geom.cylinders);
        if (disk == NULL) {
                fprintf(dumpfile, "Partition table: no\n");
                activate_exception_handler();
                return;
        }
        fprintf(dumpfile, "Partition table: yes\n");
        fprintf(dumpfile, "Type: %s\n", disk->type->name);
        fprintf(dumpfile, "Partitions: #\tid\tlength\ttype\tfs\tpath\tname\n");
        for (part = NULL;
             NULL != (part = ped_disk_next_partition(disk, part));) {
                /* TODO: there is the same code in command_get_chs */
                long long cylinder_size, track_size;
                long long start, end;
                long long cyl_start, cyl_end;
                long long head_start, head_end;
                long long sec_start, sec_end;
                char *part_info = partition_info(disk, part);
                track_size = dev->bios_geom.sectors;
                cylinder_size = track_size * dev->bios_geom.heads;
                start = (part->geom).start;
                end = (part->geom).end;
                cyl_start = start / cylinder_size;
                cyl_end = end / cylinder_size;
                start = start % cylinder_size;
                end = end % cylinder_size;
                head_start = start / track_size;
                head_end = end / track_size;
                sec_start = start % track_size;
                sec_end = end % track_size;
                fprintf(dumpfile,
                        "(%lli,%lli,%lli)\t(%lli,%lli,%lli)\t%s\n",
                        cyl_start, head_start, sec_start, cyl_end,
                        head_end, sec_end, part_info);
                free(part_info);
        }
        fprintf(dumpfile, "Dump finished.\n");
        activate_exception_handler();
}

/**********************************************************************
   Commands
*********************************************************************/

PedDevice *dev;
PedDisk *disk;
char *device_name;

void
scan_device_name()
{
        if (device_name != NULL)
                free(device_name);
        if (1 != iscanf("%as", &device_name))
                critical_error("Expected device identifier.");
        dev = device_named(device_name);
        disk = disk_named(device_name);
}

void
command_quit()
{
        log("Quitting");
        fflush(logfile);
        exit(0);
}

void
command_open()
{
        log("command_open()");
        char *device;
        scan_device_name();
        if (1 != iscanf("%as", &device))
                critical_error("Expected device name.");
        log("Request to open %s", device_name);
        open_out();
        if (device_opened(device_name)) {
                static char *only_ok[] = { "OK", NULL };
                log("Warning: the device is already opened");
                pseudo_exception("Warning",
                                 "The device is already opened.", only_ok);
        } else {
                set_device_named(device_name, ped_device_get(device));
        }
        oprintf("OK\n");
        if (NULL != device_named(device_name)) {
                oprintf("OK\n");
                deactivate_exception_handler();
                set_disk_named(device_name,
                               ped_disk_new(device_named(device_name)));
                unchange_named(device_name);
                activate_exception_handler();
        } else
                oprintf("failed\n");
        free(device);
}

void
command_close()
{
        log("command_close()");
        scan_device_name();
        open_out();
        if (!device_opened(device_name)) {
                static char *only_cancel[] = { "Cancel", NULL };
                pseudo_exception("Error",
                                 "The device is not opened!", only_cancel);
        }
        set_disk_named(device_name, NULL);
        set_device_named(device_name, NULL);
        oprintf("OK\n");
}

void
command_opened()
{
        log("command_opened()");
        scan_device_name();
        open_out();
        oprintf("OK\n");
        if (NULL != device_named(device_name)) {
                oprintf("yes\n");
        } else {
                oprintf("no\n");
        }
}

void
command_virtual()
{
        char *id;
        PedPartition *part;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_virtual()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("is virtual partition with id %s", id);
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        if (named_partition_is_virtual(device_name,
                                       part->geom.start, part->geom.end)) {
                oprintf("yes\n");
        } else {
                oprintf("no\n");
        }
        free(id);
}

void
command_disk_unchanged()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_disk_unchanged(%s)", device_name);
        open_out();
        oprintf("OK\n");
        unchange_named(device_name);
}

void
command_is_changed()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_is_changed(%s)", device_name);
        open_out();
        oprintf("OK\n");
        if (named_is_changed(device_name))
                oprintf("yes\n");
        else
                oprintf("no\n");
}

/* Print in /var/log/partition_dump information about the disk, the
   partition table and the partitions. */
void
command_dump()
{
        FILE *dumpfile;
        static char *only_cancel[] = { "Cancel", NULL };
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_dump()");
        open_out();
        dumpfile = fopen("/var/log/partition_dump", "a+");
        if (dumpfile == NULL) {
                pseudo_exception("Error",
                                 "Can't open /var/log/partition_dump",
                                 only_cancel);
        } else {
                dump_info(dumpfile, dev, disk);
                fclose(dumpfile);
        }
        oprintf("OK\n");
}

void
command_commit()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_commit()");
        open_out();
        if (disk != NULL && named_is_changed(device_name))
                ped_disk_commit(disk);
        unchange_named(device_name);
        oprintf("OK\n");
}

void
command_undo()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_undo()");
        open_out();
        log("Rereading disk label");
        deactivate_exception_handler();
        if (dev != NULL) {
                set_disk_named(device_name, NULL);
                set_disk_named(device_name, ped_disk_new(dev));
        }
        activate_exception_handler();
        unchange_named(device_name);
        oprintf("OK\n");
}

void
command_partitions()
{
        PedPartition *part;
        PedConstraint *creation_constraint;
        PedSector grain_size;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_partitions()");
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        if (disk == NULL) {
                log("No partitions");
                /* No label, hence no partitions.  When there is a
                   label, there is at least one partition because the
                   free space counts as a partition. */
                oprintf("\n");
                activate_exception_handler();
                return;
        }
        if (has_extended_partition(disk))
                minimize_extended_partition(disk);
        creation_constraint = partition_creation_constraint(dev);
        grain_size = creation_constraint->start_align->grain_size;
        ped_constraint_destroy(creation_constraint);
        for (part = NULL;
             NULL != (part = ped_disk_next_partition(disk, part));) {
                char *part_info;
                if (PED_PARTITION_EXTENDED & part->type)
                        continue;
                if (PED_PARTITION_METADATA & part->type)
                        continue;
                /* Undoubtedly the following operator is a hack.
                   Libparted tries to align the partitions at
                   appropriate boundaries but despite this it sometimes
                   reports free spaces due to aligning and even
                   allows creation of unaligned partitions in these
                   free spaces.  I am not sure if this is a bug or a
                   feature of libparted. */
                if (PED_PARTITION_FREESPACE & part->type
                    && ped_disk_type_check_feature(disk->type,
                                                   PED_DISK_TYPE_EXTENDED)
                    && ((part->geom).length
                        < dev->bios_geom.sectors * grain_size))
                        continue;
                /* Another hack :) */
                if (0 == strcmp(disk->type->name, "dvh")
                    && PED_PARTITION_LOGICAL & part->type)
                        continue;
                part_info = partition_info(disk, part);
                oprintf("%s\n", part_info);
                free(part_info);
        }
        log("Partitions printed");
        /* An empty line after the last partition */
        oprintf("\n");
        activate_exception_handler();
}

void
command_partition_info()
{
        char *id;
        PedPartition *part;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_partition_info()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("command_partition_info: info for partition with id %s", id);
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        deactivate_exception_handler();
        if (part == NULL) {
                log("command_partition_info: no such a partitions");
                oprintf("\n");
        } else {
                char *part_info;
                log("command_partition_info: partition found");
                part_info = partition_info(disk, part);
                oprintf("%s\n", part_info);
                free(part_info);
        }
        free(id);
        activate_exception_handler();
}

void
command_get_chs()
{
        char *id;
        PedPartition *part;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_get_chs()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("command_get_chs: Cyl/Head/Sec for partition with id %s", id);
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        deactivate_exception_handler();
        if (part == NULL) {
                log("command_get_chs: no such a partitions");
                oprintf("\n");
        } else {
                /* TODO: there is the same code in dump_info */
                long long cylinder_size, track_size;
                long long start, end;
                long long cyl_start, cyl_end;
                long long head_start, head_end;
                long long sec_start, sec_end;
                log("command_get_chs: partition found");
                track_size = dev->bios_geom.sectors;
                cylinder_size = track_size * dev->bios_geom.heads;
                start = (part->geom).start;
                end = (part->geom).end;
                cyl_start = start / cylinder_size;
                cyl_end = end / cylinder_size;
                start = start % cylinder_size;
                end = end % cylinder_size;
                head_start = start / track_size;
                head_end = end / track_size;
                sec_start = start % track_size;
                sec_end = end % track_size;
                oprintf("%lli\t%lli\t%lli\t%lli\t%lli\t%lli\n",
                        cyl_start, head_start, sec_start,
                        cyl_end, head_end, sec_end);
        }
        free(id);
        activate_exception_handler();
}

void
command_label_types()
{
        PedDiskType *type = NULL;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_label_types()");
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        while (NULL != (type = ped_disk_type_get_next(type))) {
                oprintf("%s\n", type->name);
        }
        oprintf("\n");
        activate_exception_handler();
}

void
command_valid_flags()
{
        char *id;
        PedPartition *part;
        PedPartitionFlag flag;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_valid_flags()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        deactivate_exception_handler();
        if (part == NULL || !ped_partition_is_active(part)) {
                log("No such active partition: %s", id);
        } else {
                log("Partition found (%s)", id);
                for (flag = 0; 0 != (flag = ped_partition_flag_next(flag));)
                        if (ped_partition_is_flag_available(part, flag))
                                oprintf("%s\n",
                                        ped_partition_flag_get_name(flag));
        }
        oprintf("\n");
        free(id);
        activate_exception_handler();
}

void
command_get_flags()
{
        char *id;
        PedPartition *part;
        PedPartitionFlag flag;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_get_flags()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        part = partition_with_id(disk, id);
        if (part == NULL || !ped_partition_is_active(part))
                critical_error("No such active partition: %s", id);
        log("Partition found (%s)", id);
        oprintf("OK\n");
        deactivate_exception_handler();
        for (flag = 0; 0 != (flag = ped_partition_flag_next(flag));)
                if (ped_partition_is_flag_available(part, flag)
                    && ped_partition_get_flag(part, flag))
                        oprintf("%s\n", ped_partition_flag_get_name(flag));
        oprintf("\n");
        free(id);
        activate_exception_handler();
}

void
command_set_flags()
{
        char *id, *str;
        PedPartition *part;
        PedPartitionFlag first, last, flag;
        bool *states;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_set_flags()");
        change_named(device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        part = partition_with_id(disk, id);
        if (part == NULL || !ped_partition_is_active(part))
                critical_error("No such active partition: %s", id);
        log("Partition found (%s)", id);
        oprintf("OK\n");
        deactivate_exception_handler();
        first = ped_partition_flag_next(0);
        last = first - 1;
        for (flag = first; flag != 0; flag = ped_partition_flag_next(flag))
                last = flag;
        states = malloc(sizeof(bool[last - first + 1]));
        for (flag = first; flag <= last; flag++)
                states[flag - first] = false;
        while (1) {
                iscan_line(&str, 1);
                if (!str)
                        critical_error("No data in infifo!");
                if (!strcmp(str, "NO_MORE"))
                        break;
                log("Processing flag %s", str);
                flag = ped_partition_flag_get_by_name(str);
                if (flag >= first && flag <= last) {
                        log("The flag set true.");
                        states[flag - first] = true;
                }
                free(str);
        }
        free(str);
        for (flag = 0; 0 != (flag = ped_partition_flag_next(flag));)
                if (ped_partition_is_flag_available(part, flag))
                        ped_partition_set_flag(part, flag,
                                               states[flag - first]);
        free(states);
        activate_exception_handler();
        free(id);
}

void
command_uses_names()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_uses_names()");
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        if (ped_disk_type_check_feature(disk->type,
                                        PED_DISK_TYPE_PARTITION_NAME))
                oprintf("yes\n");
        else
                oprintf("no\n");
        activate_exception_handler();
}

void
command_set_name()
{
        char *id, *name;
        PedPartition *part;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_set_name()");
        change_named(device_name);
        if (!ped_disk_type_check_feature(disk->type,
                                         PED_DISK_TYPE_PARTITION_NAME))
                critical_error("This label doesn't support partition names.");
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        part = partition_with_id(disk, id);
        if (part == NULL || !ped_partition_is_active(part))
                critical_error("No such active partition: %s", id);
        log("Partition found (%s)", id);
        iscan_line(&name, 0);
        if (!name)
                critical_error("No data in infifo!");
        log("Changing name to %s", name);
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        ped_partition_set_name(part, name);
        free(name);
        free(id);
        activate_exception_handler();
}

void
command_get_max_primary()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_get_max_primary()");
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        if (disk != NULL && disk->type != NULL)
                oprintf("%d\n",
                        ped_disk_get_max_primary_partition_count(disk));
        else
                oprintf("\n");
        activate_exception_handler();
}

void
command_uses_extended()
{
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_uses_extended()");
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        if (disk != NULL && disk->type != NULL
            && ped_disk_type_check_feature(disk->type, PED_DISK_TYPE_EXTENDED)
            && 0 != strcmp(disk->type->name, "dvh"))
                oprintf("yes\n");
        else
                oprintf("no\n");
        activate_exception_handler();
}

void
command_file_system_types()
{
        PedFileSystemType *type;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_file_system_types()");
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        for (type = NULL;
             NULL != (type = ped_file_system_type_get_next(type));)
                oprintf("%s\n", type->name);
        oprintf("\n");
        activate_exception_handler();
}

void
command_get_file_system()
{
        char *id;
        PedPartition *part;
        PedFileSystemType *fstype;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_get_file_system()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("command_get_file_system: File system for partition %s", id);
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        if (named_partition_is_virtual(device_name,
                                       part->geom.start, part->geom.end)) {
                oprintf("none\n");
        } else {
                deactivate_exception_handler();
                fstype = ped_file_system_probe(&(part->geom));
                if (fstype == NULL) {
                        oprintf("none\n");
                } else {
                        if (0 == strncmp(part->fs_type->name, "linux-swap", 10))
                                oprintf("linux-swap\n");
                        else
                                oprintf("%s\n", fstype->name);
                }
                free(id);
                activate_exception_handler();
        }
}

void
command_change_file_system()
{
        char *id;
        PedPartition *part;
        char *s_fstype;
        PedFileSystemType *fstype;
        PedPartitionFlag flag;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        open_out();
        if (2 != iscanf("%as %as", &id, &s_fstype))
                critical_error("Expected partition id and file system");
        log("command_change_file_system(%s,%s)", id, s_fstype);
        part = partition_with_id(disk, id);
        if (part == NULL) {
                critical_error("Partition not found: %s", id);
        }
        free(id);

        mangle_fstype_name(&s_fstype);

        fstype = ped_file_system_type_get(s_fstype);
        if (fstype == NULL) {
                log("Filesystem %s not found, let's see if it is a flag",
                    s_fstype);
                flag = ped_partition_flag_get_by_name(s_fstype);
                if (ped_partition_is_flag_available(part, flag)) {
                        if (!ped_partition_get_flag(part, flag)) {
                                change_named(device_name);
                                ped_partition_set_flag(part, flag, 1);
                        } else
                                log("Flag %s already set", s_fstype);
                } else {
                        critical_error("Bad file system or flag type: %s",
                                       s_fstype);
                }
        } else {
                if (!((PED_PARTITION_FREESPACE | PED_PARTITION_METADATA |
                       PED_PARTITION_EXTENDED) & part->type) &&
                    fstype != part->fs_type) {
                        change_named(device_name);
                        ped_partition_set_system(part, fstype);
                } else
                        log("Already using filesystem %s", s_fstype);
        }
        free(s_fstype);
        oprintf("OK\n");
}

void
command_check_file_system()
{
        char *id;
        PedPartition *part;
        PedFileSystem *fs;
        char *status;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("command_check_file_system(%s)", id);
        part = partition_with_id(disk, id);
        free(id);
        fs = ped_file_system_open(&(part->geom));
        if (NULL == fs)
                status = "n/c";
        else {
                if (timered_file_system_check(fs))
                        status = "good";
                else
                        status = "bad";
                ped_file_system_close(fs);
        }
        oprintf("OK\n");
        oprintf("%s\n", status);
}

void
command_create_file_system()
{
        char *id;
        PedPartition *part;
        char *s_fstype;
        PedFileSystemType *fstype;
        PedFileSystem *fs;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        change_named(device_name);
        open_out();
        if (2 != iscanf("%as %as", &id, &s_fstype))
                critical_error("Expected partition id and file system");
        log("command_create_file_system(%s,%s)", id, s_fstype);
        part = partition_with_id(disk, id);
        if (part == NULL)
                critical_error("No such partition: %s", id);
        free(id);

        mangle_fstype_name(&s_fstype);

        fstype = ped_file_system_type_get(s_fstype);
        if (fstype == NULL)
                critical_error("Bad file system type: %s", s_fstype);
        ped_partition_set_system(part, fstype);
        deactivate_exception_handler();
        if ((fs = timered_file_system_create(&(part->geom), fstype)) != NULL) {
                ped_file_system_close(fs);
                /* If the partition is at the very start of the disk, then
                 * we've already done all the committing we need to do, and
                 * ped_disk_commit_to_dev will overwrite the partition
                 * header.
                 */
                if (part->geom.start != 0)
                        ped_disk_commit_to_dev(disk);
        }
        activate_exception_handler();
        free(s_fstype);
        oprintf("OK\n");
        if (fs != NULL)
                oprintf("OK\n");
        else
                oprintf("failed\n");
}

void
command_new_label()
{
        PedDiskType *type;
        char *str, *device;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_new_label()");
        change_named(device_name);
        open_out();
        if (1 != iscanf("%as", &str))
                critical_error("Expected label type");
        type = ped_disk_type_get(str);
        if (type == NULL)
                critical_error("Bad label type: %s", str);
        log("command_new_label: requested label with type %s", str);
        device = strdup(device_named(device_name)->path);
        /* The old partition table may have contained wrong
           Cylinder/Head/Sector geometry.  So it is not probably
           enough to change the partition table (i.e. `disk'). */
        set_disk_named(device_name, NULL);
        set_device_named(device_name, NULL);
        dev = ped_device_get(device);
        free(device);
        if (NULL == dev)
                critical_error("Cannot reopen %s", device_name);
        set_device_named(device_name, dev);
        log("command_new_label: creating");
        disk = ped_disk_new_fresh(dev, type);
        if (disk == NULL) {
                static char *only_cancel[] = { "Cancel", NULL };
                pseudo_exception("Error",
                                 "Can't create new disk label.", only_cancel);
        } else
                set_disk_named(device_name, disk);
        oprintf("OK\n");
        free(str);
}

void
command_new_partition()
{
        char *s_type, *s_fs_type;
        PedPartitionType type;
        PedFileSystemType *fs_type;
        long long range_start, range_end;
        char *position;
        PedSector length;
        PedSector part_start, part_end;
        PedPartition *part;
        int n;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        assert(disk != NULL);
        log("command_new_partition()");
        change_named(device_name);
        open_out();
        n = iscanf("%as %as %lli-%lli %as %lli", &s_type, &s_fs_type,
                   &range_start, &range_end, &position, &length);
        if (n != 6)
                critical_error
                    ("Expected: part_type file_system id position length");

        if (!strcasecmp(s_type, "primary"))
                type = 0;
        else if (!strcasecmp(s_type, "logical"))
                type = PED_PARTITION_LOGICAL;
        else
                critical_error("Bad partition type: %s", s_type);
        log("requested partition with type %s", s_type);
        free(s_type);

        mangle_fstype_name(&s_fs_type);

        fs_type = ped_file_system_type_get(s_fs_type);
        if (fs_type == NULL)
                critical_error("Bad file system type: %s", s_fs_type);
        log("requested partition with file system %s", s_fs_type);
        free(s_fs_type);

        if (!strcasecmp(position, "full")) {
                part_start = range_start / dev->sector_size;
                part_end = ((range_end - dev->sector_size + 1)
                            / dev->sector_size);
        } else if (!strcasecmp(position, "beginning")) {
                part_start = range_start / dev->sector_size;
                part_end = (range_start + length) / dev->sector_size;
        } else if (!strcasecmp(position, "end")) {
                part_start = (range_end - length) / dev->sector_size;
                part_end = ((range_end - dev->sector_size + 1)
                            / dev->sector_size);
        } else
                critical_error("Bad position: %s", position);
        free(position);

        if (disk == NULL)
                critical_error("No opened device or no partition table");

        if (type == 0 /* PED_PARTITION_PRIMARY */ )
                part = add_primary_partition(disk, fs_type,
                                             part_start, part_end);
        else
                part = add_logical_partition(disk, fs_type,
                                             part_start, part_end);
        oprintf("OK\n");
        deactivate_exception_handler();
        if (part) {
                char *part_info = partition_info(disk, part);
                oprintf("%s\n", part_info);
                free(part_info);
        } else
                oprintf("\n");
        activate_exception_handler();
}

void
command_delete_partition()
{
        PedPartition *part;
        char *id;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        log("command_delete_partition()");
        change_named(device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("Deleting partition with id %s", id);
        part = partition_with_id(disk, id);
        if (part == NULL)
                log("No such partition");
        else {
                PedPartitionType type = part->type;
                log("Partition found");
                ped_disk_delete_partition(disk, part);
                if (type & PED_PARTITION_LOGICAL)
                        minimize_extended_partition(disk);
                log("Partition deleted");
        }
        oprintf("OK\n");
        free(id);
}

void
command_resize_partition()
{
        PedPartition *part;
        char *id;
        long long new_size;
        PedSector start, end;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        assert(disk != NULL);
        log("command_resize_partition()");
        change_named(device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("Resizing partition with id %s", id);
        part = partition_with_id(disk, id);
        if (part == NULL)
                critical_error("No such partition");
        if (1 != iscanf(" %lli", &new_size))
                critical_error("Expected new size");
        log("New size: %lli", new_size);
        start = (part->geom).start;
        end = start + new_size / dev->sector_size - 1;
        if (named_partition_is_virtual(device_name,
                                       part->geom.start, part->geom.end)) {
                resize_partition(disk, part, start, end, false);
        } else {
                if (resize_partition(disk, part, start, end, true)) {
                        ped_disk_commit(disk);
                        unchange_named(device_name);
                }
        }
        oprintf("OK\n");
        oprintf("%lli-%lli\n", (part->geom).start * dev->sector_size,
                (part->geom).end * dev->sector_size + dev->sector_size - 1);
        free(id);
}

void
command_virtual_resize_partition()
{
        PedPartition *part;
        char *id;
        long long new_size;
        PedSector start, end;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        assert(disk != NULL);
        log("command_virtual_resize_partition()");
        change_named(device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("Resizing partition with id %s", id);
        part = partition_with_id(disk, id);
        if (part == NULL)
                critical_error("No such partition");
        if (1 != iscanf(" %lli", &new_size))
                critical_error("Expected new size");
        log("New size: %lli", new_size);
        start = (part->geom).start;
        end = start + new_size / dev->sector_size - 1;
        /* ensure that the size is not less than the requested */
        do {
                resize_partition(disk, part, start, end, false);
                end = end + 1;
        } while ((part->geom).length * dev->sector_size < new_size);
        ped_disk_commit(disk);
        unchange_named(device_name);
        oprintf("OK\n");
        oprintf("%lli-%lli\n", (part->geom).start * dev->sector_size,
                (part->geom).end * dev->sector_size + dev->sector_size - 1);
        free(id);
}

void
command_get_resize_range()
{
        char *id;
        PedPartition *part;
        PedFileSystem *fs;
        PedConstraint *constraint;
        PedGeometry *max_geom;
        long long max_size, min_size, current_size;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        assert(disk != NULL);
        log("command_get_resize_range()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        deactivate_exception_handler();
        part = partition_with_id(disk, id);
        if (part == NULL)
                critical_error("No such partition");
        if (!named_partition_is_virtual(device_name,
                                        part->geom.start, part->geom.end)) {
                fs = ped_file_system_open(&(part->geom));
                if (NULL != fs && (fs->geom->start < (part->geom).start
                                   || fs->geom->end > (part->geom).end)) {
                        ped_file_system_close(fs);
                        fs = NULL;
                } else if (NULL == fs
                           && NULL != ped_file_system_probe(&(part->geom))) {
                        oprintf("OK\n");
                        oprintf("\n");
                        free(id);
                        activate_exception_handler();
                        return;
                }
        } else {
                fs = NULL;
        }
        if (NULL != fs) {
                constraint = ped_file_system_get_resize_constraint(fs);
                ped_file_system_close(fs);
        } else {
                constraint = ped_constraint_any(disk->dev);
        }
        ped_geometry_set_start(constraint->start_range, (part->geom).start);
        ped_geometry_set_end(constraint->start_range, (part->geom).start);
        if (part->type & PED_PARTITION_LOGICAL)
                maximize_extended_partition(disk);
        max_geom = ped_disk_get_max_partition_geometry(disk, part, constraint);
        if (part->type & PED_PARTITION_LOGICAL)
                minimize_extended_partition(disk);
        min_size = constraint->min_size * dev->sector_size;
        current_size = (part->geom).length * dev->sector_size;
        if (max_geom)
                max_size = max_geom->length * dev->sector_size;
        else
                max_size = current_size;
        oprintf("OK\n");
        oprintf("%lli %lli %lli\n", min_size, current_size, max_size);
        if (max_geom)
                ped_geometry_destroy(max_geom);
        ped_constraint_destroy(constraint);
        /* TODO: Probably there are memory leaks because of constraints. */
        activate_exception_handler();
        free(id);
}

void
command_get_virtual_resize_range()
{
        char *id;
        PedPartition *part;
        PedConstraint *constraint;
        PedGeometry *max_geom;
        long long max_size, min_size, current_size;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        assert(disk != NULL);
        log("command_get_virtual_resize_range()");
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        deactivate_exception_handler();
        part = partition_with_id(disk, id);
        if (part == NULL)
                critical_error("No such partition");
        constraint = ped_constraint_any(disk->dev);
        ped_geometry_set_start(constraint->start_range, (part->geom).start);
        ped_geometry_set_end(constraint->start_range, (part->geom).start);
        if (part->type & PED_PARTITION_LOGICAL)
                maximize_extended_partition(disk);
        max_geom = ped_disk_get_max_partition_geometry(disk, part, constraint);
        if (part->type & PED_PARTITION_LOGICAL)
                minimize_extended_partition(disk);
        min_size = constraint->min_size * dev->sector_size;
        current_size = (part->geom).length * dev->sector_size;
        if (max_geom)
                max_size = max_geom->length * dev->sector_size;
        else
                max_size = current_size;
        oprintf("OK\n");
        oprintf("%lli %lli %lli\n", min_size, current_size, max_size);
        if (max_geom)
                ped_geometry_destroy(max_geom);
        ped_constraint_destroy(constraint);
        /* TODO: Probably there are memory leaks because of constraints. */
        activate_exception_handler();
        free(id);
}

void
command_copy_partition()
{
        char *srcid, *srcdiskid, *destid;
        PedPartition *source, *destination;
        PedDisk *srcdisk;
        PedFileSystem *fs;
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        assert(disk != NULL);
        log("command_copy_partition()");
        change_named(device_name);
        open_out();
        if (3 != iscanf("%as %as %as", &destid, &srcdiskid, &srcid))
                critical_error("Expected id device_identifier id");
        if (!device_opened(srcdiskid))
                critical_error("The device %s is not opened.", srcdiskid);
        srcdisk = disk_named(srcdiskid);
        if (srcdisk == NULL)
                critical_error("The source device has label");
        source = partition_with_id(srcdisk, srcid);
        destination = partition_with_id(disk, destid);
        if (source == NULL)
                critical_error("No source partition %s", srcid);
        if (destination == NULL)
                critical_error("No destination partition %s", destid);
        fs = ped_file_system_open(&(source->geom));
        if (fs != NULL) {
                /* TODO: is ped_file_system_check(fs, ...) necessary? */
                if (timered_file_system_copy(fs, &(destination->geom)))
                        ped_partition_set_system(destination, fs->type);
                ped_file_system_close(fs);
        }
        oprintf("OK\n");
        free(destid);
        free(srcdiskid);
        free(srcid);
}

void
command_get_label_type()
{
        log("command_get_label_type()");
        scan_device_name();
        open_out();
        oprintf("OK\n");
        deactivate_exception_handler();
        if ((disk == NULL) || (disk->type == NULL)
            || (disk->type->name == NULL)) {
                oprintf("unknown\n");
        } else {
                oprintf("%s\n", disk->type->name);
        }
        activate_exception_handler();
}

void
command_is_busy()
{
        char *id;
        PedPartition *part;
        log("command_is_busy()");
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        log("command_is_busy: busy check for id %s", id);
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        if (ped_partition_is_busy(part)) {
                oprintf("yes\n");
        } else {
                oprintf("no\n");
        }
        free(id);
}

void
command_alignment_offset()
{
        char *id;
        PedPartition *part;
        PedAlignment *align;
        log("command_alignment_offset()");
        scan_device_name();
        if (dev == NULL)
                critical_error("The device %s is not opened.", device_name);
        open_out();
        if (1 != iscanf("%as", &id))
                critical_error("Expected partition id");
        part = partition_with_id(disk, id);
        oprintf("OK\n");
        if (alignment_of_device(dev) == ALIGNMENT_CYLINDER)
                /* None of this is useful when using cylinder alignment. */
                oprintf("0\n");
        else {
                align = ped_device_get_minimum_alignment(dev);

                /* align->offset represents the offset of the lowest logical
                 * block on the disk from the disk's natural alignment,
                 * modulo the physical sector size (e.g. 4096 bytes), as a
                 * number of logical sectors (e.g. 512 bytes).  For a disk
                 * with 4096-byte physical sectors deliberately misaligned
                 * to make DOS-style 63-sector offsets work well, we would
                 * thus expect align->offset to be 1, as (1 + 63) * 512 /
                 * 4096 is an integer.
                 *
                 * To get the alignment offset of a *partition*, we thus
                 * need to start with align->offset (in bytes) plus the
                 * partition start position.
                 */
                oprintf("%lld\n",
                        ((align->offset + part->geom.start) *
                         dev->sector_size) %
                        dev->phys_sector_size);

                ped_alignment_destroy(align);
        }
        free(id);
}

void
make_fifo(char* name)
{
    int status;
    status = mkfifo(name, 0644);
    if ((status != 0))
            if (errno != EEXIST) {
                    perror("Cannot create FIFO");
                    exit(252);
            }
}

void
make_fifos()
{
    make_fifo(infifo_name);
    make_fifo(outfifo_name);
    make_fifo(stopfifo_name);
} 

int
write_pid_file()
{
        FILE *fd;
        int status;
        pid_t oldpid;
        if ((fd = fopen(pidfile_name, "a+")) == NULL)
                return -1;

        status = fscanf(fd, "%d", &oldpid);
        if (status != 0 && status != EOF) {
		// If kill(oldpid, 0) == 0 the process is still alive
		// so we abort
		if (kill(oldpid, 0) == 0) {
			fprintf(stderr, "Not starting: process %d still exists\n", oldpid);
			fclose(fd);
			exit(250);
		}
	}

	// Truncate the pid file and continue
	freopen(pidfile_name, "w", fd);
      
        fprintf(fd, "%d", (int)(getpid()));
        fclose(fd);
        return 0;
}

void
cleanup_and_die()
{
        if (unlink(pidfile_name) != 0)
                perror("Cannot unlink pid file");
        if (unlink(infifo_name) != 0)
                perror("Cannot unlink input FIFO");
        if (unlink(outfifo_name) != 0)
                perror("Cannot unlink output FIFO");
        if (unlink(stopfifo_name) != 0)
                perror("Cannot unlink stop FIFO");
}

void
prnt_sig_hdlr(int signal)
{
        int status;
        switch(signal) {
                // SIGUSR1 signals that child is ready to take
                // requests (i.e. has finished initialisation)
                case SIGUSR1:
                    exit(0);
                    break;
                // We'll only get SIGCHLD if our child has pre-deceased us
                // In this case we should exit with its error code
                case SIGCHLD:
                    if (waitpid(-1, &status, WNOHANG) < 0)
                        exit(0);
                    if (WIFEXITED(status))
                        exit(WEXITSTATUS(status));
                    break;
                default:
                    break;
        }
}

/**********************************************************************
   Main
**********************************************************************/

void main_loop() __attribute__ ((noreturn));

void
main_loop()
{
        char *str;
        int iteration = 1;
        set_alignment();
        while (1) {
                log("main_loop: iteration %i", iteration++);
                open_in();
                if (1 != iscanf("%as", &str))
                        critical_error("No data in infifo.");
                log("Read command: %s", str);
                /* Keep partman-command in sync with changes here. */
                if (!strcasecmp(str, "QUIT"))
                        command_quit();
                else if (!strcasecmp(str, "OPEN"))
                        command_open();
                else if (!strcasecmp(str, "CLOSE"))
                        command_close();
                else if (!strcasecmp(str, "OPENED"))
                        command_opened();
                else if (!strcasecmp(str, "VIRTUAL"))
                        command_virtual();
                else if (!strcasecmp(str, "DISK_UNCHANGED"))
                        command_disk_unchanged();
                else if (!strcasecmp(str, "IS_CHANGED"))
                        command_is_changed();
                else if (!strcasecmp(str, "DUMP"))
                        command_dump();
                else if (!strcasecmp(str, "COMMIT"))
                        command_commit();
                else if (!strcasecmp(str, "UNDO"))
                        command_undo();
                else if (!strcasecmp(str, "PARTITIONS"))
                        command_partitions();
                else if (!strcasecmp(str, "PARTITION_INFO"))
                        command_partition_info();
                else if (!strcasecmp(str, "GET_CHS"))
                        command_get_chs();
                else if (!strcasecmp(str, "LABEL_TYPES"))
                        command_label_types();
                else if (!strcasecmp(str, "VALID_FLAGS"))
                        command_valid_flags();
                else if (!strcasecmp(str, "GET_FLAGS"))
                        command_get_flags();
                else if (!strcasecmp(str, "SET_FLAGS"))
                        command_set_flags();
                else if (!strcasecmp(str, "SET_NAME"))
                        command_set_name();
                else if (!strcasecmp(str, "USES_NAMES"))
                        command_uses_names();
                else if (!strcasecmp(str, "GET_MAX_PRIMARY"))
                        command_get_max_primary();
                else if (!strcasecmp(str, "USES_EXTENDED"))
                        command_uses_extended();
                else if (!strcasecmp(str, "FILE_SYSTEM_TYPES"))
                        command_file_system_types();
                else if (!strcasecmp(str, "GET_FILE_SYSTEM"))
                        command_get_file_system();
                else if (!strcasecmp(str, "CHANGE_FILE_SYSTEM"))
                        command_change_file_system();
                else if (!strcasecmp(str, "CHECK_FILE_SYSTEM"))
                        command_check_file_system();
                else if (!strcasecmp(str, "CREATE_FILE_SYSTEM"))
                        command_create_file_system();
                else if (!strcasecmp(str, "NEW_LABEL"))
                        command_new_label();
                else if (!strcasecmp(str, "NEW_PARTITION"))
                        command_new_partition();
                else if (!strcasecmp(str, "DELETE_PARTITION"))
                        command_delete_partition();
                else if (!strcasecmp(str, "RESIZE_PARTITION"))
                        command_resize_partition();
                else if (!strcasecmp(str, "GET_RESIZE_RANGE"))
                        command_get_resize_range();
                /* these two functions are undocumented and should disappear */
                else if (!strcasecmp(str, "VIRTUAL_RESIZE_PARTITION"))
                        command_virtual_resize_partition();
                else if (!strcasecmp(str, "GET_VIRTUAL_RESIZE_RANGE"))
                        command_get_virtual_resize_range();
                else if (!strcasecmp(str, "COPY_PARTITION"))
                        command_copy_partition();
                else if (!strcasecmp(str, "GET_LABEL_TYPE"))
                        command_get_label_type();
                else if (!strcasecmp(str, "IS_BUSY"))
                        command_is_busy();
                else if (!strcasecmp(str, "ALIGNMENT_OFFSET"))
                        command_alignment_offset();
                else
                        critical_error("Unknown command %s", str);
                free(str);
                close_fifos_and_synchronise();
        }
}

int
main(int argc, char *argv[])
{
        struct sigaction act, oldact;
        int i;

        /* Close all extraneous file descriptors, including our pipe to
         * debconf.
         */
        for (i = 3; i < 256; ++i)
                close(i);

        // Set up signal handling
        memset(&act,0,sizeof(struct sigaction));
        memset(&oldact,0,sizeof(struct sigaction));
        act.sa_handler = prnt_sig_hdlr;
        sigemptyset(&act.sa_mask);

        // Set up signal handling for parent
        if  ((sigaction(SIGCHLD, &act, &oldact) < 0)
          || (sigaction(SIGUSR1, &act, &oldact) < 0))
        {
            fprintf(stderr, "Could not set up signal handling for parent\n");
            exit(251);
        }
      
        // The parent process should wait; we die once child is
        // initialised (signalled by a SIGUSR1)
        if (fork()) {
            while (1) { sleep(5); };
        }

        // Set up signal handling for child
        if  ((sigaction(SIGCHLD, &oldact, NULL) < 0)
          || (sigaction(SIGUSR1, &oldact, NULL) < 0))
        {
            fprintf(stderr, "Could not set up signal handling for child\n");
            exit(250);
        }

        // Continue as a daemon process
        logfile = fopen(logfile_name, "a+");
        if (logfile == NULL) {
                fprintf(stderr, "Cannot append to the log file\n");
                exit(255);
        }
        if (write_pid_file() != 0) {
                fprintf(stderr, "Cannot open pid file\n");
                exit(254);
        }
        if (atexit(cleanup_and_die) != 0) {
                fprintf(stderr, "Cannot set atexit routine\n");
                exit(253);
        }
        make_fifos();
        // Signal that we've finished initialising so that the parent process
        // can die and the shell scripts can continue
        kill(getppid(), SIGUSR1);
        ped_exception_set_handler(exception_handler);
        log("======= Starting the server");
        main_loop();
}

/*
The following command can be used to format this file in a consistent
with codingstyle.txt way:

indent parted_server.c -kr -i8 -nut -psl -l79 -T FILE -T bool -T PedSector -T PedDeviceType -T PedDevice -T PedDiskTypeFeature -T PedDiskType -T PedDisk -T PedGeometry -T PedPartitionType -T PedPartitionFlag -T PedPartition -T PedFileSystemType -T PedFileSystem -T PedConstraint -T PedAlignment -T PedTimer -T PedExceptionType -T PedExceptionOption -T PedException
*/

/*
Local variables:
indent-tabs-mode: nil
c-file-style: "linux"
c-font-lock-extra-types: ("FILE" "\\sw+_t" "bool" "Ped\\sw+")
End:
*/
