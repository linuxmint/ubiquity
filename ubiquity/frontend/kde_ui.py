# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
# -*- kate: indent-mode python; space-indent true; indent-width 4;
# -*- kate: backspace-indents true;
#
# Copyright (C) 2006, 2007, 2008, 2009 Canonical Ltd.
#
# Author(s):
#   Jonathan Riddell <jriddell@ubuntu.com>
#   Mario Limonciello <superm1@ubuntu.com>
#   Roman Shtylman <shtylman@gmail.com>
#
# This file is part of Ubiquity.
#
# Ubiquity is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or at your option)
# any later version.
#
# Ubiquity is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with Ubiquity; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from __future__ import print_function

import atexit
import dbus
from functools import reduce
import os
import signal
import sys
import syslog
import traceback

# kde gui specifics
import sip
sip.setapi("QVariant", 1)
from PyQt4 import QtCore, QtGui, uic

from ubiquity import filteredcommand, i18n, misc
from ubiquity.components import partman_commit, install, plugininstall
import ubiquity.frontend.base
from ubiquity.frontend.base import BaseFrontend
from ubiquity.frontend.kde_components import ProgressDialog
from ubiquity.frontend.kde_components.Breadcrumb import Breadcrumb
from ubiquity.frontend.kde_components import qssutils
from ubiquity.plugin import Plugin
import ubiquity.progressposition


# Define global path
PATH = '/usr/share/ubiquity'

# Define locale path
LOCALEDIR = "/usr/share/locale"

#currently using for testing, will remove
UIDIR = os.path.join(PATH, 'qt')


class UbiquityUI(QtGui.QMainWindow):
    def __init__(self, parent=None):
        QtGui.QMainWindow.__init__(self, parent)
        #app.ui MainWindow now hardcoded to 1000px wide for main
        #content this will look bad on high res displays and should be
        #defined by dpi not pixels
        uic.loadUi(os.path.join(UIDIR, "app.ui"), self)

        # QProcessManager sets a SIGCHLD handler without SA_RESTART; this
        # can cause ubiquity crashes, because Python's subprocess module
        # (and indeed much of Python in general) is not EINTR-safe.  Force
        # this to be restartable.
        signal.siginterrupt(signal.SIGCHLD, False)

        distro_name = "Kubuntu"
        distro_release = ""

        ## setup the release and codename
        with open("/etc/lsb-release", 'r') as fp:
            for line in fp:
                if "DISTRIB_ID=" in line:
                    name = str.strip(line.split("=")[1], '\n')
                    if name != "Ubuntu":
                        distro_name = name
                elif "DISTRIB_RELEASE=" in line:
                    distro_release = str.strip(line.split("=")[1], '\n')

        self.distro_name_label.setText(distro_name)
        self.distro_release_label.setText(distro_release)

        self.setWindowTitle("%s %s" % (distro_name, distro_release))

    def setWizard(self, wizardRef):
        self.wizard = wizardRef

    def closeEvent(self, event):
        if not self.wizard.on_quit_clicked():
            event.ignore()


class Controller(ubiquity.frontend.base.Controller):
    def translate(self, lang=None, just_me=True, not_me=False, reget=False):
        if lang:
            self._wizard.locale = lang
        self._wizard.translate_pages(lang, just_me, not_me, reget)

    def allow_go_forward(self, allowed):
        self._wizard.allow_go_forward(allowed)

    def allow_go_backward(self, allowed):
        self._wizard.allow_go_backward(allowed)

    def allow_change_step(self, allowed):
        self._wizard.allow_change_step(allowed)

    def allowed_change_step(self):
        return self._wizard.allowed_change_step

    def go_forward(self):
        self._wizard.ui.next.click()

    def go_backward(self):
        self._wizard.ui.back.click()

    def go_to_page(self, widget):
        self._wizard.set_current_page(self._wizard.stackLayout.indexOf(widget))

    def toggle_top_level(self):
        if self._wizard.ui.isVisible():
            self._wizard.ui.hide()
        else:
            self._wizard.ui.show()
        self._wizard.refresh()

    def get_string(self, name, lang=None, prefix=None):
        return self._wizard.get_string(name, lang, prefix)

    def setNextButtonTextInstallNow(self):
        self._wizard.update_next_button(install_now=True)

    def setNextButtonTextNext(self):
        self._wizard.update_next_button(install_now=False)


