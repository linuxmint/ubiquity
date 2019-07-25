#!/usr/bin/python3

import sys

with open('/proc/self/cgroup') as f:
    if 'docker' in f.read():
        print("UBIQUITY CANNOT BE BUILT IN DOCKER!")
        print("Docker misses necessary translations in /usr/share/locale")
        sys.exit(1)
