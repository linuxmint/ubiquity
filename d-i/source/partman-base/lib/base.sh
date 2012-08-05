
. /usr/share/debconf/confmodule

NBSP=' '
TAB='	'
NL='
'
ORIGINAL_IFS="${ORIGINAL_IFS:-$IFS}"; export ORIGINAL_IFS

restore_ifs () {
	IFS="$ORIGINAL_IFS"
}

dirname () {
	local x
	x="${1%/}"
	echo "${x%/*}"
}

basename () {
	local x
	x="${1%$2}"
	x="${x%/}"
	echo "${x##*/}"
}

maybe_escape () {
	local code saveret
	text="$1"
	shift
	if [ "$can_escape" ]; then
		db_capb backup align escape
		code=0
		"$@" "$(printf '%s' "$text" | debconf-escape -e)" || code=$?
		saveret="$RET"
		db_capb backup align
		RET="$saveret"
		return $code
	else
		"$@" "$text"
	fi
}

# Deprecated debconf_select() for templates not switched to Choices-C yet.
old_debconf_select () {
	local IFS priority template choices default_choice default x u newchoices code
	priority="$1"
	template="$2"
	choices="$3"
	default_choice="$4"
	default=''
	# Debconf ignores spaces so we have to remove them from $choices
	newchoices=''
	case $PARTMAN_SNOOP in
		?*)
			> /var/lib/partman/snoop
			;;
	esac
	IFS="$NL"
	for x in $choices; do
		local key option
		restore_ifs
		key=$(echo ${x%$TAB*})
		option=$(echo "${x#*$TAB}" | sed "s/ *\$//g; s/^ /$debconf_select_lead/g")
		newchoices="${newchoices:+${newchoices}${NL}}${key}${TAB}${option}"
		if [ "$key" = "$default_choice" ]; then
			default="$option"
		fi
		case $PARTMAN_SNOOP in
			?*)
				echo "$key$TAB$option" >> /var/lib/partman/snoop
				;;
		esac
	done
	choices="$newchoices"
	u=''
	IFS="$NL"
	# escape the commas and leading whitespace but keep them unescaped
	# in $choices
	for x in $choices; do
		u="$u, `echo ${x#*$TAB} | sed 's/,/\\\\,/g; s/^ /\\\\ /'`"
	done
	u=${u#, }
	restore_ifs
	# You can preseed questions asked through this function by using
	# full localised text (deprecated) or by using the key (the part
	# before the tab). Additionally, if the question was asked via
	# ask_user below, then you can also preseed it using the name of the
	# plugin responsible for the answer you want.
	if [ -n "$default" ]; then
		db_set $template "$default"
	fi
	db_subst $template CHOICES "$u"
	code=0
	db_input $priority $template || code=1
	db_go || return 255
	db_get $template
	IFS="$NL"
	for x in $choices; do
		if [ "$RET" = "${x#*$TAB}" ]; then
			RET="${x%$TAB*}"
			break
		else
			# Help out ask_user.
			local key="${x%%__________*}"
			if [ "$key" != "$x" ] && \
			   ([ "$RET" = "$key" ] || \
			    [ "$RET" = "${key#[0-9][0-9]}" ]); then
				RET="${x%$TAB*}"
				break
			fi
		fi
	done
	restore_ifs
	return $code
}

debconf_select () {
	local IFS priority template choices default keys descriptions code x
	priority="$1"
	template="$2"
	choices="$3"
	default="$4"
	case $PARTMAN_SNOOP in
		?*)
			> /var/lib/partman/snoop
			;;
	esac

	if ! db_metaget $template choices-c; then
		logger -t partman "warning: $template is not using Choices-C"
		old_debconf_select "$@"
		return $?
	fi

	if [ -z "$default" ]; then
		db_get "$template" && default="$RET"
	fi
	keys=""
	descriptions=""
	case $PARTMAN_SNOOP in
		?*)
			echo "$choices" | sed "h; s/.*$TAB//; s/ *\$//g; s/^ /$debconf_select_lead/g; x; s/$TAB.*//; G; s/\\n/$TAB/; s/^$TAB\$//" >> /var/lib/partman/snoop
			;;
	esac
	# Use the hold space carefully here to allow us to make some
	# substitutions on only the RHS (description).
	choices="$(echo "$choices" | sed "h; s/.*$TAB//; s/ *\$//g; s/^ /$debconf_select_lead/g; s/,/\\\\,/g; s/^ /\\\\ /; x; s/$TAB.*//; G; s/\\n/$TAB/; s/^$TAB\$//")"
	IFS="$NL"
	for x in $choices; do
		local key plugin
		restore_ifs
		key="${x%$TAB*}"
		keys="${keys:+${keys}, }$key"
		descriptions="${descriptions:+${descriptions}, }${x#*$TAB}"

		# If the question was asked via ask_user, this allow preseeding
		# by using the name of the plugin responsible for the answer.
		if [ -n "$default" ]; then
			plugin="${key%%__________*}"
			if [ "$default" = "$plugin" ] ||
			   [ "$default" = "${plugin#[0-9][0-9]}" ]; then
				default="$key"
			fi
		fi
	done
	# You can preseed questions asked through this function by using
	# the key (the part before the tab).
	if [ -n "$default" ]; then
		db_set $template "$default"
	fi
	db_subst $template CHOICES "$keys"
	db_subst $template DESCRIPTIONS "$descriptions"
	code=0
	db_input $priority $template || code=1
	db_go || return 255
	db_get $template
	return $code
}

