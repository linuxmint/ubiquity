{
    split($0, line, ":")
    filename=line[1]
    # Get basename and trim line
    sub(/^.*\//, "", filename)
    sub(/[ \t\r\n]+/, "", filename)
    # Remove filename from line
    logline=$0
    sub(/^[^:]*: /, "", logline)

    if (filename) {
        print logline>filename;
    }
}
