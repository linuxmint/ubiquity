Introduction
============

This document describes how to setup and run automated autopilot tests of
Ubiquity. These testcases work for Ubuntu, Xubuntu and Lubuntu. and should work
for all other flavours of Ubuntu.

Source code: `lp:ubiquity`

Tests use python3 version of autopilot.

When this code is modified, check that it is compliant with PEP8 and there is
no pyflakes error by executing the following command in the top directory of
the checkout:

    $ fakeroot debian/rules check


Project Structure
=================

The project is structured as follow:

 * *autopilot/* Contains the tests, the runner and a wrapper for autopilot and
   ubiquity

   * *ubiquity-autopilot-runner/* Runner to setup a VM from an ISO
     and execute autopilot tests

     * *config/* Contains configuration examples to override default values of
       the runner

     * *custom-installation/iso-override/* Content of this directory will
       override the content on the ISO

     * *jenkins/* Scripts, templates and configuration files to deply jenkins
       jobs

   * *ubiquity_autopilot_tests/* Autopilot tests


Running the tests
=================

Directly from a Live Session
----------------------------

Install the following dependencies :

    $ sudo apt-get install python-autopilot libautopilot-gtk python-xlib

To run the tests, open 2 terminals.

Run in Terminal 1 :

    $ cd ubiquity/autopilot
    $ ./run_ubiquity

To execute the test *test_english_default* Run in Terminal 2:

    $ cd ubiquity/autopilot
    $ ./autopilot run ubiquity_autopilot_tests.tests.test_english_default

Other tests are available from *ubiquity_autopilot_tests/tests/*. To get a list
of available tests run:

    $ autopilot-py3 list ubiquity_autopilot_tests.tests

On a local machine with the runner
----------------------------------

 * Install the following dependencies:

        $ sudo apt-get install bsdtar qemu-system-x86 bzr xz-utils cpio

 * Download a desktop image from *http//cdimage.ubuntu.com/*

 * Execute the command:
    
        $ ./ubiquity-autopilot-runner/run-ubiquity-test <ISO> 
        e.g
        $ ./ubiquity-autopilot-runner/run-ubiquity-test ~/iso/ubuntu/trusty-desktop-amd64.iso

 * If you want to watch what is running use option `--sdl`

 * If your system have enough memory you can run tests in memory (in /dev/shm
   actually) with option `-s|--shm`

 * And of course `-h|--help` for a list of available options

 * At the end of the run, results are collected in `/tmp/ubiquity.tests`

Executing in Jenkins
====================

Execute the tasks below on the slave:

 * Create a user called `ubiquity`. This account will pull all the code
   required to execute the tests. It can update the code without any specific
   jenkins privileges. You can then import ssh keys of the person you want to
   be able to manage this account.

 * Create a directory `$HOME/bin` for this user.

 * Branch ubiquity trunk:

        $ bzr branch lp:ubiquity

 * Branch ubuntu-qa-tools (to get the script `dl-ubuntu-test-iso`)

        $ bzr branch lp:ubuntu-qa-tools

 * Get the script `download-latest-test-iso.py` from the project
   `lp:ubuntu-server-iso-testing`. This script is a wrapper around
   dl-ubuntu-test-iso that adds additional checksums validation, cache and lock
   handling to run multiple time in parallel.

        $ bzr cat lp:ubuntu-server-iso-testing/download-latest-test-iso.py > ~/bin/download-latest-test-iso.py

 * Create the following links in ~/bin/

        $ ln -s ~/ubuntu-qa-tools/dl-ubuntu-test-iso/dl-ubuntu-test-iso ~/bin
        $ ln -s ~/ubiquity/autopilot/ubiquity-autopilot-runner/jenkins/publish2jenkins

 * On **jenkins server** create an account in jenkins with job management
   privileges.
   
 * On the slave create a credential file in ~/.jenkins.credentials for the
   account create on the server with the following content:

        <INSTANCE>:  # Name of the instance, must match SERVER in publish2jenkins
            username: <JENKINS USER NAME>
            password: <JENKINS PASSWORD>
            url: <JENKINS SERVER URL>
            token: <REMOTE JOBS TOKEN>

 * Login as **user jenkins** and create the directory `bin`

 * Create the same symlinks than symlinks in `/home/ubiquity/bin/`

        $ find /home/ubiquity/bin/ ! -type d -exec ln -s {} $HOME/bin/

 * **Logout** from user jenkins

 * As **user ubiquity** deploy jenkins jobs:

        $ publish2jenkins

 * If it runs without error, verify that jenkins jobs are created or updated if
   they already existed on `<JENKINS SERVER URL>`

 * On **jenkins server** create the following jenkins views:
   
   * **Main** view is a `nested view` that defaults to `All`
   
   * **All** view is a `dashboard view` with the following configuration:

     * Regular expression to include jobs: `ubiquity_ap.*`

     * Left portlet: `Unstable jobs` and `Jobs statistics`

     * Right portlet: `Latest builds`

     * Bottom portlet: `Jenkins jobs list`

   * Each **flavor view** is a list view with a regular expression to include
     jobs set to `ubiquity_ap-<FLAVOR>_.*` . Replace `<FLAVOR>` by the name of
     the flavor.

The hierachy of jobs is:

 * `ubiquity_ap-<flavor>_devel_daily-download`: Monitor the publication of new
   images, download the image and start a new run

   * `ubiquity_ap-<flavor>_devel_daily-run`: Run all the tests for a given
     flavor.

     * `ubiquity_ap-flavor_devel_daily-<test>`: Executes a test for a flavor.
       This is a matrix job with an architecture axis. Supported architectures
       are amd64 and i386.
       There is one job for each test defined in the flavor
       configuration file in `ubiquity-autopilot-runner/jenkins/config/`

The tests will start automatically when a new image is available. This is done
a URL content's change trigger that monitor the URL defined in the flavor
configuration file; for example
`http://cdimage.ubuntu.com/daily-live/pending/MD5SUMS`

You can run a specific flavor manually from jenkins by running the job
`ubiquity_ap-ubuntu_devel_daily-download` if there is no ISO already downloaded
on the system, or `ubiquity_ap-ubuntu_devel_daily-run` is an ISO is already
present.

To modifiy jenkins configuration, do not do it directly from the UI but instead
either modify the template in
`ubiquity/autopilot/ubiquity-autopilot-runner/jenkins/templates/` or the configuration
of the flavor in `ubiquity/autopilot/ubiquity-autopilot-runner/jenkins/config/`

To add a new flavor, add a configuration file for the flavor in
`ubiquity/autopilot/ubiquity-autopilot-runner/jenkins/config/`.

To add/remove/modify the list of autopilot tests to run for a flavor, change it
in its configuration file.

Contact Information
-------------------

Authors: 
    Dan Chapman <dpniel@ubuntu.com>
    Jean-Baptiste Lallement <jean-baptiste.lallement@ubuntu.com>

Report Autopilot tests or test runner bugs at: http://bugs.launchpad.net/ubiquity