menudir_default_choice () {
	printf "%s__________%s\n" "$(basename $1/??$2)" "$3" > $1/default_choice
}

ask_user () {
	local IFS dir template priority default choices plugin name option
	dir="$1"; shift
	template=$(cat $dir/question)
	priority=$(cat $dir/priority)
	if [ -f $dir/default_choice ]; then
		default=$(cat $dir/default_choice)
	else
		default=""
	fi
	choices=$(
		if [ -e $dir/no_show_choices ]; then
			printf "dummy__________dummy$TAB\n"
			exit 0
		fi
		local skip_divider=1
		for plugin in $dir/*; do
			[ -d $plugin ] || continue
			name=$(basename $plugin)
			IFS="$NL"
			for option in $($plugin/choices "$@"); do
				# Skip a divider (only has space as description)
				# if it's the first option or when two in a row
				if echo "$option" | grep -q "$TAB *$"; then
					if [ "$skip_divider" ]; then
						continue
					fi
					skip_divider=1
				else
					skip_divider=
				fi
				printf "%s__________%s\n" $name "$option"
			done
			restore_ifs
		done
	)
	code=0
	debconf_select $priority $template "$choices" "$default" || code=$?
	if [ $code -ge 100 ]; then return 255; fi
	echo "$RET" >$dir/default_choice
	$dir/${RET%__________*}/do_option ${RET#*__________} "$@" || return $?
	return 0
}

ask_active_partition () {
	local dev=$1
	local id=$2
	local num=$3
	local RET

	db_subst partman/active_partition DEVICE "$(humandev $(cat device))"
	db_subst partman/active_partition PARTITION "$num"

	if [ -f $id/detected_filesystem ]; then
		local filesystem=$(cat $id/detected_filesystem)
		RET=''
		db_metaget partman/filesystem_long/"$filesystem" description || RET=''
		if [ "$RET" ]; then
			filesystem="$RET"
		fi
		db_subst partman/text/there_is_detected FILESYSTEM "$filesystem"
		db_metaget partman/text/there_is_detected description
	else
		db_metaget partman/text/none_detected description
	fi
	db_subst partman/active_partition OTHERINFO "${RET}"

	if [ -f $id/detected_filesystem ] && [ -f $id/format ]; then
		db_metaget partman/text/destroyed description
		db_subst partman/active_partition DESTROYED "${RET}"
	else
		db_subst partman/active_partition DESTROYED ''
	fi

	ask_user /lib/partman/active_partition "$dev" "$id" || return $?
}

partition_tree_choices () {
	local IFS
	for dev in $DEVICES/*; do
		[ -d $dev ] || continue
		if [ -e "$dev/partition_tree_cache" ]; then
			cat "$dev/partition_tree_cache"
			continue
		fi
		printf "%s//\t%s\n" $dev "$(device_name $dev)" >"$dev/partition_tree_cache" # GETTEXT?
		cd $dev

		open_dialog PARTITIONS
		partitions="$(read_paragraph)"
		close_dialog

		IFS="$TAB"
		echo "$partitions" |
		while { read num id size type fs path name; [ "$id" ]; }; do
			part=${dev}/$id
			[ -f $part/view ] || continue
			printf "%s//%s\t%s\n" "$dev" "$id" $(cat $part/view) >>partition_tree_cache
		done
		cat partition_tree_cache
		restore_ifs
	done
}

longint_le () {
	local x y
	# remove the leading 0
	x=$(expr "$1" : '0*\(.*\)')
	y=$(expr "$2" : '0*\(.*\)')
	if [ ${#x} -lt ${#y} ]; then
		return 0
	elif [ ${#x} -gt ${#y} ]; then
		return 1
	elif [ "$x" = "$y" ]; then
		return 0
	elif [ "$x" '<' "$y" ]; then
		return 0
	else
		return 1
	fi
}

longint2human () {
	local longint suffix bytes int frac deci
	# fallback value for $deci:
	deci="${deci:-.}"
	case ${#1} in
	    1|2|3)
		suffix=B
		longint=${1}00
		;;
	    4|5|6)
		suffix=kB
		longint=${1%?}
		;;
	    7|8|9)
		suffix=MB
		longint=${1%????}
		;;
	    10|11|12)
		suffix=GB
		longint=${1%???????}
		;;
	    *)
		suffix=TB
		longint=${1%??????????}
		;;
	esac
	longint=$(($longint + 5))
	longint=${longint%?}
	int=${longint%?}
	frac=${longint#$int}
	printf "%i%s%i %s\n" $int $deci $frac $suffix
}

human2longint () {
	local human orighuman gotb suffix int frac longint
	set -- $*; human="$1$2$3$4$5" # without the spaces
	orighuman="$human"
	human=${human%b} #remove last b
	human=${human%B} #remove last B
	gotb=''
	if [ "$human" != "$orighuman" ]; then
		gotb=1
	fi
	suffix=${human#${human%?}} # the last symbol of $human
	case $suffix in
	k|K|m|M|g|G|t|T)
		human=${human%$suffix}
		;;
	*)
		if [ "$gotb" ]; then
			suffix=B
		else
			suffix=''
		fi
		;;
	esac
	int="${human%[.,]*}"
	[ "$int" ] || int=0
	frac=${human#$int}
	frac="${frac#[.,]}0000" # to be sure there are at least 4 digits
	frac=${frac%${frac#????}} # only the first 4 digits of $frac
	longint=$(expr "$int" \* 10000 + "$frac")
	case $suffix in
	b|B)
		longint=${longint%????}
		[ "$longint" ] || longint=0
		;;
	k|K)
		longint=${longint%?}
		;;
	m|M)
		longint=${longint}00
		;;
	g|G)
		longint=${longint}00000
		;;
	t|T)
		longint=${longint}00000000
		;;
	*) # no suffix:
		# bytes
		#longint=${longint%????}
		#[ "$longint" ] || longint=0
		# megabytes
		longint=${longint}00
		;;
	esac
	echo $longint
}

valid_human () {
	local IFS patterns
	patterns='[0-9][0-9]* *$
[0-9][0-9]* *[bB] *$
[0-9][0-9]* *[kKmMgGtT] *$
[0-9][0-9]* *[kKmMgGtT][bB] *$
[0-9]*[.,][0-9]* *$
[0-9]*[.,][0-9]* *[bB] *$
[0-9]*[.,][0-9]* *[kKmMgGtT] *$
[0-9]*[.,][0-9]* *[kKmMgGtT][bB] *$'
	IFS="$NL"
	for regex in $patterns; do
		if expr "$1" : "$regex" >/dev/null; then return 0; fi
	done
	return 1
}

convert_to_megabytes() {
	local size="$1"
	expr 0000000"$size" : '0*\(..*\)......$'
}

stop_parted_server () {
	open_infifo
	write_line "QUIT"
	close_infifo
}

# Must call stop_parted_server before calling this.
restart_partman () {
	initcount=`ls /lib/partman/init.d/* | wc -l`
	db_progress START 0 $initcount partman/progress/init/title
	for s in /lib/partman/init.d/*; do
		if [ -x $s ]; then
			base=$(basename $s | sed 's/[0-9]*//')
			if ! db_progress INFO partman/progress/init/$base; then
				db_progress INFO partman/progress/init/fallback
			fi
			if ! $s; then
				db_progress STOP
				exit 255
			fi
		fi
		db_progress STEP 1
	done
	db_progress STOP
}

update_partition () {
	local u
	cd $1
	open_dialog PARTITION_INFO $2
	read_line part
	close_dialog
	[ "$part" ] || return 0
	rm -f partition_tree_cache
	for u in /lib/partman/update.d/*; do
		[ -x "$u" ] || continue
		$u $1 $part
	done
}

DEVICES=/var/lib/partman/devices

# 0, 1 and 2 are standard input, output and error.
# 3, 4 and 5 are used by cdebconf
# 6=infifo
# 7=outfifo

open_infifo() {
	exec 6>/var/lib/partman/infifo
}

close_infifo() {
	exec 6>&-
}

open_outfifo () {
	exec 7</var/lib/partman/outfifo
}

close_outfifo () {
	exec 7<&-
}

write_line () {
	log IN: "$@"
	echo "$@" >&6
}

read_line () {
	read "$@" <&7
}

synchronise_with_server () {
	exec 6>/var/lib/partman/stopfifo
	exec 6>&-
}

read_paragraph () {
    local line
    while { read_line line; [ "$line" ]; }; do
	log "paragraph: $line"
	echo "$line"
    done
}

read_list () {
	local item list
	list=''
	while { read_line item; [ "$item" ]; }; do
		log "option: $item"
		list="${list:+$list, }$item"
	done
	echo "$list"
}

name_progress_bar () {
	echo $1 >/var/lib/partman/progress_info
}

error_handler () {
    local exception_type info state frac type priority message options skipped
    while { read_line exception_type; [ "$exception_type" != OK ]; }; do
	log error_handler: exception with type $exception_type
	case "$exception_type" in
	    Timer)
		if [ -f /var/lib/partman/progress_info ]; then
		    info=$(cat /var/lib/partman/progress_info)
		else
		    info=partman/processing
		fi
		db_progress START 0 1000 partman/text/please_wait
		db_progress INFO $info
		while { read_line frac state; [ "$frac" != ready ]; }; do
		    if [ "$state" ]; then
			db_subst $info STATE "$state"
			db_progress INFO $info
		    fi
		    db_progress SET $frac
		done
		db_progress STOP
		continue
		;;
	    Information)
		type='Information'
		priority=medium
		;;
	    Warning)
		type='Warning!'
		priority=high
		;;
	    Error)
		type='ERROR!!!'
		priority=critical
		;;
	    Fatal)
		type='FATAL ERROR!!!'
		priority=critical
		;;
	    Bug)
		type='A bug has been discovered!!!'
		priority=critical
		;;
	    No?Implementation)
		type='Not yet implemented!'
		priority=critical
		;;
	    *)
		type="??? $exception_type ???"
		priority=critical
		;;
	esac
	log error_handler: reading message
	message=$(read_paragraph)
	log error_handler: reading options
	options=$(read_list)
	db_subst partman/exception_handler TYPE "$type"
	maybe_escape "$message" db_subst partman/exception_handler DESCRIPTION
	db_subst partman/exception_handler CHOICES "$options"
	if
	    expr "$options" : '.*,.*' >/dev/null \
	    && db_fset partman/exception_handler seen false \
	    && db_input $priority partman/exception_handler
	then
	    if db_go; then
		db_get partman/exception_handler
		write_line "$RET"
	    else
		write_line "unhandled"
	    fi
	else
	    db_subst partman/exception_handler_note TYPE "$type"
	    maybe_escape "$message" db_subst partman/exception_handler_note DESCRIPTION
	    db_fset partman/exception_handler_note seen false
	    db_input $priority partman/exception_handler_note || true
	    db_go || true
	    write_line "unhandled"
	fi
    done
    rm -f /var/lib/partman/progress_info
}

open_dialog () {
	command="$1"
	shift
	open_infifo
	write_line "$command" "${PWD##*/}" "$@"
	open_outfifo
	error_handler
}

