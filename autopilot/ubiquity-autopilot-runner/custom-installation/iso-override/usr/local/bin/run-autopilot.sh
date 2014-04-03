#!/bin/sh

#
# This script runs autopilot
#

# Copyright © 2013 Canonical Ltd.
# Author: Jean-baptiste Lallement <jean-baptiste.lallement@canonical.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License version 2, as published by the
# Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
set -eu

# Lock management to prevent this script of running twice
LOCKFILE=/tmp/$(basename $0).lock
if [ -e ${LOCKFILE} ] && kill -0 $(cat ${LOCKFILE}); then
    echo "W: $(basename $0) already running. Exiting!"
    exit
fi
echo $$>${LOCKFILE}

# The following variables can be overridden with a configuration file
TSBRANCH=lp:ubiquity
EXTRAPACKAGES=""
ARTIFACTS=""
AP_OPTS="-v"
SHUTDOWN=1
TIMEOUT=1200  # 20min timeout
DEBUG=0
SHAREDVOL=""

# Custom configuration
# Do not use the variable TESTBASE because we don't want it to be overridden
[ -f /var/local/autopilot/config ] && . /var/local/autopilot/config

TESTBASE=/var/local/autopilot/
AP_ARTIFACTS=$TESTBASE/videos/
AP_RESULTS=$TESTBASE/junit/
AP_LOGS=$TESTBASE/logs/
AP_TESTSUITES=$TESTBASE/testsuites
AP_LOGFILE=$AP_LOGS/autopilot.log
AP_SUMMARY=$AP_LOGS/summary.log
AP_INFO=$AP_LOGS/build_info.txt
RMD_OPTS="-r -rd $AP_ARTIFACTS --record-options=--fps=6,--no-wm-check"
SPOOLDIR=$TESTBASE/spool
TSEXPORT=$HOME/ubiquity-autopilot
SESSION_LOG=""
# Append mandatory artifacts
ARTIFACTS="$TESTBASE /var/log/installer /var/log/syslog $HOME/.cache/upstart /var/crash $ARTIFACTS"


# Specific configurations for various DE
case $SESSION in
    ubuntu)    # Covers Ubuntu and Edubuntu
        SESSION_LOG=$HOME/.cache/upstart/gnome-session.log
        ;;
    xubuntu)
        SESSION_LOG=$HOME/.cache/upstart/startxfce4.log
        ;;
    Lubuntu)
        SESSION_LOG=$HOME/.cache/lxsession/Lubuntu/run.log
        ARTIFACTS="$ARTIFACTS $HOME/.cache/lxsession"
        ;;
    gnome)     # ubuntu-gnome
        SESSION_LOG=$HOME/.cache/upstart/gnome-session.log
esac

PACKAGES="bzr ssh python3-autopilot libautopilot-gtk python3-xlib \
    recordmydesktop"

export DEBIAN_FRONTEND=noninteractive

