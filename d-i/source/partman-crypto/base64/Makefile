CFLAGS = -Wall -Os -s

all: base64 test

base64: base64.c
	$(CC) $(CFLAGS) -o $@ $< 
	strip -s $@

test: test-stamp
test-stamp: base64
	@set -e; \
	echo "Running self-tests"; \
	for t in tests/case*; do \
		num=$${t#tests/case}; \
		echo "  $${t}..."; \
		./base64 < $$t > out$$num; \
		cmp tests/want$$num out$$num; \
		rm out$$num; \
	done
	touch test-stamp

clean:
	rm -f base64 test-stamp