class Wizard(BaseFrontend):
    def __init__(self, distro):
        BaseFrontend.__init__(self, distro)

        self.previous_excepthook = sys.excepthook
        sys.excepthook = self.excepthook

        # Hardcode the KDE platform plugin to get Oxygen palette. Without this,
        # Ubiquity uses the default Windows-95-like palette when running as a
        # DM.
        os.environ["QT_PLATFORM_PLUGIN"] = "kde"
        # For above settings to apply automatically we need to indicate that we
        # are inside a full KDE session.
        os.environ["KDE_FULL_SESSION"] = "TRUE"

        self.app = QtGui.QApplication([])
        # The "hicolor" icon theme gets picked when Ubiquity is running as a
        # DM. This causes some icons to be missing. Hardcode the theme name to
        # prevent that.
        QtGui.QIcon.setThemeName('oxygen')
        self._apply_stylesheet()

        self.app.setWindowIcon(QtGui.QIcon.fromTheme("ubiquity-kde"))
        import dbus.mainloop.qt
        dbus.mainloop.qt.DBusQtMainLoop(set_as_default=True)

        self.ui = UbiquityUI()

        # initially the steps widget is not visible
        # it becomes visible once the first step becomes active
        self.ui.steps_widget.setVisible(False)
        self.ui.content_widget.setVisible(False)

        if 'UBIQUITY_GREETER' in os.environ:
            self.ui.setWindowFlags(
                QtCore.Qt.Dialog
                | QtCore.Qt.CustomizeWindowHint
                | QtCore.Qt.WindowTitleHint
                )

        self.ui.setWizard(self)

        self.stackLayout = QtGui.QStackedLayout(self.ui.content_widget)

        self.pages = []
        self.pagesindex = 0
        self.pageslen = 0
        for mod in self.modules:
            if hasattr(mod.module, 'PageKde'):
                mod.ui_class = mod.module.PageKde
                mod.controller = Controller(self)
                mod.ui = mod.ui_class(mod.controller)
                widgets = mod.ui.get('plugin_widgets')
                optional_widgets = mod.ui.get('plugin_optional_widgets')
                # Use a placeholder for breadcrumb if none defined
                breadcrumb = mod.ui.get('plugin_breadcrumb') or '------'
                if widgets or optional_widgets:
                    def fill_out(widget_list):
                        rv = []
                        if not isinstance(widget_list, list):
                            widget_list = [widget_list]
                        for w in widget_list:
                            if not w:
                                continue
                            if not isinstance(w, str):
                                # Until we ship with no pre-built pages, insert
                                # at 'beginning'
                                self.stackLayout.insertWidget(self.pageslen, w)
                            elif hasattr(self.ui, w):
                                w = getattr(self.ui, w)
                            rv.append(w)
                        return rv
                    mod.widgets = fill_out(widgets)
                    mod.optional_widgets = fill_out(optional_widgets)

                    mod.breadcrumb_question = breadcrumb
                    mod.breadcrumb = self._create_breadcrumb(breadcrumb)

                    self.pageslen += 1
                    self.pages.append(mod)
        self.user_pageslen = self.pageslen

        self.breadcrumb_install = self._create_breadcrumb('breadcrumb_install')

        # declare attributes
        self.language_questions = (
            'live_installer',
            'quit',
            'back',
            'next',
            'warning_dialog',
            'warning_dialog_label',
            'cancelbutton',
            'exitbutton',
            'install_process_label'
        )

        self.current_page = None
        self.first_seen_page = None
        self.allowed_change_step = True
        self.allowed_go_backward = True
        self.allowed_go_forward = True
        self.stay_on_page = False
        self.mainLoopRunning = False
        self.progress_position = ubiquity.progressposition.ProgressPosition()
        self.progress_cancelled = False
        self.previous_partitioning_page = self.step_index("stepPartAuto")
        self.installing = False
        self.installing_no_return = False
        self.returncode = 0
        self.backup = False
        self.history = []
        self.progressDialog = ProgressDialog.ProgressDialog(0, 0, self.ui)
        self.finished_installing = False
        self.finished_pages = False
        self.parallel_db = None

        self.set_busy_cursor(True)

        # set default language
        self.locale = i18n.reset_locale(self)

        self.socketNotifierRead = {}
        self.socketNotifierWrite = {}
        self.socketNotifierException = {}
        # Array to keep callback functions needed by debconf file descriptors.
        self.debconf_callbacks = {}

        self.allow_go_backward(False)

        self.stop_debconf()
        self.translate_widgets(reget=True)

        if self.custom_title:
            self.ui.setWindowTitle(self.custom_title)
        elif self.oem_config:
            self.ui.setWindowTitle(self.get_string('oem_config_title'))
        elif self.oem_user_config:
            self.ui.setWindowTitle(self.get_string('oem_user_config_title'))
            self.ui.setWindowIcon(QtGui.QIcon.fromTheme("preferences-system"))
            flags = self.ui.windowFlags() ^ QtCore.Qt.WindowMinMaxButtonsHint
            if hasattr(QtCore.Qt, 'WindowCloseButtonHint'):
                flags = flags ^ QtCore.Qt.WindowCloseButtonHint
            self.ui.setWindowFlags(flags)
            self.ui.quit.hide()
            # TODO cjwatson 2010-04-07: provide alternative strings instead
            self.ui.install_process_label.hide()
            self.breadcrumb_install.hide()

        self.update_back_button()
        self.update_next_button(install_now=False)
        self.ui.quit.setIcon(QtGui.QIcon.fromTheme("dialog-close"))
        self.ui.progressCancel.setIcon(QtGui.QIcon.fromTheme("dialog-close"))

        self._show_progress_bar(False)

        misc.add_connection_watch(self.network_change)

    def _show_progress_bar(self, show):
        if show:
            widget = self.ui.progress_widget
        else:
            widget = self.ui.progress_placeholder
        self.ui.progress_stack.setCurrentWidget(widget)

    def _create_breadcrumb(self, name):
        widget = Breadcrumb()
        widget.setObjectName(name)
        layout = self.ui.steps_widget.layout()
        # "- 1" to insert before the bottom spacer
        layout.insertWidget(layout.count() - 1, widget)
        return widget

    def _apply_stylesheet(self):
        qss = qssutils.load("style.qss",
                            ltr=QtGui.QApplication.isLeftToRight())
        self.app.setStyleSheet(qss)

    def excepthook(self, exctype, excvalue, exctb):
        """Crash handler."""

        if (issubclass(exctype, KeyboardInterrupt) or
                issubclass(exctype, SystemExit)):
            return

        tbtext = ''.join(traceback.format_exception(exctype, excvalue, exctb))
        syslog.syslog(syslog.LOG_ERR,
                      "Exception in KDE frontend (invoking crash handler):")
        for line in tbtext.split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
        print("Exception in KDE frontend (invoking crash handler):",
              file=sys.stderr)
        print(tbtext, file=sys.stderr)

        self.post_mortem(exctype, excvalue, exctb)

        if os.path.exists('/usr/share/apport/apport-qt'):
            self.previous_excepthook(exctype, excvalue, exctb)
        else:
            dialog = QtGui.QDialog(self.ui)
            uic.loadUi("%s/crashdialog.ui" % UIDIR, dialog)
            dialog.crash_detail.setText(tbtext)
            dialog.exec_()
            sys.exit(1)

    def network_change(self, online=False):
        from PyQt4.QtCore import QTimer, SIGNAL
        if not online:
            self.set_online_state(False)
            return
        QTimer.singleShot(300, self.check_returncode)
        self.timer = QTimer(self.ui)
        self.timer.connect(
            self.timer, SIGNAL("timeout()"), self.check_returncode)
        self.timer.start(300)

    def check_returncode(self, *args):
        from PyQt4.QtCore import SIGNAL
        if not BaseFrontend.check_returncode(self, args):
            self.timer.disconnect(
                self.timer, SIGNAL("timeout()"), self.check_returncode)

    def set_online_state(self, state):
        for p in self.pages:
            if hasattr(p.ui, 'plugin_set_online_state'):
                p.ui.plugin_set_online_state(state)

    # Disable the KDE media notifier to avoid problems during partitioning.
    def disable_volume_manager(self):
        # FIXME, medianotifier unload port to KDE 4"
        # misc.execute('dcop', 'kded', 'kded', 'unloadModule', 'medianotifier')
        atexit.register(self.enable_volume_manager)

    def enable_volume_manager(self):
        # FIXME, medianotifier unload port to KDE 4"
        # misc.execute('dcop', 'kded', 'kded', 'loadModule', 'medianotifier')
        pass

    def run(self):
        """run the interface."""

        if os.getuid() != 0:
            title = ('This installer must be run with administrative '
                     'privileges, and cannot continue without them.')
            QtGui.QMessageBox.critical(self.ui, "Must be root", title)
            sys.exit(1)

        self.disable_volume_manager()

        self.allow_change_step(True)

        # Declare SignalHandler
        self.ui.next.clicked.connect(self.on_next_clicked)
        self.ui.back.clicked.connect(self.on_back_clicked)
        self.ui.quit.clicked.connect(self.on_quit_clicked)
        self.ui.progressCancel.clicked.connect(
            self.on_progress_cancel_button_clicked)

        if 'UBIQUITY_AUTOMATIC' in os.environ:
            self.debconf_progress_start(
                0, self.pageslen, self.get_string('ubiquity/install/checking'))
            self.progressDialog.setWindowTitle(
                self.get_string('ubiquity/install/title'))
            self.refresh()

        # Start the interface
        self.set_current_page(0)

        if not 'UBIQUITY_AUTOMATIC' in os.environ:
            # Only show now so that the window does not show empty, then resize
            # itself and show content
            self.ui.show()

        if 'UBIQUITY_TEST_SLIDESHOW' in os.environ:
            # Quick way to test slideshow without going through the whole
            # install
            self._update_breadcrumbs('__install')
            self.start_slideshow()
            self.run_main_loop()

        while(self.pagesindex < self.pageslen):
            if self.current_page is None:
                break

            page = self.pages[self.pagesindex]
            skip = False
            if hasattr(page.ui, 'plugin_skip_page'):
                if page.ui.plugin_skip_page():
                    skip = True
            automatic = False
            if hasattr(page.ui, 'is_automatic'):
                automatic = page.ui.is_automatic

            if not skip and not page.filter_class:
                # This page is just a UI page
                self.dbfilter = None
                self.dbfilter_status = None
                if self.set_page(page.module.NAME):
                    self.allow_change_step(True)
                    self.app.exec_()
            elif not skip:
                old_dbfilter = self.dbfilter
                if issubclass(page.filter_class, Plugin):
                    ui = page.ui
                else:
                    ui = None
                self.start_debconf()
                self.dbfilter = page.filter_class(self, ui=ui)

                # Non-debconf steps are no longer possible as the interface
                # is now driven by whether there is a question to ask.
                if self.dbfilter is not None and self.dbfilter != old_dbfilter:
                    self.allow_change_step(False)
                    QtCore.QTimer.singleShot(
                        0, lambda: self.dbfilter.start(auto_process=True))

                page.controller.dbfilter = self.dbfilter
                self.app.exec_()
                page.controller.dbfilter = None

            if self.backup or self.dbfilter_handle_status():
                if self.current_page is not None and not self.backup:
                    self.process_step()
                    if not self.stay_on_page:
                        self.pagesindex = self.pagesindex + 1
                    if automatic:
                        # if no debconf_progress, create another one, set
                        # start to pageindex
                        self.debconf_progress_step(1)
                        self.refresh()
                if self.backup:
                    self.pagesindex = self.pop_history()

            self.app.processEvents()

        if self.current_page is not None:
            self._update_breadcrumbs('__install')
            self.start_slideshow()
            self.run_main_loop()

            quitText = '<qt>%s</qt>' % self.get_string("finished_label")
            rebootButtonText = self.get_string("reboot_button")
            shutdownButtonText = self.get_string("shutdown_button")
            quitButtonText = self.get_string("quit_button")
            titleText = self.get_string("finished_dialog")

            self.ui.hide()
            self.run_success_cmd()
            if self.oem_user_config:
                self.quit()
            elif not (self.get_reboot_seen() or self.get_shutdown_seen()):
                if ('UBIQUITY_ONLY' in os.environ or
                        'UBIQUITY_GREETER' in os.environ):
                    quitText = self.get_string(
                        'ubiquity/finished_restart_only')
                quitText = quitText.replace(
                    '${RELEASE}', misc.get_release().name)
                messageBox = QtGui.QMessageBox(
                    QtGui.QMessageBox.Question, titleText,
                    quitText, QtGui.QMessageBox.NoButton, self.ui)
                messageBox.addButton(
                    rebootButtonText, QtGui.QMessageBox.AcceptRole)
                if self.show_shutdown_button:
                    messageBox.addButton(shutdownButtonText,
                                         QtGui.QMessageBox.AcceptRole)
                if ('UBIQUITY_ONLY' not in os.environ and
                        'UBIQUITY_GREETER' not in os.environ):
                    messageBox.addButton(
                        quitButtonText, QtGui.QMessageBox.RejectRole)
                messageBox.setWindowFlags(messageBox.windowFlags() |
                                          QtCore.Qt.WindowStaysOnTopHint)
                quitAnswer = messageBox.exec_()

                if quitAnswer == 0:
                    self.reboot()
            elif self.get_reboot():
                self.reboot()
            elif self.get_shutdown():
                self.shutdown()

        return self.returncode

    def _update_breadcrumbs(self, active_page_name):
        done = True
        for page in self.pages:
            if not page.breadcrumb:
                continue
            if page.module.NAME == active_page_name:
                page.breadcrumb.setState(Breadcrumb.CURRENT)
                done = False
            else:
                if done:
                    page.breadcrumb.setState(Breadcrumb.DONE)
                else:
                    page.breadcrumb.setState(Breadcrumb.TODO)

        if active_page_name == '__install':
            self.breadcrumb_install.setState(Breadcrumb.CURRENT)
        else:
            self.breadcrumb_install.setState(Breadcrumb.TODO)

    def _create_webview(self):
        # HACK! For some reason, if the QWebView is created from the .ui file,
        # the slideshow does not start (but it starts if one runs
        # UBIQUITY_TEST_SLIDESHOW=1 ubiquity !). Creating it from the code
        # works. I have no idea why.
        from PyQt4.QtWebKit import QWebView
        from PyQt4.QtWebKit import QWebPage

        webView = QWebView()
        webView.setMinimumSize(700, 420)
        webView.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

