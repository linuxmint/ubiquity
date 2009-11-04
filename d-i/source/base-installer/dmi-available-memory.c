/* Some code here borrowed from dmidecode, also GPLed and copyrighted by:
 *   (C) 2000-2002 Alan Cox <alan@redhat.com>
 *   (C) 2002-2005 Jean Delvare <khali@linux-fr.org>
 * I (Colin Watson) copied it in reduced form rather than using dmidecode
 * directly because (a) the d-i initrd is tight on space and this is much
 * smaller and (b) parsing the output of dmidecode in shell is unreasonably
 * painful.
 */

#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <stdio.h>

#define WORD(x) (*(const uint16_t *)(x))
#define DWORD(x) (*(const uint32_t *)(x))

struct dmi_header
{
	uint8_t type;
	uint8_t length;
	uint16_t handle;
};

static int checksum(const uint8_t *buf, size_t len)
{
	uint8_t sum = 0;
	size_t a;

	for (a = 0; a < len; a++)
		sum += buf[a];
	return (sum == 0);
}

/* Copy a physical memory chunk into a memory buffer.
 * This function allocates memory.
 */
static void *mem_chunk(size_t base, size_t len)
{
	void *p;
	int fd;
	size_t mmoffset;
	void *mmp;

	fd = open("/dev/mem", O_RDONLY);
	if (fd == -1)
		return NULL;

	p = malloc(len);
	if (p == NULL)
	{
		close(fd);
		return NULL;
	}

#ifdef _SC_PAGESIZE
	mmoffset = base % sysconf(_SC_PAGESIZE);
#else
	mmoffset = base % getpagesize();
#endif
	/* Please note that we don't use mmap() for performance reasons here,
	 * but to workaround problems many people encountered when trying
	 * to read from /dev/mem using regular read() calls.
	 */
	mmp = mmap(0, mmoffset + len, PROT_READ, MAP_SHARED, fd,
		   base - mmoffset);
	if (mmp == MAP_FAILED)
	{
		free(p);
		close(fd);
		return NULL;
	}

	memcpy(p, mmp + mmoffset, len);

	munmap(mmp, mmoffset + len);

	close(fd);

	return p;
}

static uint64_t dmi_table(uint32_t base, uint16_t len, uint16_t num)
{
	uint8_t *buf, *data;
	int i = 0;
	uint64_t available = 0;

	buf = mem_chunk(base, len);
	if (buf == NULL)
		return 0;

	data = buf;
	while (i < num && data + sizeof(struct dmi_header) <= buf + len)
	{
		uint8_t *next;
		struct dmi_header *h = (struct dmi_header *)data;

		/* Stop decoding at end of table marker */
		if (h->type == 127)
			break;

		/* Look for the next handle */
		next = data + h->length;
		while (next - buf + 1 < len && (next[0] != 0 || next[1] != 0))
			next++;
		next += 2;
		/* Memory Array Mapped Address */
		if (h->type == 19 && h->length >= 0x0F)
		{
			uint64_t start, end;
			start = DWORD(data + 0x04);
			end = DWORD(data + 0x08);
			if (end >= start)
				/* output in kilobytes */
				available += end - start + 1;
		}

		data = next;
		i++;
	}

	free(buf);
	return available;
}

static uint64_t smbios_decode(uint8_t *buf)
{
	if (checksum(buf, buf[0x05]) &&
	    memcmp(buf + 0x10, "_DMI_", 5) == 0 &&
	    checksum(buf + 0x10, 0x0F))
	{
		return dmi_table(DWORD(buf + 0x18), WORD(buf + 0x16),
				 WORD(buf + 0x1C));
	}

	return 0;
}

static uint64_t legacy_decode(uint8_t *buf)
{
	if (checksum(buf, 0x0F))
	{
		return dmi_table(DWORD(buf + 0x08), WORD(buf + 0x06),
				 WORD(buf + 0x0C));
	}

	return 0;
}

static uint64_t dmi_available_memory(void)
{
	uint8_t *buf;
	size_t fp;
	uint64_t ret = 0;

	buf = mem_chunk(0xF0000, 0x10000);
	if (buf == NULL)
		return 0;

	for (fp = 0; fp <= 0xFFF0; fp += 16)
	{
		if (memcmp(buf + fp, "_SM_", 4) == 0 && fp <= 0xFFE0)
		{
			ret = smbios_decode(buf + fp);
			if (ret)
				break;
			fp += 16;
		}
		else if (memcmp(buf + fp, "_DMI_", 5) == 0)
		{
			ret = legacy_decode(buf + fp);
			if (ret)
				break;
		}
	}

	free(buf);
	return ret;
}

int main(int argc, char **argv)
{
	printf("%llu\n", dmi_available_memory());
	return 0;
}
