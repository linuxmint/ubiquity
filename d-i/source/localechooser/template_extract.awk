# AWK-script to extract specific template from templates file

# The script takes three parameters:
# - TEMPLATE: The template to be extracted from the templatefile
# - TFILE1: The extracted template will be written here
# - TFILE2: All other templates will be written here (can be /dev/null ;-)

BEGIN {
    FOUND = 0
    TEMPLATE = "Template: " TEMPLATE
}

{
    line=$0

    if (index(line, TEMPLATE) > 0) {
        FOUND = 1
        print line >>TFILE1
        getline
        line=$0
    }

    if (FOUND == 1) {
        if (substr(line, 1, 9) == "Template:") {
            FOUND = 0
            print line >>TFILE2
        } else {
            print line >>TFILE1
        }
    } else {
        print line >>TFILE2
    }
}
