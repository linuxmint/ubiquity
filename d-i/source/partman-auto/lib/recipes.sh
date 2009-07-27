# If you are curious why partman-auto is so slow, it is because
# update-all is slow
update_all () {
	local dev num id size type fs path name partitions
	for dev in $DEVICES/*; do
		[ -d "$dev" ] || continue
		cd $dev
		partitions=''
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			partitions="$partitions $id"
		done
		close_dialog
		for id in $partitions; do
			update_partition $dev $id
		done
	done
}

autopartitioning_failed () {
	db_input critical partman-auto/autopartitioning_failed || true
	db_go || true
	update_all
	exit 1
}

unnamed=0

decode_recipe () {
	local ignore ram line word min factor max fs -
	ignore="${2:+${2}ignore}"
	unnamed=$(($unnamed + 1))
	ram=$(grep ^Mem: /proc/meminfo | { read x y z; echo $y; }) # in bytes
	if [ -z "$ram" ]; then
		ram=$(grep ^MemTotal: /proc/meminfo | { read x y z; echo $y; })000
	fi
	ram=$(convert_to_megabytes $ram)
	name="Unnamed.${unnamed}"
	scheme=''
	line=''
	for word in $(cat $1); do
		case $word in
		    :)
			name=$line
			line=''
			;;
		    ::)
			db_metaget $line description || RET=''
			name="${RET:-Unnamed.$unnamed}"
			line=''
			;;
		    .)
			# we correct errors in order not to crash parted_server
			set -- $line
			if expr "$1" : '[0-9][0-9]*$' >/dev/null; then
				min=$1
			elif expr "$1" : '[0-9][0-9]*%$' >/dev/null; then
				min=$(($ram * ${1%?} / 100))
			else # error
				min=2200000000 # there is no so big storage device jet
			fi
			if expr "$2" : '[0-9][0-9]*%$' >/dev/null; then
				factor=$(($ram * ${2%?} / 100))
			elif expr "$2" : '[0-9][0-9]*$' >/dev/null; then
				factor=$2
			else # error
				factor=$min # do not enlarge the partition
			fi
			if [ $factor -lt $min ]; then
				factor=$min
			fi
			if [ "$3" = "-1" ] || \
			   expr "$3" : '[0-9][0-9]*$' >/dev/null; then
				max=$3
			elif expr "$3" : '[0-9][0-9]*%$' >/dev/null; then
				max=$(($ram * ${3%?} / 100))
			else # error
				max=$min # do not enlarge the partition
			fi
			if [ $max -ne -1 ] && [ $max -lt $min ]; then
				max=$min
			fi
			case "$4" in # allow only valid file systems
			    ext2|ext3|ext4|xfs|reiserfs|jfs|linux-swap|fat16|fat32|hfs)
				fs="$4"
				;;
			    \$default_filesystem)
				db_get partman/default_filesystem
				fs="$RET"
				;;
			    *)
				fs=ext2
				;;
			esac
			shift; shift; shift; shift
			line="$min $factor $max $fs $*"

			# Exclude partitions that have ...ignore set
			if [ "$ignore" ] && [ "$(echo $line | grep "$ignore")" ]; then
				:
			else
				scheme="${scheme:+$scheme$NL}$line"
			fi
			line=''
			;;
		    *)
			line="${line:+$line }$word"
			;;
		esac
	done
}

foreach_partition () {
	local - doing IFS pcount last partition
	doing=$1
	pcount=$(echo "$scheme" | wc -l)
	last=no

	IFS="$NL"
	for partition in $scheme; do
		restore_ifs
		[ $pcount -gt 1 ] || last=yes
		set -- $partition
		eval "$doing"
		pcount=$(($pcount - 1))
	done
}

min_size () {
	local size
	size=0
	foreach_partition '
		size=$(($size + $1))'
	echo $size
}

factor_sum () {
	local factor
	factor=0
	foreach_partition '
		factor=$(($factor + $2))'
	echo $factor
}

partition_before () {
	local num id size type fs path name result found
	result=''
	found=no
	open_dialog PARTITIONS
	while { read_line num id size type fs path name; [ "$id" ]; }; do
		if [ "$id" = "$1" ]; then
			found=yes
		fi
		if [ $found = no ]; then
			result=$id
		fi
	done
	close_dialog
	echo $result
}

partition_after () {
	local num id size type fs path name result found
	result=''
	found=no
	open_dialog PARTITIONS
	while { read_line num id size type fs path name; [ "$id" ]; }; do
		if [ $found = yes ] && [ -z "$result" ]; then
			result=$id
		fi
		if [ "$id" = "$1" ]; then
			found=yes
		fi
	done
	close_dialog
	echo $result
}

pull_primary () {
	primary=''
	scheme_rest=''
	foreach_partition '
		if [ -z "$primary" ] && \
		   echo $* | grep '\''\$primary{'\'' >/dev/null; then
			primary="$*"
		else
			scheme_rest="${scheme_rest:+$scheme_rest$NL}$*"
		fi'
}

setup_partition () {
	local id flags file line
	id=$1; shift
	while [ "$1" ]; do
		case "$1" in
		    \$bootable{)
			while [ "$1" != '}' ] && [ "$1" ]; do
				shift
			done
			open_dialog GET_FLAGS $id
			flags=$(read_paragraph)
			close_dialog
			open_dialog SET_FLAGS $id
			write_line "$flags"
			write_line boot
			write_line NO_MORE
			close_dialog
			;;
		    \$default_filesystem{)
			while [ "$1" != '}' ] && [ "$1" ]; do
				shift
			done
			mkdir -p $id
			db_get partman/default_filesystem
			echo "$RET" >$id/filesystem
			;;
		    \$*{)
			while [ "$1" != '}' ] && [ "$1" ]; do
				shift
			done
			;;
		    *{)
			file=${1%?}
			mkdir -p $id
			case $file in
			    */*)
				mkdir -p $id/${file%/*}
				;;
			esac
			>$id/$file
			shift
			line=''
			while [ "$1" != '}' ] && [ "$1" ]; do
				if [ "$1" = ';' ]; then
					echo "$line" >>$id/$file
				else
					line="${line:+$line }$1"
				fi
				shift
			done
			echo "$line" >>$id/$file
		esac
		shift
	done
	return 0
}

get_recipedir () {
	local archdetect arch sub recipedir

	if type archdetect >/dev/null 2>&1; then
		archdetect=$(archdetect)
	else
		archdetect=unknown/generic
	fi
	arch=${archdetect%/*}
	sub=${archdetect#*/}

	for recipedir in \
	    /lib/partman/recipes-$arch-$sub \
	    /lib/partman/recipes-$arch \
	    /lib/partman/recipes; do
	if [ -d $recipedir ]; then
		echo $recipedir
		break
	fi
	done
}

