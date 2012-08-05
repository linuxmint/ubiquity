CFLAGS := -Os -g -Wall

all: ensure-active

ensure-active: ensure-active.c
	$(CC) $(CFLAGS) $^ -o $@ -lparted

clean:
	rm -f ensure-active
