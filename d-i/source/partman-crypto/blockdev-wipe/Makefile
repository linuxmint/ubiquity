CFLAGS = -Wall -Os -s
STRIP = strip

blockdev-wipe: blockdev-wipe.c
	$(CC) $(CFLAGS) -o $@ $<
	$(STRIP) -s $@

clean:
	rm -f blockdev-wipe