# Make it transparent, see
# http://ariya.blogspot.com/2009/04/transparent-qwebview-and-qwebpage.html

        palette = webView.palette()
        palette.setBrush(QtGui.QPalette.Base, QtCore.Qt.transparent)
        page = webView.page()
        page.setPalette(palette)
        webView.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, False)

        page.setLinkDelegationPolicy(QWebPage.DelegateExternalLinks)
        page.mainFrame().setScrollBarPolicy(
            QtCore.Qt.Horizontal, QtCore.Qt.ScrollBarAlwaysOff)
        page.mainFrame().setScrollBarPolicy(
            QtCore.Qt.Vertical, QtCore.Qt.ScrollBarAlwaysOff)
        return webView

    def start_slideshow(self):
        slideshow_dir = '/usr/share/ubiquity-slideshow'
        slideshow_locale = self.slideshow_get_available_locale(slideshow_dir,
                                                               self.locale)
        slideshow_main = os.path.join(slideshow_dir, 'slides', 'index.html')
        if not os.path.exists(slideshow_main) or self.hide_slideshow:
            placeHolder = QtGui.QWidget()
            self.stackLayout.addWidget(placeHolder)
            self.stackLayout.setCurrentWidget(placeHolder)
            return

        parameters = []
        parameters.append('locale=%s' % slideshow_locale)
        ltr = i18n.get_string(
            'default-ltr', slideshow_locale, 'ubiquity/imported')
        if ltr == 'default:RTL':
            parameters.append('rtl')
        parameters_encoded = '&'.join(parameters)

        slides = 'file://%s#%s' % (slideshow_main, parameters_encoded)

        def openLink(qUrl):
            QtGui.QDesktopServices.openUrl(qUrl)

        webView = self._create_webview()
        webView.linkClicked.connect(openLink)
        webView.load(QtCore.QUrl(slides))

        self.ui.navigation.hide()
        self.stackLayout.addWidget(webView)
        self.stackLayout.setCurrentWidget(webView)

    def set_layout_direction(self, lang=None):
        if not lang:
            lang = self.locale
        if lang in ("ug",):
            # Special case for languages for which Qt does not know the script
            # direction
            direction = QtCore.Qt.RightToLeft
        else:
            locale = QtCore.QLocale(lang)
            direction = locale.textDirection()

        if direction == self.app.layoutDirection():
            return
        self.app.setLayoutDirection(direction)
        self._apply_stylesheet()
        self.update_back_button()
        self.update_next_button()

    def all_children(self, parentWidget=None):
        if parentWidget is None:
            parentWidget = self.ui

        def recurse(x, y):
            return x + self.all_children(y)
        rv = reduce(recurse, parentWidget.children(), [parentWidget])
        return rv

    def translate_pages(self, lang=None, just_current=True, not_current=False,
                        reget=False):
        current_page = self.pages[self.pagesindex]
        if just_current:
            pages = [self.pages[self.pagesindex]]
        else:
            pages = self.pages
        widgets = []
        for p in pages:
            # There's no sense retranslating the page we're leaving.
            if not_current and p == current_page:
                continue
            prefix = p.ui.get('plugin_prefix')
            for w in p.widgets:
                for c in self.all_children(w):
                    widgets.append((c, prefix))

        #if not just_current:
        #for toplevel in self.toplevels:
            #if toplevel.name != 'live_installer':
                #for c in self.all_children(toplevel):
                    #widgets.append((c, None))
        self.translate_widgets(lang=lang, widgets=widgets, reget=reget)
        # Allow plugins to provide a hook for translation.
        for p in pages:
            # There's no sense retranslating the page we're leaving.
            if not_current and p == current_page:
                continue
            if hasattr(p.ui, 'plugin_translate'):
                try:
                    p.ui.plugin_translate(lang or self.locale)
                except Exception as e:
                    print('Could not translate page (%s): %s' %
                          (p.module.NAME, str(e)), file=sys.stderr)

    # translates widget text based on the object names
    # widgets is a list of (widget, prefix) pairs
    def translate_widgets(self, lang=None, widgets=None, reget=True):
        if lang is None:
            lang = self.locale
        if lang is None:
            languages = []
        else:
            languages = [lang]
        if widgets is None:
            widgets = [(x, None) for x in self.all_children()]

        if reget:
            core_names = [
                'ubiquity/text/%s' % q for q in self.language_questions]
            core_names.append('ubiquity/text/oem_config_title')
            core_names.append('ubiquity/text/oem_user_config_title')
            core_names.append('ubiquity/text/breadcrumb_install')
            core_names.append('ubiquity/text/release_notes_only')
            core_names.append('ubiquity/text/update_installer_only')
            core_names.append('ubiquity/text/USB')
            core_names.append('ubiquity/text/CD')
            for stock_item in ('cancel', 'close', 'go-back', 'go-forward',
                               'ok', 'quit', 'yes', 'no'):
                core_names.append('ubiquity/imported/%s' % stock_item)
            prefixes = []
            for p in self.pages:
                prefix = p.ui.get('plugin_prefix')
                if not prefix:
                    prefix = 'ubiquity/text'
                if p.ui.get('plugin_is_language'):
                    children = reduce(
                        lambda x, y: x + self.all_children(y), p.widgets, [])
                    core_names.extend(
                        [prefix + '/' + c.objectName() for c in children])
                if p.breadcrumb_question:
                    core_names.append(p.breadcrumb_question)
                prefixes.append(prefix)
            i18n.get_translations(
                languages=languages, core_names=core_names,
                extra_prefixes=prefixes)

        # We always translate always-visible widgets
        for q in self.language_questions:
            if hasattr(self.ui, q):
                widgets.append((getattr(self.ui, q), None))
            elif q == 'live_installer':
                widgets.append((self.ui, None))
        widgets.extend(
            [(x, None) for x in self.all_children(self.ui.steps_widget)])

        for w in widgets:
            self.translate_widget(w[0], lang=lang, prefix=w[1])

        self.set_layout_direction()

    def translate_widget_children(self, parentWidget):
        for w in self.all_children(parentWidget):
            self.translate_widget(w)

    def translate_widget(self, widget, lang=None, prefix=None):
        if lang is None:
            lang = self.locale
        #FIXME needs translations for Next, Back and Cancel
        if not isinstance(widget, QtGui.QWidget):
            return

        name = str(widget.objectName())

        text = self.get_string(name, lang, prefix)

        if str(name) == "UbiquityUIBase":
            text = self.get_string("live_installer", lang, prefix)

        if text is None:
            return

        if isinstance(widget, (QtGui.QLabel, Breadcrumb)):
            if name == 'select_language_label' and self.oem_user_config:
                text = self.get_string(
                    'select_language_oem_user_label', lang, prefix)

            if 'heading_label' in name:
                widget.setText("<h2>" + text + "</h2>")
            # TODO remove small from ubiquity.template and disable replace here
            elif 'extra_label' in name:
                text = text.replace("&lt;small&gt;", "")
                text = text.replace("&lt;/small&gt;", "")
                widget.setText("<small>" + text + "</small>")
                print("TEXT " + widget.text())
            elif ('group_label' in name or 'warning_label' in name or
                  name in ('drives_label', 'partition_method_label')):
                widget.setText("<strong>" + text + "</strong>")
            else:
                widget.setText(text)

        elif isinstance(widget, QtGui.QAbstractButton):
            widget.setText(text.replace('_', '&', 1))

        elif (isinstance(widget, QtGui.QWidget) and
              str(name) == "UbiquityUIBase"):
            if self.custom_title:
                text = self.custom_title
            elif self.oem_config:
                text = self.get_string('oem_config_title', lang, prefix)
            elif self.oem_user_config:
                text = self.get_string('oem_user_config_title', lang, prefix)
            widget.setWindowTitle(text)

        else:
            print("WARNING: unknown widget: " + name)
            print("Type: ", type(widget))

    def set_busy_cursor(self, busy):
        if busy:
            cursor = QtGui.QCursor(QtCore.Qt.WaitCursor)
        else:
            cursor = QtGui.QCursor(QtCore.Qt.ArrowCursor)
        self.ui.setCursor(cursor)
        self.busy_cursor = busy

    def allow_change_step(self, allowed):
        self.set_busy_cursor(not allowed)
        self.ui.back.setEnabled(allowed and self.allowed_go_backward)
        self.ui.next.setEnabled(allowed and self.allowed_go_forward)
        self.allowed_change_step = allowed

    def allow_go_backward(self, allowed):
        self.ui.back.setEnabled(allowed and self.allowed_change_step)
        self.allowed_go_backward = allowed

    def allow_go_forward(self, allowed):
        self.ui.next.setEnabled(allowed and self.allowed_change_step)
        self.allowed_go_forward = allowed

    def dbfilter_handle_status(self):
        """If a dbfilter crashed, ask the user if they want to continue anyway.

        Returns True to continue, or False to try again."""

        if not self.dbfilter_status or self.current_page is None:
            return True

        syslog.syslog('dbfilter_handle_status: %s' % str(self.dbfilter_status))

        # TODO cjwatson 2007-04-04: i18n
        text = ('%s failed with exit code %s. Further information may be '
                'found in /var/log/syslog. Do you want to try running this '
                'step again before continuing? If you do not, your '
                'installation may fail entirely or may be broken.' %
                (self.dbfilter_status[0], self.dbfilter_status[1]))
        # FIXME QMessageBox seems to have lost the ability to set custom
        # labels so for now we have to get by with these not-entirely
        # meaningful stock labels
        answer = QtGui.QMessageBox.warning(
            self.ui, '%s crashed' % self.dbfilter_status[0], text,
            QtGui.QMessageBox.Retry,
            QtGui.QMessageBox.Ignore,
            QtGui.QMessageBox.Close)
        self.dbfilter_status = None
        syslog.syslog('dbfilter_handle_status: answer %d' % answer)
        if answer == QtGui.QMessageBox.Ignore:
            return True
        elif answer == QtGui.QMessageBox.Close:
            self.quit()
        else:
            step = self.step_name(self.get_current_page())
            if str(step) == "partman":
                self.set_current_page(self.step_index("stepPartAuto"))
            return False

    def step_name(self, step_index):
        if step_index < 0:
            step_index = 0
        return str(self.stackLayout.widget(step_index).objectName())

    def step_index(self, step_name):
        if hasattr(self.ui, step_name):
            step = getattr(self.ui, step_name)
            return self.stackLayout.indexOf(step)
        else:
            return 0

    def update_back_button(self):
        if QtGui.QApplication.isRightToLeft():
            icon = "go-next"
        else:
            icon = "go-previous"
        self.ui.back.setIcon(QtGui.QIcon.fromTheme(icon))

    def update_next_button(self, install_now=None):
        if install_now is None:
            install_now = self.ui.next.icon().name() == "dialog-ok-apply"

        if install_now:
            text = self.get_string('install_button')
            icon = "dialog-ok-apply"
        else:
            text = self.get_string('next')
            if QtGui.QApplication.isRightToLeft():
                icon = "go-previous"
            else:
                icon = "go-next"
        text = text.replace('_', '&', 1)

        self.ui.next.setIcon(QtGui.QIcon.fromTheme(icon))
        self.ui.next.setText(text)

    def set_page(self, n):
        self.run_automation_error_cmd()
        # We only stop the backup process when we're on a page where questions
        # need to be asked, otherwise you wont be able to back up past
        # pages that do not stop on questions or are preseeded away.
        self.backup = False
        self.ui.show()

        #set all the steps active
        #each step will set its previous ones as inactive
        #this handles the ability to go back

        is_install = False
        for page in self.pages:
            if page.module.NAME == n:
                # Now ask ui class which page we want to be showing right now
                if hasattr(page.ui, 'plugin_get_current_page'):
                    cur = page.ui.call('plugin_get_current_page')
                    if isinstance(cur, str) and hasattr(self.ui, cur):
                        cur = getattr(self.ui, cur)  # for not-yet-plugins
                elif page.widgets:
                    cur = page.widgets[0]
                if not cur:
                    return False
                index = self.stackLayout.indexOf(cur)
                self.add_history(page, cur)
                self.set_current_page(index)
                is_install = hasattr(page.ui, 'plugin_is_install') \
                    and page.ui.plugin_is_install
        self._update_breadcrumbs(n)

        self.update_next_button(install_now=is_install)

        if self.pagesindex == 0:
            self.allow_go_backward(False)
        elif self.pages[self.pagesindex - 1].module.NAME == 'partman':
            # We're past partitioning.  Unless the install fails, there is no
            # going back.
            self.allow_go_backward(False)
            self.ui.quit.hide()
        else:
            self.allow_go_backward(True)

        return True

    def page_name(self, step_index):
        if step_index < 0:
            step_index = 0
        return str(self.stackLayout.widget(step_index).objectName())

    def set_current_page(self, current):
        widget = self.stackLayout.widget(current)
        if self.stackLayout.currentWidget() == widget:
            # self.ui.widgetStack.raiseWidget() will do nothing.
            # Update state ourselves.
            self.on_steps_switch_page(current)
        else:
            self.stackLayout.setCurrentWidget(widget)
            self.on_steps_switch_page(current)

    def reboot(self, *args):
        """Reboot the system after installing."""
        self.returncode = 10
        self.quit()

    def shutdown(self, *args):
        """Shutdown the system after installing."""
        self.returncode = 11
        self.quit()

    def do_reboot(self):
        """Callback for main program to actually reboot the machine."""
        try:
            session = dbus.Bus.get_session()
            ksmserver = session.name_has_owner('org.kde.ksmserver')
        except dbus.exceptions.DBusException:
            ksmserver = False
        if ksmserver:
            ksmserver = session.get_object('org.kde.ksmserver', '/KSMServer')
            ksmserver = dbus.Interface(ksmserver, 'org.kde.KSMServerInterface')
            # ShutdownConfirmNo, ShutdownTypeReboot, ShutdownModeForceNow
            ksmserver.logout(0, 1, 2)
        else:
            misc.execute_root('reboot')

    def do_shutdown(self):
        """Callback for main program to actually shutdown the machine."""
        try:
            session = dbus.Bus.get_session()
            ksmserver = session.name_has_owner('org.kde.ksmserver')
        except dbus.exceptions.DBusException:
            ksmserver = False
        if ksmserver:
            ksmserver = session.get_object('org.kde.ksmserver', '/KSMServer')
            ksmserver = dbus.Interface(ksmserver, 'org.kde.KSMServerInterface')
            # ShutdownConfirmNo, ShutdownTypeReboot, ShutdownModeForceNow
            ksmserver.logout(0, 2, 2)
        else:
            misc.execute_root('poweroff')

    def quit(self):
        """Quit installer cleanly."""
        self.current_page = None
        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()

        self.app.exit()

    def quit_installer(self):
        """Quit installer cleanly."""
        # exiting from application
        self.current_page = None
        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
        self.quit_main_loop()

    def on_quit_clicked(self):
        warning_dialog_label = self.get_string("warning_dialog_label")
        abortTitle = self.get_string("warning_dialog")
        yes = self.get_string('yes', prefix='ubiquity/imported')
        no = self.get_string('no', prefix='ubiquity/imported')
        messageBox = QtGui.QMessageBox()
        messageBox.setWindowTitle(abortTitle)
        messageBox.setText(warning_dialog_label)
        messageBox.setStandardButtons(
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        messageBox.setDefaultButton(QtGui.QMessageBox.Yes)
        messageBox.button(QtGui.QMessageBox.Yes).setText(
            yes.replace('_', '&', 1))
        messageBox.button(QtGui.QMessageBox.No).setText(
            no.replace('_', '&', 1))
        response = messageBox.exec_()
        if response == QtGui.QMessageBox.Yes:
            self.current_page = None
            self.quit()
            return True
        else:
            return False

    def on_next_clicked(self):
        """Callback to control the installation process between steps."""
        if not self.allowed_change_step or not self.allowed_go_forward:
            return

        self.allow_change_step(False)

        if self.dbfilter is not None:
            self.dbfilter.ok_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits
        else:
            self.app.exit()

    def process_step(self):
        """Process and validate the results of this step."""

        # setting actual step
        step_num = self.get_current_page()
        step = self.page_name(step_num)
        syslog.syslog('Step_before = %s' % step)

        if step.startswith("stepPart"):
            self.previous_partitioning_page = step_num

        # Automatic partitioning
        if step == "stepPartAuto":
            self.process_autopartitioning()

    def process_autopartitioning(self):
        """Processing automatic partitioning step tasks."""
        self.app.processEvents()

        # For safety, if we somehow ended up improperly initialised
        # then go to manual partitioning.
        choice = self.get_autopartition_choice()[0]
        if self.manual_choice is None or choice == self.manual_choice:
            self.set_current_page(self.step_index("stepPartAdvanced"))
        else:
            self.set_current_page(self.step_index("stepUserInfo"))

    def on_back_clicked(self):
        """Callback to set previous screen."""
        if not self.allowed_change_step:
            return

        self.allow_change_step(False)

        self.backup = True
        self.stay_on_page = False

        # Enabling next button
        self.allow_go_forward(True)
        self.set_busy_cursor(True)

        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits
        else:
            self.app.exit()

    def on_steps_switch_page(self, newPageID):
        self.ui.content_widget.show()
        self.current_page = newPageID
        name = self.step_name(newPageID)
        syslog.syslog('switched to page %s' % name)
        if 'UBIQUITY_GREETER' in os.environ:
            if name == 'language':
                self.ui.steps_widget.hide()
                self.ui.navigation.hide()
            else:
                self.ui.steps_widget.show()
                self.ui.navigation.show()
        else:
            self.ui.steps_widget.show()
            self.ui.navigation.show()

    def watch_debconf_fd(self, from_debconf, process_input):
        if from_debconf in self.debconf_callbacks:
            self.watch_debconf_fd_helper_disconnect(from_debconf)
        self.socketNotifierRead[from_debconf] = QtCore.QSocketNotifier(
            from_debconf, QtCore.QSocketNotifier.Read, self.app)
        self.socketNotifierRead[from_debconf].activated[int].connect(
            self.watch_debconf_fd_helper_read)

        self.socketNotifierWrite[from_debconf] = QtCore.QSocketNotifier(
            from_debconf, QtCore.QSocketNotifier.Write, self.app)
        self.socketNotifierWrite[from_debconf].activated[int].connect(
            self.watch_debconf_fd_helper_write)

        self.socketNotifierException[from_debconf] = QtCore.QSocketNotifier(
            from_debconf, QtCore.QSocketNotifier.Exception, self.app)
        self.socketNotifierException[from_debconf].activated[int].connect(
            self.watch_debconf_fd_helper_exception)

        self.debconf_callbacks[from_debconf] = process_input

    def watch_debconf_fd_helper_disconnect(self, source):
        del self.debconf_callbacks[source]
        self.socketNotifierRead[source].activated[int].disconnect(
            self.watch_debconf_fd_helper_read)
        self.socketNotifierWrite[source].activated[int].disconnect(
            self.watch_debconf_fd_helper_write)
        self.socketNotifierException[source].activated[int].disconnect(
            self.watch_debconf_fd_helper_exception)
        del self.socketNotifierRead[source]
        del self.socketNotifierWrite[source]
        del self.socketNotifierException[source]

    def watch_debconf_fd_helper_read(self, source):
        debconf_condition = 0
        debconf_condition |= filteredcommand.DEBCONF_IO_IN
        callback = self.debconf_callbacks[source]
        if not callback(source, debconf_condition):
            # The parallel dbfilter code in debconffilter_done could re-open
            # this fd before we reach this point.
            if callback == self.debconf_callbacks[source]:
                self.watch_debconf_fd_helper_disconnect(source)

    def watch_debconf_fd_helper_write(self, source):
        debconf_condition = 0
        debconf_condition |= filteredcommand.DEBCONF_IO_OUT
        callback = self.debconf_callbacks[source]
        if not callback(source, debconf_condition):
            if callback == self.debconf_callbacks[source]:
                self.watch_debconf_fd_helper_disconnect(source)

    def watch_debconf_fd_helper_exception(self, source):
        debconf_condition = 0
        debconf_condition |= filteredcommand.DEBCONF_IO_ERR
        callback = self.debconf_callbacks[source]
        if not callback(source, debconf_condition):
            if callback == self.debconf_callbacks[source]:
                self.watch_debconf_fd_helper_disconnect(source)

    def debconf_progress_start(self, progress_min, progress_max,
                               progress_title):
        self.progress_position.start(progress_min, progress_max,
                                     progress_title)
        self.debconf_progress_set(0)
        self.debconf_progress_info(progress_title)
        total_steps = progress_max - progress_min
        self.ui.progressBar.setMaximum(total_steps)
        self.ui.progressBar.setFormat(progress_title + " %p%")

    def debconf_progress_set(self, progress_val):
        self.progress_cancelled = self.progressDialog.wasCanceled()
        if self.progress_cancelled:
            return False
        self.progress_position.set(progress_val)
        fraction = self.progress_position.fraction()

        self.ui.progressBar.setValue(
            int(fraction * self.ui.progressBar.maximum()))

        return True

    def debconf_progress_step(self, progress_inc):
        self.progress_cancelled = self.progressDialog.wasCanceled()
        if self.progress_cancelled:
            return False
        self.progress_position.step(progress_inc)
        fraction = self.progress_position.fraction()

        self.ui.progressBar.setValue(
            int(fraction * self.ui.progressBar.maximum()))

        return True

    def debconf_progress_info(self, progress_info):
        self.progress_cancelled = self.progressDialog.wasCanceled()
        if self.progress_cancelled:
            return False

        self.ui.progressBar.setFormat(progress_info + " %p%")

        return True

    def debconf_progress_stop(self):
        self.progress_cancelled = False
        self.progress_position.stop()

    def debconf_progress_region(self, region_start, region_end):
        self.progress_position.set_region(region_start, region_end)

    def debconf_progress_cancellable(self, cancellable):
        if cancellable:
            self.progressDialog.setCancellable(True)
            self.ui.progressCancel.show()
        else:
            self.ui.progressCancel.hide()
            self.progressDialog.setCancellable(False)
            self.progress_cancelled = False

    def on_progress_cancel_button_clicked(self, button):
        self.progress_cancelled = True

    def debconffilter_done(self, dbfilter):
        # processing events here prevents GUI from hanging until mouse moves
        # (LP #556376)
        self.app.processEvents()
        if not dbfilter.status:
            self.find_next_step(dbfilter.__module__)
        elif dbfilter.__module__ in ('ubiquity.components.install',
                                     'ubiquity.components.plugininstall'):
            # We don't want to try to retry a failing step here, because it
            # will have the same set of inputs, and thus likely the same
            # result.
            # TODO: We may want to call return_to_partitioning after the crash
            # dialog instead.
            dialog = QtGui.QDialog(self.ui)
            uic.loadUi("%s/crashdialog.ui" % UIDIR, dialog)
            dialog.exec_()
            sys.exit(1)
        if BaseFrontend.debconffilter_done(self, dbfilter):
            self.app.exit()
            return True
        else:
            return False

    def find_next_step(self, finished_step):
        # TODO need to handle the case where debconffilters launched from
        # here crash.  Factor code out of dbfilter_handle_status.
        last_page = self.pages[-1].module.__name__
        if finished_step == last_page and not self.backup:
            self.finished_pages = True
            if self.finished_installing or self.oem_user_config:
                self.debconf_progress_info('')
                self._show_progress_bar(True)
                dbfilter = plugininstall.Install(self)
                dbfilter.start(auto_process=True)

        elif finished_step == 'ubi-partman':
            # Flush changes to the database so that when the parallel db
            # starts, it does so with the most recent changes.
            self.stop_debconf()
            self.start_debconf()
            self._show_progress_bar(True)
            self.installing = True
            from ubiquity.debconfcommunicator import DebconfCommunicator
            if self.parallel_db is not None:
                # Partitioning failed and we're coming back through again.
                self.parallel_db.shutdown()
            env = os.environ.copy()
            # debconf-apt-progress, start_debconf()
            env['DEBCONF_DB_REPLACE'] = 'configdb'
            env['DEBCONF_DB_OVERRIDE'] = 'Pipe{infd:none outfd:none}'
            self.parallel_db = DebconfCommunicator('ubiquity', cloexec=True,
                                                   env=env)
            dbfilter = partman_commit.PartmanCommit(self, db=self.parallel_db)
            dbfilter.start(auto_process=True)

        # FIXME OH DEAR LORD.  Use isinstance.
        elif finished_step == 'ubiquity.components.partman_commit':
            dbfilter = install.Install(self, db=self.parallel_db)
            dbfilter.start(auto_process=True)

        elif finished_step == 'ubiquity.components.install':
            self.finished_installing = True
            if self.finished_pages:
                dbfilter = plugininstall.Install(self)
                dbfilter.start(auto_process=True)
            else:
                self._show_progress_bar(False)

        elif finished_step == 'ubiquity.components.plugininstall':
            self.installing = False
            self.quit_main_loop()

    def installation_medium_mounted(self, message):
        self.ui.part_advanced_warning_message.setText(message)
        self.ui.part_advanced_warning_hbox.show()

    def return_to_partitioning(self):
        """If the install progress bar is up but still at the partitioning
        stage, then errors can safely return us to partitioning.
        """
        if self.installing and not self.installing_no_return:
            # Stop the currently displayed page.
            if self.dbfilter is not None:
                self.dbfilter.cancel_handler()
            # Go back to the partitioner and try again.
            self.pagesindex = -1
            for page in self.pages:
                if page.module.NAME == 'partman':
                    self.pagesindex = self.pages.index(page)
                    break
            if self.pagesindex == -1:
                return
            self.start_debconf()
            ui = self.pages[self.pagesindex].ui
            self.dbfilter = self.pages[self.pagesindex].filter_class(
                self, ui=ui)
            self.allow_change_step(False)
            self.dbfilter.start(auto_process=True)
            self.ui.next.setText(self.get_string("next").replace('_', '&', 1))
            self.ui.next.setIcon(self.forwardIcon)
            self.translate_widget(self.ui.next)
            self.installing = False
            self._show_progress_bar(False)
            self.ui.quit.show()

    def error_dialog(self, title, msg, fatal=True):
        self.run_automation_error_cmd()
        saved_busy_cursor = self.busy_cursor
        self.set_busy_cursor(False)
        # TODO: cancel button as well if capb backup
        QtGui.QMessageBox.warning(self.ui, title, msg, QtGui.QMessageBox.Ok)
        self.set_busy_cursor(saved_busy_cursor)
        if fatal:
            self.return_to_partitioning()

    def question_dialog(self, title, msg, options, use_templates=True):
        self.run_automation_error_cmd()
        # I doubt we'll ever need more than three buttons.
        assert len(options) <= 3, options

        saved_busy_cursor = self.busy_cursor
        self.set_busy_cursor(False)
        buttons = {}
        messageBox = QtGui.QMessageBox(QtGui.QMessageBox.Question, title, msg,
                                       QtGui.QMessageBox.NoButton, self.ui)
        for option in options:
            if use_templates:
                text = self.get_string(option)
            else:
                text = option
            if text is None:
                text = option
            text = text.replace("_", "&")
            # Convention for options is to have the affirmative action last;
            # KDE convention is to have it first.
            if option == options[-1]:
                button = messageBox.addButton(
                    text, QtGui.QMessageBox.AcceptRole)
            else:
                button = messageBox.addButton(
                    text, QtGui.QMessageBox.RejectRole)
            buttons[button] = option

        response = messageBox.exec_()
        self.set_busy_cursor(saved_busy_cursor)

        if response < 0:
            return None
        else:
            return buttons[messageBox.clickedButton()]

    def refresh(self):
        self.app.processEvents()

    # Run the UI's main loop until it returns control to us.
    def run_main_loop(self):
        self.allow_change_step(True)
        self.mainLoopRunning = True
        while self.mainLoopRunning:  # nasty, but works OK
            self.app.processEvents(QtCore.QEventLoop.WaitForMoreEvents)

    # Return control to the next level up.
    def quit_main_loop(self):
        self.mainLoopRunning = False

    # returns the current wizard page
    def get_current_page(self):
        return self.stackLayout.indexOf(self.stackLayout.currentWidget())
