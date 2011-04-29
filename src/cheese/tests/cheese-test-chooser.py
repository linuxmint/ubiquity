#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- Mode: Python -*-
# vim:si:ai:et:sw=4:sts=4:ts=4

""" Cheese Test chooser """

import sys
CHEESE_LIBPATH = '../.libs'
sys.path.insert(0,CHEESE_LIBPATH)
import cheese as CH
import gtk

import gettext
import locale

PACKAGE_LOCALEDIR = '/usr/share/locale/'
GETTEXT_PACKAGE = 'cheese'


def init_i18n():
    locale.setlocale(locale.LC_ALL, '')
    gettext.bindtextdomain(GETTEXT_PACKAGE, PACKAGE_LOCALEDIR)
    gettext.textdomain(GETTEXT_PACKAGE)
    gettext.install(GETTEXT_PACKAGE, PACKAGE_LOCALEDIR)


def destroy(*args):
    """ Callback function that is activated when the program is destoyed """
    gtk.main_quit()


def response_cb(widget, response,chooser):
    if response == gtk.RESPONSE_ACCEPT:
        print "PixBuf captured"
        print chooser.get_property('pixbuf')    
    gtk.main_quit()


def main(args):

    gtk.gdk.threads_init()

    init_i18n()

    window = CH.AvatarChooser() 
    window.connect("response", response_cb,window)

    # shows the window
    window.show_all()

    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == '__main__':
    sys.exit(main(sys.argv))