close_dialog () {
	close_outfifo
	close_infifo
	exec 6>/var/lib/partman/stopfifo
	exec 6>&-
	exec 7>/var/lib/partman/outfifo
	exec 7>&-
	exec 6>/var/lib/partman/stopfifo
	exec 6>&-
	exec 6</var/lib/partman/infifo
	cat <&6 >/dev/null
	exec 6<&-
	exec 6>/var/lib/partman/stopfifo
	exec 6>&-
}

log () {
	local program
	echo $0: "$@" >>/var/log/partman
}

####################################################################
# The functions below are not yet documented
####################################################################

# Returns free memory in kB
memfree () {
	local free buff
	if [ -e /proc/meminfo ]; then
		free=$(grep MemFree /proc/meminfo | head -n1 | \
			sed 's/.*:[[:space:]]*\([0-9]*\).*/\1/')
		buff=$(grep Buffers /proc/meminfo | head -n1 | \
			sed 's/.*:[[:space:]]*\([0-9]*\).*/\1/')
		echo $(($free + $buff))
	else
		echo 0
	fi
}

# return the device mapper table type
dm_table () {
	local type=""
	if [ -x /sbin/dmsetup ]; then
		type=$(/sbin/dmsetup table "$1" 2>/dev/null | head -n 1 | cut -d " " -f3)
	fi
	echo $type
}

