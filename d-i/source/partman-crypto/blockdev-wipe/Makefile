CFLAGS = -Wall -Os -s

blockdev-wipe: blockdev-wipe.c
	$(CC) $(CFLAGS) -o $@ $< 
	strip -s $@

clean:
	rm -f blockdev-wipe