on_exit() {
    # Exit handler
    echo "I: Archiving artifacts"
    archive=/tmp/artifacts

    # Attempt to retrieve crash information
    if [ -n "$(ls /var/crash/)" ]; then
        export CRASH_DB_URL=https://daisy.ubuntu.com 
        export CRASH_DB_IDENTIFIER=$(echo ubiquity_autopilot_$(lsb_release -sc)_$(arch)|sha512sum|cut -d' ' -f1)
        sudo -E whoopsie||true
        sleep 3
        [ -x "/usr/share/apport/whoopsie-upload-all" ] && echo "I: Uploading crash files" && sudo -E /usr/share/apport/whoopsie-upload-all -t 300
        chmod og+r /var/crash/* 2>/dev/null || true
    fi

    for artifact in $ARTIFACTS; do
        [ -e "$artifact" ] && sudo tar rf ${archive}.tar $artifact || true
    done

    # Find a better way. ttys are a bit limited and sometimes output is
    # truncated or messages are skipped by the kernel if it goes too fast.
    if [ -f ${archive}.tar ]; then
        sudo stty -F /dev/ttyS1 raw speed 115200
        gzip -9 -c ${archive}.tar > ${archive}.tgz
        sudo sh -c "cat ${archive}.tgz>/dev/ttyS1"
    fi

    rm -f ${LOCKFILE}
    shutdown_host
}
trap on_exit EXIT INT QUIT ABRT PIPE TERM

usage() {
    # Display usage and exit
    cat<<EOF
Usage: $(basename $0) [OPTIONS...]
Run autopilot tests in $SPOOLDIR

Options:
  -h, --help      This help
  -d, --debug     Enable debug mode
  -N, --new       Restart all the tests in $AP_TESTSUITES otherwise
                  only the remaining tests in $SPOOLDIR are run
  -R, --norecord  Do not use recordmydesktop.
  -S, --noshutdown
                  Do not shutdown the system after the tests

EOF
    exit 1
}

# retry command a certain number of time
# $1 is the number of retry
# $2 is the delay in second between retries
# the command is then passed
retry_cmd() {
    # Tries to execute $@ $loop times with a delay of $delay between retries
    # before aborting
    loop=$1
    loopcnt=$1  # Just used to print the status on failure
    delay=$2
    shift
    shift
    while [ $loop -gt 0 ]; do
        rc=0
        $@ || rc=$?
        [ $rc -eq 0 ] && return
        loop=$((loop - 1))
        sleep $delay
    done

    echo "E: Command failed after $loopcnt tries: $@"
    echo "E: Aborting!"
    exit 1
}

setup_tests() {
    # Prepares the environment for the tests
    flag=$HOME/.ap_setup_done

    [ -e "$flag" ] && return 0


    if [ $DEBUG -ne 0 ]; then
        # Put here everything you want to run in debug mode
        xterm &  # Easier to debug from a live session, and rarely broken
    fi

    sudo stty -F /dev/ttyS0 raw speed 115200
    
    tail_logs $SESSION_LOG /var/log/syslog
    # Disable notifications and screensaver
    if which gsettings >/dev/null 2>&1; then 
        echo "I: Disabling crash notifications"
        gsettings set com.ubuntu.update-notifier show-apport-crashes false
        echo "I: Disabling screensaver"
        gsettings set org.gnome.desktop.screensaver idle-activation-enabled false
    fi

    # Loads the list of test and queue them in test spool
    sudo mkdir -p $SPOOLDIR $AP_ARTIFACTS $AP_RESULTS $AP_LOGS
    sudo chown -R $USER:$USER $TESTBASE $SPOOLDIR $AP_ARTIFACTS $AP_RESULTS $AP_LOGS

    echo "I: Installating additional packages"
    retry_cmd 3 30 sudo apt-get update
    retry_cmd 3 30 sudo apt-get install -yq $PACKAGES $EXTRAPACKAGES
    echo "I: Purging ubiquity-slideshow"
    sudo apt-get autoremove --purge -y $(dpkg -l "ubiquity-slideshow-*"|awk '/^ii/ {print $2}')||true

    if [ -n "$SHAREDVOL" ]; then
        echo "I: Mounting $SHAREDVOL on $TSEXPORT"
        mkdir -p $TSEXPORT
        sudo mount -t 9p -o trans=virtio,access=any $SHAREDVOL $TSEXPORT
        sudo chmod 777 $TSEXPORT
    else
        echo "I: Branch $TSBRANCH"
        bzr export $TSEXPORT $TSBRANCH
    fi

    if [ -e "$AP_TESTSUITES" ]; then
        (cd $SPOOLDIR; touch $(cat $AP_TESTSUITES))
    fi

    cat>$AP_INFO<<EOF
Image Id:      $(cat /cdrom/.disk/info)
Ubiquity:      $(dpkg-query -f '${Version}' -W ubiquity)
Test branch:   ${TSBRANCH}
Test revno:    $(bzr revno $TSBRANCH)
EOF
    
    cat<<EOF

============================== Test Info ============================== 
$(cat $AP_INFO)
======================================================================= 

EOF
    touch $flag

    dpkg -l > $AP_LOGS/packages.list
}

shutdown_host() {
    # Shutdown host
    sleep 10
    if [ $SHUTDOWN -eq 1 ]; then
        echo "I: Shutting down test environment"
        sudo shutdown -h now
    else
        echo "I: Shutdown disabled, host will keep running"
    fi
}

tail_logs() {
    # Tail log files in -F mode in background
    #   
    # $@ List of log files
    for log in $@; do
        if [ -f "$log" ]; then
            sudo sh -c "/bin/busybox tail -n0 -f $log | mawk -Winteractive -v logfile=\"$log\" '{print logfile\":\",\$0}' > /dev/ttyS0" &
        fi
    done
    }


run_tests() {
    # Runs all the tests in spooldir
    #
    # $1: Spool directory
    spooldir=$1
    if [ ! -d $spooldir ]; then
        echo "E: '$spooldir is not a directory. Exiting!"
        exit 1
    fi

    if ! which autopilot-py3 >/dev/null 2>&1; then
        echo "E: autopilot is required to run autopilot tests"
        echo "autopilot_installed (see autopilot.log for details): ERROR" >> $AP_SUMMARY
        shutdown_host
        exit 1
    fi
    echo "autopilot_installed: PASS" >> $AP_SUMMARY

    exec >>$AP_LOGFILE
    exec 2>&1
    touch $AP_LOGFILE
    tail_logs $AP_LOGFILE

    echo "I: Launching Ubiquity"
    cd $TSEXPORT/autopilot
    sudo dbus-launch ubiquity --autopilot &
    sleep 30
    tail_logs /var/log/installer/debug
    for testfile in $(ls -d $spooldir/* 2>/dev/null); do
        testname=$(basename $testfile)
        echo "I: Running autopilot run $testname $AP_OPTS -o $AP_RESULTS/$testname.xml"
        aprc=0
        timeout -s 9 -k 30 $TIMEOUT ./autopilot run $testname $AP_OPTS -f xml -o $AP_RESULTS/${testname}.xml||aprc=$?
        if [ $aprc -gt 0 ]; then
            echo "${testname}: FAIL" >> $AP_SUMMARY
        else
            echo "${testname}: DONE" >> $AP_SUMMARY
        fi
        sudo rm -f $testfile
    done
}

reset_test() {
    # Reset the tests for a new run
    rm -f $HOME/.ap_setup_done $AP_SUMMARY $AP_LOGFILE $SPOOLDIR/* $AP_ARTIFACTS/* $AP_RESULTS/*
}
SHORTOPTS="hdNRS"
LONGOPTS="help,debug,new,norecord,noshutdown"

TEMP=$(getopt -o $SHORTOPTS --long $LONGOPTS -- "$@")
eval set -- "$TEMP"

while true ; do
    case "$1" in
    -h|--help)
        usage;;
    -d|--debug)
        set -x
        shift;;
    -N|--new)
        reset_test
        shift;;
    -R|--norecord)
        RMD_OPTS=""
        shift;;
    -S|--noshutdown)
        SHUTDOWN=0
        shift;;
    --) shift;
        break;;
    *) usage;;
    esac
done

setup_tests
if [ -f "/usr/lib/libeatmydata/libeatmydata.so" ]; then
    echo "I: Enabling eatmydata"
    export LD_PRELOAD="${LD_PRELOAD:+$LD_PRELOAD:}/usr/lib/libeatmydata/libeatmydata.so"
fi
# Specific option for recordmydesktop for unity tests
# It is suspected to caused memory fragmentation and make the test crash
if [ -e "$AP_TESTSUITES" ]; then
    if grep -qw "unity" "$AP_TESTSUITES" 2>/dev/null; then
        RMD_OPTS="$RMD_OPTS --record-options=--fps=6,--no-wm-check"
    fi
fi

if which recordmydesktop >/dev/null 2>&1; then
    AP_OPTS="$AP_OPTS $RMD_OPTS"
fi

run_tests $SPOOLDIR

exit 0
