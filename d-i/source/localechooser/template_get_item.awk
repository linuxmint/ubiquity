# AWK-script to extract specific template from templates file

BEGIN {
    FOUND = 0
}

{
    line=$0

    if (index(line, ITEM) > 0) {
        FOUND = 1
        print line
        getline
        line=$0
    }

    if (FOUND == 1) {
        if (match(line, /^[^\ ]*:/) > 0) {
            FOUND = 0
        } else {
            print line
        }
    }
}
