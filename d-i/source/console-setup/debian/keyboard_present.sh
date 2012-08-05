

keyboard_present () {
    local kern kbdpattern class subclass protocol

    kern=`uname -r`
    case "$kern" in
	1*|2.0*|2.1*|2.2*|2.3*|2.4*|2.5*)
	    # can't check keyboard presence
	    return 0; 
	    ;;
    esac

    [ -f /proc/bus/input/devices ] || return 0
    kbdpattern="AT Set \|AT Translated Set\|AT Raw Set"
    kbdpattern="$kbdpattern\|Atari Keyboard"
    kbdpattern="$kbdpattern\|Amiga Keyboard"
    kbdpattern="$kbdpattern\|HIL keyboard"
    kbdpattern="$kbdpattern\|ADB keyboard"
    kbdpattern="$kbdpattern\|Sun Type"
    if grep -i "$kbdpattern" /proc/bus/input/devices >/dev/null; then
	return 0
    fi

    [ -d /sys/bus/usb/devices ] || return 0
    for d in /sys/bus/usb/devices/*:*; do
	class=$(cat "$d/bInterfaceClass") # 03 = Human Interface Device
	subclass=$(cat "$d/bInterfaceSubClass") # 01 = Boot Interface Subclass
	protocol=$(cat "$d/bInterfaceProtocol") # 01 = Keyboard
	case "$class:$subclass:$protocol" in
	    03:01:01)
		return 0
		;;
	esac
    done

    return 1
}