choose_recipe () {
	local recipes recipedir free_size choices min_size type target

	type=$1
	target="$2"
	free_size=$3

	# Preseeding of recipes
	db_get partman-auto/expert_recipe
	if [ -n "$RET" ]; then
		echo "$RET" > /tmp/expert_recipe
		db_set partman-auto/expert_recipe_file /tmp/expert_recipe
	fi
	db_get partman-auto/expert_recipe_file
	if [ ! -z "$RET" ] && [ -e "$RET" ]; then
		recipe="$RET"
		decode_recipe $recipe $type
		if [ $(min_size) -le $free_size ]; then
			return 0
		else
			logger -t partman-auto \
			"Expert recipe too large ($(min_size) > $free_size); skipping"
		fi
	fi

	recipedir=$(get_recipedir)

	choices=''
	default_recipe=no
	db_get partman-auto/choose_recipe
	old_default_recipe="$RET"
	for recipe in $recipedir/*; do
		[ -f "$recipe" ] || continue
		decode_recipe $recipe $type
		if [ $(min_size) -le $free_size ]; then
			choices="${choices}${recipe}${TAB}${name}${NL}"
			if [ "$default_recipe" = no ]; then
				default_recipe="$recipe"
			fi
			if [ "$old_default_recipe" = "$name" ]; then
				default_recipe="$recipe"
			else
				local base="$(basename "$recipe")"
				if [ "$old_default_recipe" = "$base" ] || \
				   [ "$old_default_recipe" = "${base#[0-9][0-9]}" ]; then
					default_recipe="$recipe"
				fi
			fi
		fi
	done

	if [ -z "$choices" ]; then
		db_input critical partman-auto/no_recipe || true
		db_go || true # TODO handle backup right
		return 1
	fi

	db_subst partman-auto/choose_recipe TARGET "$target"
	debconf_select medium partman-auto/choose_recipe \
		"$choices" "$default_recipe"
	if [ $? = 255 ]; then
		return 255
	fi
	recipe="$RET"
}

expand_scheme() {
	# Make factors small numbers so we can multiply on them.
	# Also ensure that fact, max and fs are valid
	# (Ofcourse in valid recipes they must be valid.)
	factsum=$(($(factor_sum) - $(min_size)))
	if [ $factsum -eq 0 ]; then
		factsum=100
	fi
	scheme=$(
	    foreach_partition '
		local min fact max fs
		min=$1
		fact=$((($2 - $min) * 100 / $factsum))
		max=$3
		fs=$4
		case "$fs" in
		    ext2|ext3|ext4|linux-swap|fat16|fat32|hfs)
			true
			;;
		    *)
			fs=ext2
			;;
		esac
		shift; shift; shift; shift
		echo $min $fact $max $fs $*'
	)

	oldscheme=''
	while [ "$scheme" != "$oldscheme" ]; do
		oldscheme="$scheme"
		factsum=$(factor_sum)
		unallocated=$(($free_size - $(min_size)))
		if [ $unallocated -lt 0 ]; then
			unallocated=0
		fi
		scheme=$(
		    foreach_partition '
			local min fact max newmin
			min=$1
			fact=$2
			max=$3
			shift; shift; shift
			if [ $factsum -eq 0 ]; then
				newmin=$min
				if [ $fact -lt 0 ]; then
					fact=0
				fi
			else
				newmin=$(($min + $unallocated * $fact / $factsum))
			fi
			if [ $max -ne -1 ] && [ $newmin -gt $max ]; then
				echo $max 0 $max $*
			elif [ $newmin -lt $min ]; then
				echo $min 0 $min $*
			else
				echo $newmin $fact $max $*
			fi'
		)
	done
}

clean_method() {
	for device in $DEVICES/*; do
		[ -d "$device" ] || continue
		cd $device
		open_dialog PARTITIONS
		while { read_line num id size type fs path name; [ "$id" ]; }; do
			rm -f $id/method
		done
		close_dialog
	done
}