# Check if a d-m device is a multipath device
is_multipath_dev () {
	local type

	type=$(dm_table $1)
	[ "$type" = multipath ] || return 1
}

# Check if a d-m device is a partition on a multipath device by checking if
# the corresponding multipath map exists
is_multipath_part () {
	local type mp name

	type multipath >/dev/null 2>&1 || return 1

	type=$(dm_table $1)
	[ "$type" = linear ] || return 1
	name=$(dmsetup info --noheadings -c -oname "$1")

	mp=${name%-part*}
	if [ $(multipath -l $mp | wc -l) -gt  0 ]; then
		return 0
	fi
	return 1
}

# TODO: this should not be global
humandev () {
    local device disk drive host bus target part line controller lun
    local idenum scsinum targtype linux kfreebsd mapping vglv vg lv wwid
    local dev discipline frdisk type rtype desc n
    case "$1" in
	/dev/ide/host*/bus[01]/target[01]/lun0/disc)
	    host=`echo $1 | sed 's,/dev/ide/host\(.*\)/bus.*/target[01]/lun0/disc,\1,'`
	    bus=`echo $1 | sed 's,/dev/ide/host.*/bus\(.*\)/target[01]/lun0/disc,\1,'`
	    target=`echo $1 | sed 's,/dev/ide/host.*/bus.*/target\([01]\)/lun0/disc,\1,'`
	    idenum=$((2 * $host + $bus + 1))
	    linux=$(mapdevfs $1)
	    linux=${linux#/dev/}
	    if [ "$target" = 0 ]; then
		db_metaget partman/text/ide_master_disk description
		printf "$RET" ${idenum} ${linux}
	    else
		db_metaget partman/text/ide_slave_disk description
		printf "$RET" ${idenum} ${linux}
	    fi
	    ;;
	# Some drivers advertise the disk as "part", workaround for #404950
	/dev/ide/host*/bus[01]/target[01]/lun0/part)
	    host=`echo $1 | sed 's,/dev/ide/host\(.*\)/bus.*/target[01]/lun0/part,\1,'`
	    bus=`echo $1 | sed 's,/dev/ide/host.*/bus\(.*\)/target[01]/lun0/part,\1,'`
	    target=`echo $1 | sed 's,/dev/ide/host.*/bus.*/target\([01]\)/lun0/part,\1,'`
	    idenum=$((2 * $host + $bus + 1))
	    linux=$(mapdevfs $1)
	    linux=${linux#/dev/}
	    if [ "$target" = 0 ]; then
		db_metaget partman/text/ide_master_disk description
		printf "$RET" ${idenum} ${linux}
	    else
		db_metaget partman/text/ide_slave_disk description
		printf "$RET" ${idenum} ${linux}
	    fi
	    ;;
	/dev/ide/host*/bus[01]/target[01]/lun0/part*)
	    host=`echo $1 | sed 's,/dev/ide/host\(.*\)/bus.*/target[01]/lun0/part.*,\1,'`
	    bus=`echo $1 | sed 's,/dev/ide/host.*/bus\(.*\)/target[01]/lun0/part.*,\1,'`
	    target=`echo $1 | sed 's,/dev/ide/host.*/bus.*/target\([01]\)/lun0/part.*,\1,'`
	    part=`echo $1 | sed 's,/dev/ide/host.*/bus.*/target[01]/lun0/part\(.*\),\1,'`
	    idenum=$((2 * $host + $bus + 1))
	    linux=$(mapdevfs $1)
	    linux=${linux#/dev/}
	    if [ "$target" = 0 ]; then
		db_metaget partman/text/ide_master_partition description
		printf "$RET" ${idenum} "$part" "${linux}"
	    else
		db_metaget partman/text/ide_slave_partition description
		printf "$RET" ${idenum} "$part" "${linux}"
	    fi
	    ;;
	/dev/hd[a-z])
	    drive=$(printf '%d' "'$(echo $1 | sed 's,^/dev/hd\([a-z]\).*,\1,')")
	    drive=$(($drive - 97))
	    linux=${1#/dev/}
	    if [ "$(($drive % 2))" = 0 ]; then
		db_metaget partman/text/ide_master_disk description
	    else
		db_metaget partman/text/ide_slave_disk description
	    fi
	    printf "$RET" "$(($drive / 2 + 1))" "$linux"
	    ;;
	/dev/hd[a-z][0-9]*)
	    drive=$(printf '%d' "'$(echo $1 | sed 's,^/dev/hd\([a-z]\).*,\1,')")
	    drive=$(($drive - 97))
	    part=$(echo $1 | sed 's,^/dev/hd[a-z]\([0-9][0-9]*\).*,\1,')
	    linux=${1#/dev/}
	    if [ "$(($drive % 2))" = 0 ]; then
		db_metaget partman/text/ide_master_partition description
	    else
		db_metaget partman/text/ide_slave_partition description
	    fi
	    printf "$RET" "$(($drive / 2 + 1))" "$part" "$linux"
	    ;;
	/dev/scsi/host*/bus*/target*/lun*/disc)
	    host=`echo $1 | sed 's,/dev/scsi/host\(.*\)/bus.*/target.*/lun.*/disc,\1,'`
	    bus=`echo $1 | sed 's,/dev/scsi/host.*/bus\(.*\)/target.*/lun.*/disc,\1,'`
	    target=`echo $1 | sed 's,/dev/scsi/host.*/bus.*/target\(.*\)/lun.*/disc,\1,'`
	    lun=`echo $1 | sed 's,/dev/scsi/host.*/bus.*/target.*/lun\(.*\)/disc,\1,'`
	    scsinum=$(($host + 1))
	    linux=$(mapdevfs $1)
	    linux=${linux#/dev/}
	    db_metaget partman/text/scsi_disk description
	    printf "$RET" ${scsinum} ${bus} ${target} ${lun} ${linux}
	    ;;
	/dev/scsi/host*/bus*/target*/lun*/part*)
	    host=`echo $1 | sed 's,/dev/scsi/host\(.*\)/bus.*/target.*/lun.*/part.*,\1,'`
	    bus=`echo $1 | sed 's,/dev/scsi/host.*/bus\(.*\)/target.*/lun.*/part.*,\1,'`
	    target=`echo $1 | sed 's,/dev/scsi/host.*/bus.*/target\(.*\)/lun.*/part.*,\1,'`
	    lun=`echo $1 | sed 's,/dev/scsi/host.*/bus.*/target.*/lun\(.*\)/part.*,\1,'`
	    part=`echo $1 | sed 's,/dev/scsi/host.*/bus.*/target.*/lun.*/part\(.*\),\1,'`
	    scsinum=$(($host + 1))
	    linux=$(mapdevfs $1)
	    linux=${linux#/dev/}
	    db_metaget partman/text/scsi_partition description
	    printf "$RET" ${scsinum} ${bus} ${target} ${lun} ${part} ${linux}
	    ;;
	/dev/sd[a-z]|/dev/sd[a-z][a-z])
	    disk="${1#/dev/}"
	    if [ -h "/sys/block/$disk/device" ]; then
		bus_id="$(basename "$(readlink "/sys/block/$disk/device")")"
		host="${bus_id%%:*}"
		bus_id="${bus_id#*:}"
		bus="${bus_id%%:*}"
		bus_id="${bus_id#*:}"
		target="${bus_id%%:*}"
		lun="${bus_id#*:}"
		scsinum="$(($host + 1))"
		db_metaget partman/text/scsi_disk description
		printf "$RET" "$scsinum" "$bus" "$target" "$lun" "$disk"
	    else
		# Can't figure out host/bus/target/lun without sysfs, but
		# never mind; if we don't have sysfs then we're probably on
		# 2.4 and devfs anyway.
		echo "$1"
	    fi
	    ;;
	/dev/sd[a-z][0-9]*|/dev/sd[a-z][a-z][0-9]*)
	    part="${1#/dev/}"
	    disk="${part%%[0-9]*}"
	    part="${part#$disk}"
	    if [ -h "/sys/block/$disk/device" ]; then
		bus_id="$(basename "$(readlink "/sys/block/$disk/device")")"
		host="${bus_id%%:*}"
		bus_id="${bus_id#*:}"
		bus="${bus_id%%:*}"
		bus_id="${bus_id#*:}"
		target="${bus_id%%:*}"
		lun="${bus_id#*:}"
		scsinum="$(($host + 1))"
		db_metaget partman/text/scsi_partition description
		printf "$RET" "$scsinum" "$bus" "$target" "$lun" "$part" "$disk"
	    else
		# Can't figure out host/bus/target/lun without sysfs, but
		# never mind; if we don't have sysfs then we're probably on
		# 2.4 and devfs anyway.
		echo "$1"
	    fi
	    ;;
	/dev/cciss/host*|/dev/cciss/disc*)
	    # /dev/cciss/hostN/targetM/disc is 2.6 devfs form
	    # /dev/cciss/discM/disk seems to be 2.4 devfs form
	    line=`echo $1 | sed 's,/dev/cciss/\([a-z]*\)\([0-9]*\)/\(.*\),\1 \2 \3,'`
	    controller=`echo "$line" | cut -d" " -f2`
	    host=`echo "$line" | cut -d" " -f1`
	    line=`echo "$line" | cut -d" " -f3`
	    if [ "$host" = host ] ; then
	       line=`echo "$line" | sed 's,target\([0-9]*\)/\([a-z]*\)\(.*\),\1 \2 \3,'`
	       lun=`echo  "$line" | cut -d" " -f1`
	       disk=`echo "$line" | cut -d" " -f2`
	       part=`echo "$line" | cut -d" " -f3`
	    else
	       line=`echo "$line" | sed 's,disc\([0-9]*\)/\([a-z]*\)\(.*\),\1 \2 \3,'`
	       lun=`echo  "$line" | cut -d" " -f1`
	       controller=$(($lun / 16))
	       lun=$(($lun % 16))
	       disk=`echo "$line" | cut -d" " -f2`
	       part=`echo "$line" | cut -d" " -f3`
	    fi
	    linux=$(mapdevfs $1)
	    linux=${linux#/dev/}
	    if [ "$disk" = disc ] ; then
	       db_metaget partman/text/scsi_disk description
	       printf "$RET" ".CCISS" "-" ${controller} ${lun} ${linux}
	    else
	       db_metaget partman/text/scsi_partition description
	       printf "$RET" ".CCISS" "-" ${controller} ${lun} ${part} ${linux}
	    fi
	    ;;
	/dev/cciss/c*d*)
	    # It would be a lot easier to parse the /sys/block/*/device
	    # symlink. Unfortunately, unlike other block devices, this
	    # doesn't seem to exist in this case, so we just have to live
	    # with parsing the device name (note: added in upstream 2.6.18).
	    controller="$(echo "$1" | sed 's,/dev/cciss/c\([0-9]*\).*,\1,')"
	    lun="$(echo "$1" | sed 's,/dev/cciss/c[0-9]*d\([0-9]*\).*,\1,')"
	    case $1 in
		/dev/cciss/c*d*p*)
		    # partition
		    part="$(echo "$1" | sed 's,/dev/cciss/c[0-9]*d[0-9]*p\([0-9]*\).*,\1,')"
		    ;;
		*)
		    part=
		    ;;
	    esac
	    linux="$(mapdevfs "$1")"
	    linux="${linux#/dev/}"
	    if [ -z "$part" ]; then
		db_metaget partman/text/scsi_disk description
		printf "$RET" ".CCISS" "-" "$controller" "$lun" "$linux"
	    else
		db_metaget partman/text/scsi_partition description
		printf "$RET" ".CCISS" "-" "$controller" "$lun" "$part" "$linux"
	    fi
	    ;;
	/dev/mmcblk[0-9])
	    drive=$(echo $1 | sed 's,^/dev/mmcblk\([0-9]\).*,\1,')
	    linux=${1#/dev/}
	    db_metaget partman/text/mmc_disk description
	    printf "$RET" "$(($drive + 1))" "$linux"
	    ;;
	/dev/mmcblk[0-9]p[0-9]*)
	    drive=$(echo $1 | sed 's,^/dev/mmcblk\([0-9]\).*,\1,')
	    part=$(echo $1 | sed 's,^/dev/mmcblk[0-9]p\([0-9][0-9]*\).*,\1,')
	    linux=${1#/dev/}
	    db_metaget partman/text/mmc_partition description
	    printf "$RET" "$(($drive + 1))" "$part" "$linux"
	    ;;
	/dev/md*|/dev/md/*)
	    device=`echo "$1" | sed -e "s/.*md\/\?\(.*\)/\1/"`
	    type=`grep "^md${device}[ :]" /proc/mdstat | sed -e "s/^.* : active raid\([[:alnum:]]\{,2\}\).*/\1/"`
	    db_metaget partman/text/raid_device description
	    printf "$RET" ${type} ${device}
	    ;;
	/dev/mapper/*)
	    type=$(dm_table "$1")

	    # First check for Serial ATA RAID devices
	    if type dmraid >/dev/null 2>&1 && \
	       dmraid -s -c >/dev/null 2>&1; then
		for frdisk in $(dmraid -s -c); do
			device=${1#/dev/mapper/}
			case "$1" in
			    /dev/mapper/$frdisk)
				type=sataraid
				desc=$(dmraid -s -c -c "$device")
				rtype=$(echo "$desc" | cut -d: -f4)
				db_metaget partman/text/dmraid_volume description
				printf "$RET" $device $rtype
				;;
			    /dev/mapper/$frdisk*)
				type=sataraid
				part=${device#$frdisk}
				db_metaget partman/text/dmraid_part description
				printf "$RET" $device $part
				;;
			esac
		done
	    fi

	    if [ "$type" = sataraid ]; then
		:
	    elif [ "$type" = crypt ]; then
	        mapping=${1#/dev/mapper/}
	        db_metaget partman/text/dmcrypt_volume description
	        printf "$RET" $mapping
	    elif [ "$type" = multipath ]; then
		device=${1#/dev/mapper/}
		wwid=$(multipath -l ${device} | head -n 1 | sed "s/^${device} \+(\([a-f0-9]\+\)).*/\1/")
		db_metaget partman/text/multipath description
		printf "$RET" ${device} ${wwid}
	    elif is_multipath_part $1; then
		part=$(echo "$1" | sed 's%.*-part\([0-9]\+\)$%\1%')
		device=$(echo "$1" | sed 's%/dev/mapper/\(.*\)-part[0-9]\+$%\1%')
		db_metaget partman/text/multipath_partition description
		printf "$RET" ${device} ${part}
	    else
	        # LVM2 devices are found as /dev/mapper/<vg>-<lv>.  If the vg
	        # or lv contains a dash, the dash is replaced by two dashes.
	        # In order to decode this into vg and lv, first find the
	        # occurance of one single dash to split the string into vg and
	        # lv, and then replace two dashes next to each other with one.
	        vglv=${1#/dev/mapper/}
	        vglv=`echo "$vglv" | sed 's/\([^-]\)-\([^-]\)/\1 \2/; s/--/-/g'`
	        vg=`echo "$vglv" | cut -d" " -f1`
	        lv=`echo "$vglv" | cut -d" " -f2`
	        db_metaget partman/text/lvm_lv description
	        printf "$RET" $vg $lv
	    fi
	    ;;
	/dev/linux_lvm/*)
	      # On GNU/kFreeBSD, LVM devices are found as /dev/linux_lvm/<vg>-<lv>.
	      vglv=${1#/dev/linux_lvm/}
	      vglv=`echo "$vglv" | sed 's/\([^-]\)-\([^-]\)/\1 \2/; s/--/-/g'`
	      vg=`echo "$vglv" | cut -d" " -f1`
	      lv=`echo "$vglv" | cut -d" " -f2`
	      db_metaget partman/text/lvm_lv description
	      printf "$RET" $vg $lv
	    ;;
	/dev/loop/*|/dev/loop*)
	    n=${1#/dev/loop}
	    n=${n#/}
	    db_metaget partman/text/loopback description
	    printf "$RET" $n
	    ;;
	# DASD partition, classic
	/dev/dasd*[0-9]*)
	    part="${1#/dev/}"
	    disk="${part%%[0-9]*}"
	    part="${part#$disk}"
	    humandev_dasd_partition /sys/block/$disk/$(readlink /sys/block/$disk/device) $part
	    ;;
	# DASD disk, classic
	/dev/dasd*)
	    disk="${1#/dev/}"
	    humandev_dasd_disk /sys/block/$disk/$(readlink /sys/block/$disk/device)
	    ;;
	/dev/*vd[a-z])
	    drive=$(printf '%d' "'$(echo $1 | sed 's,^/dev/x\?vd\([a-z]\).*,\1,')")
	    drive=$(($drive - 96))
	    linux=${1#/dev/}
	    db_metaget partman/text/virtual_disk description
	    printf "$RET" "$drive" "$linux"
	    ;;
	/dev/*vd[a-z][0-9]*)
	    drive=$(printf '%d' "'$(echo $1 | sed 's,^/dev/x\?vd\([a-z]\).*,\1,')")
	    drive=$(($drive - 96))
	    part=$(echo $1 | sed 's,^/dev/x\?vd[a-z]\([0-9][0-9]*\).*,\1,')
	    linux=${1#/dev/}
	    db_metaget partman/text/virtual_partition description
	    printf "$RET" "$drive" "$part" "$linux"
	    ;;
	/dev/ad[0-9]*[sp][0-9]*)
	    drive=$(echo $1 | sed 's,/dev/ad\([0-9]\+\).*,\1,')
	    drive=$(($drive + 1))
	    part=$(echo $1 | sed 's,/dev/ad[0-9]\+[sp]\([0-9]\+\).*,\1,')
	    kfreebsd=${1#/dev/}
	    db_metaget partman/text/ata_partition description
	    printf "$RET" "$drive" "$part" "$kfreebsd"
	    ;;
	/dev/ad[0-9]*)
	    drive=$(echo $1 | sed 's,/dev/ad\([0-9]\+\).*,\1,')
	    drive=$(($drive + 1))
	    kfreebsd=${1#/dev/}
	    db_metaget partman/text/ata_disk description
	    printf "$RET" "$drive" "$kfreebsd"
	    ;;
	/dev/da[0-9]*[sp][0-9]*)
	    drive=$(echo $1 | sed 's,/dev/da\([0-9]\+\).*,\1,')
	    drive=$(($drive + 1))
	    part=$(echo $1 | sed 's,/dev/da[0-9]\+[sp]\([0-9]\+\).*,\1,')
	    kfreebsd=${1#/dev/}
	    db_metaget partman/text/scsi_simple_partition description
	    printf "$RET" "$drive" "$part" "$kfreebsd"
	    ;;
	/dev/da[0-9]*)
	    drive=$(echo $1 | sed 's,/dev/da\([0-9]\+\).*,\1,')
	    drive=$(($drive + 1))
	    kfreebsd=${1#/dev/}
	    db_metaget partman/text/scsi_simple_disk description
	    printf "$RET" "$drive" "$kfreebsd"
	    ;;
	/dev/zvol/*)
	    pool=`echo "$1" | sed -e 's,/dev/zvol/\([^/]*\)/[^/]*,\1,'`
	    zvol=`echo "$1" | sed -e 's,/dev/zvol/[^/]*/\([^/]*\),\1,'`
	    db_metaget partman/text/zfs_volume description
	    printf "$RET" "$pool" "$zvol"
	    ;;
	*)
	    # Check if it's an LVM1 device
	    vg=`echo "$1" | sed -e 's,/dev/\([^/]\+\).*,\1,'`
	    lv=`echo "$1" | sed -e 's,/dev/[^/]\+/,,'`
	    if [ -e "/proc/lvm/VGs/$vg/LVs/$lv" ] ; then
		db_metaget partman/text/lvm_lv description
		printf "$RET" $vg $lv
	    else
		echo "$1"
	    fi
	    ;;
    esac
}

humandev_dasd_disk () {
	dev=${1##*/}
	discipline=$(cat $1/discipline)
	db_metaget partman/text/dasd_disk description
	printf "$RET" "$dev" "$discipline"
}

humandev_dasd_partition () {
	dev=${1##*/}
	discipline=$(cat $1/discipline)
	db_metaget partman/text/dasd_partition description
	printf "$RET" "$dev" "$discipline" "$part"
}

device_name () {
	cd $1
	printf "%s - %s %s" "$(humandev $(cat device))" "$(longint2human $(cat size))" "$(cat model)"
}

enable_swap () {
    local swaps dev num id size type fs path name method
    local startdir="$(pwd)"
    # do swapon only when we will be able to swapoff afterwards
    [ -f /proc/swaps ] || return 0
    swaps=''
    for dev in $DEVICES/*; do
	[ -d $dev ] || continue
	cd $dev
	open_dialog PARTITIONS
	while { read_line num id size type fs path name; [ "$id" ]; }; do
	    [ $fs != free ] || continue
	    [ -f "$id/method" ] || continue
	    method=$(cat $id/method)
	    if [ "$method" = swap ]; then
		swaps="$swaps $path"
	    fi
	done
	close_dialog
    done
    for path in $swaps; do
	if ! grep -q "^$(readlink -f "$path") " /proc/swaps; then
	    swapon $path 2>/dev/null || true
	fi
    done
    cd "$startdir"
}

disable_swap () {
    local dev=$1
    local id=$2

    [ -f /proc/swaps ] || return 0

    if [ "$dev" ] && [ -d "$dev" ]; then
	local device
	cd $dev
	if [ "$id" ] && [ -d "$id" ]; then
	    open_dialog PARTITION_INFO "$id"
	    read_line x1 x2 x3 x4 x5 device x7
	    close_dialog
	    # Add space to ensure we won't match substrings.
	    device="$device "
	else
	    device=$(cat device)
	fi

	grep "^$device" /proc/swaps \
	    | while read path x; do
		  swapoff $path
	      done
    else
	grep '^/dev' /proc/swaps | egrep -v '^/dev/(ramzswap|zram)' \
	    | while read path x; do
		  swapoff $path
	      done
    fi
}

# Lock a device or partition against further modifications
partman_lock_unit() {
	local device message cwd dev testdev
	local num id size type fs path name
	device="$1"
	message="$2"

	# We need to preserve the current working directory as the caller might
	# be working on a specific device.  See #488687 for details.
	cwd="$(pwd)"
	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev

		# First check if we should lock a device
		if [ -e device ]; then
			testdev=$(mapdevfs $(cat device))
			if [ "$device" = "$testdev" ]; then
				echo "$message" > locked
				cd "$cwd"
				return 0
			fi
		fi

		# Second check if we should lock a partition
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			testdev=$(mapdevfs $path)
			if [ "$device" = "$testdev" ]; then
				echo "$message" > $id/locked
			fi
		done
		close_dialog
	done
	cd "$cwd"
}

# Unlock a device or partition to allow further modifications
partman_unlock_unit() {
	local device cwd dev testdev
	local num id size type fs path name
	device="$1"

	# See partman_lock_unit() for details about $cwd.
	cwd="$(pwd)"
	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev

		# First check if we should unlock a device
		if [ -e device ]; then
			testdev=$(mapdevfs $(cat device))
			if [ "$device" = "$testdev" ]; then
				rm -f locked
				cd "$cwd"
				return 0
			fi
		fi

		# Second check if we should unlock a partition
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			testdev=$(mapdevfs $path)
			if [ "$device" = "$testdev" ]; then
				rm -f $id/locked
			fi
		done
		close_dialog
	done
	cd "$cwd"
}

partman_list_allowed() {
	local allowed_func=$1
	local IFS
	local partitions
	local freenum=1
	for dev in $DEVICES/*; do
		[ -d $dev ] || continue
		cd $dev

		open_dialog PARTITIONS
		partitions="$(read_paragraph)"
		close_dialog

		local id size fs path
		IFS="$TAB"
		echo "$partitions" |
		while { read x1 id size x4 fs path x7; [ "$id" ]; }; do
			restore_ifs
			if $allowed_func "$dev" "$id"; then
				if [ "$fs" = free ]; then
					printf "%s\t%s\t%s\t%s free #%d\n" "$dev" "$id" "$size" "$(mapdevfs "$(cat "$dev/device")")" "$freenum"
					freenum="$(($freenum + 1))"
				else
					printf "%s\t%s\t%s\t%s\n" "$dev" "$id" "$size" "$(mapdevfs "$path")"
				fi
			fi
			IFS="$TAB"
		done
		restore_ifs
	done
}


[ "$PARTMAN_TEST" ] || log '*******************************************************'

# Local Variables:
# coding: utf-8
# End:
