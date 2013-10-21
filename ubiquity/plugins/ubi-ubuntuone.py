# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

# Copyright (C) 2012-2013 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import http.client
import json
from oauthlib.oauth1 import (Client, SIGNATURE_HMAC,
                             SIGNATURE_TYPE_AUTH_HEADER)
import os
import os.path
import platform
import pwd
import subprocess
import shutil
import syslog
import traceback
from urllib.parse import urlencode

from ubiquity import plugin, misc

PLUGIN_VERSION = "1.0"
UBUNTU_SSO_URL = "https://login.ubuntu.com/api/v2/"
UBUNTU_ONE_URL = "https://one.ubuntu.com/"
UBUNTU_TC_URL = "https://one.ubuntu.com/terms/embedded/"

TOKEN_SEPARATOR = ' @ '
SEPARATOR_REPLACEMENT = ' AT '
U1_APP_NAME = "Ubuntu One"

(ACCOUNT_CALLBACK_ACTION,
 TOKEN_CALLBACK_ACTION,
 PING_CALLBACK_ACTION) = range(3)

NAME = 'ubuntuone'
AFTER = 'usersetup'
WEIGHT = 10

(PAGE_LOGIN,
 PAGE_REGISTER,
 PAGE_SPINNER,
 PAGE_TC,
 PAGE_ABOUT,
 PAGE_OFFLINE,
 ) = range(6)


class Page(plugin.Plugin):

    def prepare(self, unfiltered=False):
        self.ui._user_password = self.db.get('passwd/user-password')
        self.ui.hostname = self.db.get('netcfg/get_hostname')
        return plugin.Plugin.prepare(unfiltered)


def get_ping_info():
    base = os.environ.get("UBUNTU_ONE_URL", UBUNTU_ONE_URL)
    url = base + "oauth/sso-finished-so-get-tokens/{email}"
    params = dict(platform=platform.system(),
                  platform_version=platform.release(),
                  platform_arch=platform.machine(),
                  client_version=PLUGIN_VERSION)
    return (url, params)


def get_token_name(hostname):
    computer_name = hostname.replace(TOKEN_SEPARATOR,
                                     SEPARATOR_REPLACEMENT)
    return TOKEN_SEPARATOR.join((U1_APP_NAME, computer_name))


class PageGtk(plugin.PluginUI):
    plugin_title = 'ubiquity/text/ubuntuone_heading_label'

    def __init__(self, controller, *args, **kwargs):
        from gi.repository import Gtk
        self.controller = controller

        # keep ubuntuone for oem client config
        if self.controller.oem_config:
            misc.execute_root('apt-install', 'ubiquity-plugin-ubuntuone')

        # check if we are needed at all
        if ('UBIQUITY_AUTOMATIC' in os.environ or
                'UBIQUITY_NO_SSO' in os.environ or
                self.controller.oem_config):
            self.page = None
            return
        # check dependencies
        try:
            from gi.repository import GnomeKeyring
            assert(GnomeKeyring)
        except ImportError as e:
            syslog.syslog("skipping SSO page, no GnomeKeyring (%s)" % e)
            self.page = None
            return
        # add builder/signals
        builder = Gtk.Builder()
        self.controller.add_builder(builder)
        builder.add_from_file(
            os.path.join(os.environ['UBIQUITY_GLADE'], 'stepUbuntuOne.ui'))
        builder.connect_signals(self)
        # make the widgets available under their gtkbuilder name
        for obj in builder.get_objects():
            if issubclass(type(obj), Gtk.Buildable):
                setattr(self, Gtk.Buildable.get_name(obj), obj)
        self.page = builder.get_object('stepUbuntuOne')
        self.notebook_main.set_show_tabs(False)
        self.plugin_widgets = self.page
        self.progressUbuntuOne.show_all()
        self.progress_page = False
        self.last_page = False

        self.skip_step = False
        self.online = False

        self._generic_error = "error"

        # TODO 20130529 xnox: need to figure out a proper way for
        # errors - that is when to display/hide them and on which
        # pages and when to "reset"/clear them. Currently it will
        # continue displaying the error for longer than probably is
        # needed.
        self.label_global_error.set_text("")
        self.error_bar.set_message_type(Gtk.MessageType.OTHER)

        self.oauth_token_json = None
        self.ping_successful = False
        self.account_creation_successful = False

        self.hostname = ""

        from gi.repository import Soup
        self.soup = Soup
        self.session = Soup.SessionAsync()
        if "DEBUG_SSO_API" in os.environ:
            self.session.add_feature(Soup.Logger.new(Soup.LoggerLogLevel.BODY,
                                                     -1))
        self.on_notebook_main_switch_page(None, None, None)

    def login_to_sso(self, email, password, token_name, from_page):
        """Queue POST message to /tokens to get oauth token.
        See _handle_soup_message_done() for completion details.
        """
        body = json.dumps({'email': email,
                           'password': password,
                           'token_name': token_name})
        service_url = os.environ.get("UBUNTU_SSO_URL", UBUNTU_SSO_URL)
        tokens_url = service_url + "tokens/oauth"
        message = self.soup.Message.new("POST", tokens_url)
        message.set_request('application/json',
                            self.soup.MemoryUse.COPY,
                            body, len(body))
        message.request_headers.append('Accept', 'application/json')

        self.session.queue_message(message, self._handle_soup_message_done,
                                   dict(action=TOKEN_CALLBACK_ACTION,
                                        from_page=from_page))

    def register_new_sso_account(self, email, password, displayname):
        """Queue POST to /accounts to register new account and get token.
        See _handle_soup_message_done() for completion details.
        """
        params = {'email': email,
                  'password': password,
                  'displayname': displayname}
        body = json.dumps(params)
        service_url = os.environ.get("UBUNTU_SSO_URL", UBUNTU_SSO_URL)
        accounts_url = service_url + "accounts"
        message = self.soup.Message.new("POST", accounts_url)
        message.set_request('application/json',
                            self.soup.MemoryUse.COPY,
                            body, len(body))
        message.request_headers.append('Accept', 'application/json')

        self.session.queue_message(message, self._handle_soup_message_done,
                                   dict(action=ACCOUNT_CALLBACK_ACTION,
                                        from_page=PAGE_REGISTER))

    def _handle_soup_message_done(self, session, message, info):
        """Handle message completion, check for errors."""
        from gi.repository import Gtk
        syslog.syslog("soup message ({}) code: {}".format(info,
                                                          message.status_code))
        content = message.response_body.flatten().get_data().decode("utf-8")

        if message.status_code in [http.client.OK, http.client.CREATED]:
            if info['action'] == TOKEN_CALLBACK_ACTION:
                self.oauth_token_json = content
            elif info['action'] == PING_CALLBACK_ACTION:
                self.ping_successful = True
            elif info['action'] == ACCOUNT_CALLBACK_ACTION:
                self.account_creation_successful = True
        else:
            self.notebook_main.set_current_page(info['from_page'])

            syslog.syslog("Error in soup message: %r" % message.reason_phrase)
            syslog.syslog("Error response headers: %r" %
                          message.get_property("response-headers"))
            syslog.syslog("error response body: %r " %
                          message.response_body.flatten().get_data())

            try:
                response_dict = json.loads(content)
                error_message = response_dict["message"]
            except ValueError:
                error_message = self._generic_error

            self.label_global_error.set_text(error_message)
            self.error_bar.set_message_type(Gtk.MessageType.WARNING)

        Gtk.main_quit()

    def ping_u1_url(self, email, from_page):
        """Sign and GET a URL to enable U1 server access."""
        token = json.loads(self.oauth_token_json)

        oauth_client = Client(token['consumer_key'],
                              token['consumer_secret'],
                              token['token_key'],
                              token['token_secret'],
                              signature_method=SIGNATURE_HMAC,
                              signature_type=SIGNATURE_TYPE_AUTH_HEADER)

        url, params = get_ping_info()
        url = url.format(email=email)
        url += "?" + urlencode(params)
        signed_url, signed_headers, _ = oauth_client.sign(url, "GET")
        message = self.soup.Message.new("GET", signed_url)

        for k, v in signed_headers.items():
            message.request_headers.append(k, v)

        self.session.queue_message(message, self._handle_soup_message_done,
                                   dict(action=PING_CALLBACK_ACTION,
                                        from_page=from_page))

    def plugin_set_online_state(self, state):
        self.online = state

    def plugin_get_current_page(self):
        self.page.show_all()
        PATH = (os.environ.get('UBIQUITY_PATH', False) or
                '/usr/share/ubiquity')
        self.controller._wizard.page_logo.set_from_file(
            os.path.join(PATH, 'pixmaps', 'u1', 'ubuntu_one_logo.svg'))
        self.progressUbuntuOne.show_all()
        self.controller.toggle_skip_button('u1_login_skip')
        self.note = self.controller._wizard.progress_mode
        if not self.progress_page:
            self.progress_page = self.note.append_page(
                self.progressUbuntuOne, None)
        self.note.set_current_page(self.progress_page)
        self.u1_learn_more.connect(
            'activate-link', self.on_u1_learn_more_activate)
        if self.online:
            self.notebook_main.set_current_page(PAGE_LOGIN)
        else:
            self.notebook_main.set_current_page(PAGE_OFFLINE)
        self.on_notebook_main_switch_page(None, None, None)
        self.skip_step = False
        return self.page

    def plugin_on_skip_clicked(self):
        self.oauth_token = None
        self.skip_step = True
        self.controller.allow_go_forward(True)
        self.controller.allow_change_step(True)
        self.controller.go_forward()

    def plugin_on_back_clicked(self):
        from_page = self.notebook_main.get_current_page()
        if from_page == PAGE_REGISTER:
            email = self.entry_email1.get_text()
            self.entry_email.set_text(email)
            self.controller.toggle_skip_button('u1_login_skip')
            self.notebook_main.set_current_page(PAGE_LOGIN)
        elif from_page == PAGE_TC:
            self.controller.toggle_skip_button('u1_register_skip')
            self.notebook_main.set_current_page(PAGE_REGISTER)
        elif from_page == PAGE_ABOUT:
            self.controller._wizard.skip.show()
            self.notebook_main.set_current_page(self.last_page)

        if from_page in (PAGE_REGISTER, PAGE_TC, PAGE_ABOUT):
            self.on_notebook_main_switch_page(None, None, None)
            return True

        self.note.set_current_page(1)
        self.controller._wizard.page_logo.hide()

        return False

    def plugin_on_next_clicked(self):
        if self.skip_step:
            self.note.set_current_page(0)
            self.controller._wizard.page_logo.hide()
            return False

        from gi.repository import Gtk

        from_page = self.notebook_main.get_current_page()
        self.notebook_main.set_current_page(PAGE_SPINNER)
        self.spinner_connect.start()

        if from_page == PAGE_LOGIN:
            email = self.entry_email.get_text()
            if self.u1_new_account.get_active():
                self.entry_email1.set_text(email)
                self.spinner_connect.stop()
                self.controller.toggle_skip_button('u1_register_skip')
                self.notebook_main.set_current_page(PAGE_REGISTER)
                self.on_notebook_main_switch_page(None, None, None)
                return True
            else:
                password = self.u1_password_existing.get_text()

        elif from_page == PAGE_REGISTER:
            # First create new account before getting token:
            email = self.entry_email1.get_text()
            password = self.u1_password.get_text()
            displayname = self.u1_name.get_text()

            try:
                self.register_new_sso_account(email, password, displayname)
            except Exception:
                syslog.syslog("exception in register_new_sso_account: %r" %
                              traceback.format_exc())
                self.on_notebook_main_switch_page(None, None, None)
                return True

            Gtk.main()

            if not self.account_creation_successful:
                syslog.syslog("Error registering SSO account, exiting.")
                self.on_notebook_main_switch_page(None, None, None)
                return True

        else:
            raise AssertionError("'Next' from invalid page: %r" % from_page)

        # Now get the token, regardless of which page we came from
        try:
            self.login_to_sso(email, password,
                              get_token_name(self.hostname),
                              from_page)
        except Exception:
            syslog.syslog("exception in login_to_sso: %r" %
                          traceback.format_exc())
            self.on_notebook_main_switch_page(None, None, None)
            return True

        Gtk.main()

        if self.oauth_token_json is None:
            syslog.syslog("Error getting oauth_token, not creating keyring")
            self.on_notebook_main_switch_page(None, None, None)
            return True

        try:
            self.ping_u1_url(email, from_page)
        except Exception:
            syslog.syslog("exception in ping_u1_url: %r" %
                          traceback.format_exc())

        Gtk.main()

        self.spinner_connect.stop()

        if not self.ping_successful:
            syslog.syslog("Error pinging U1 URL, not creating keyring")
            self.on_notebook_main_switch_page(None, None, None)
            return True

        # all good, create a (encrypted) keyring and store the token for later
        rv = self._create_keyring_and_store_u1_token(self.oauth_token_json)
        if rv != 0:
            syslog.syslog("Error creating keyring, u1 token not saved.")
            self.on_notebook_main_switch_page(None, None, None)
            return True
        self.note.set_current_page(0)
        self.controller._wizard.page_logo.hide()
        return False

    def _duplicate_token_data_for_v1(self, token_dict):
        """Duplicate two keys in the stored token, for compatibility
         with clients expecting V1 API keys. See bug LP: #1136590 to
         check if we can remove this."""
        token_dict['token'] = token_dict['token_key']
        token_dict['name'] = token_dict['token_name']
        return token_dict

    def _create_keyring_and_store_u1_token(self, token_json):
        """Helper that spawns a external helper to create the keyring"""
        # this needs to be a external helper as ubiquity is running as
        # root and it seems that anything other than "drop_all_privileges"
        # will not trigger the correct dbus activation for the
        # gnome-keyring daemon

        token_dict = json.loads(token_json)
        token_dict = self._duplicate_token_data_for_v1(token_dict)
        urlencoded_token = urlencode(token_dict)

        cmd = os.environ.get("U1_KEYRING_HELPER",
                             "/usr/share/ubiquity/ubuntuone-keyring-helper")
        p = subprocess.Popen([cmd], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             preexec_fn=misc.drop_all_privileges)
        params = '%s\n%s\n' % (self._user_password, urlencoded_token)
        p.communicate(input=params.encode('UTF-8'))
        return p.returncode

    def plugin_translate(self, lang):
        pasw = self.controller.get_string('password_inactive_label', lang)
        self.u1_password_existing.set_placeholder_text(pasw)
        pasw_length = self.controller.get_string('password_new_inactive_label')
        self.u1_password.set_placeholder_text(pasw_length)
        pasw_retype = self.controller.get_string(
            'password_new_again_inactive_label')
        self.u1_verified_password.set_placeholder_text(pasw_retype)
        email_p = self.controller.get_string('email_inactive_label', lang)
        self.entry_email.set_placeholder_text(email_p)
        self.entry_email1.set_placeholder_text(email_p)
        name_p = self.controller.get_string('fullname_inactive_label', lang)
        self.u1_name.set_placeholder_text(name_p)
        # error messages
        self._error_register = self.controller.get_string(
            'error_register', lang)
        self._error_login = self.controller.get_string(
            'error_login', lang)
        self._generic_error = self.controller.get_string(
            'generic_error', lang)

    def set_page_title(self, title):
        self.controller._wizard.page_title.set_markup(
            '<span size="xx-large">%s</span>' % title)

    # signals
    def on_u1_learn_more_activate(self, unused_widget, unused):
        self.last_page = self.notebook_main.get_current_page()
        if self.last_page in (PAGE_ABOUT, PAGE_TC):
            return
        self.controller._wizard.skip.hide()
        self.notebook_main.set_current_page(PAGE_ABOUT)
        self.on_notebook_main_switch_page(None, None, None)

    def on_u1_terms_activate_link(self, unused_widget, unused):
        self.notebook_main.set_current_page(PAGE_TC)
        self.controller._wizard.skip.hide()
        self.on_notebook_main_switch_page(None, None, None)
        # TODO xnox 2012-03-07 add URL link handling hook like in slideshow
        from gi.repository import WebKit
        # We have no significant browsing interface, so there isn't much point
        # in WebKit creating a memory-hungry cache.
        WebKit.set_cache_model(WebKit.CacheModel.DOCUMENT_VIEWER)
        self.webview = WebKit.WebView()
        # WebKit puts file URLs in their own domain by default.
        # This means that anything which checks for the same origin,
        # such as creating a XMLHttpRequest, will fail unless this
        # is disabled.
        # http://www.gitorious.org/webkit/webkit/commit/624b946
        if (os.environ.get('UBIQUITY_A11Y_PROFILE') == 'screen-reader'):
            s = self.webview.get_settings()
            s.set_property('enable-caret-browsing', True)
        self.webview.connect(
            'new-window-policy-decision-requested',
            self.controller._wizard.on_slideshow_link_clicked)

        self.webkit_tc_view.add(self.webview)
        self.webview.open(UBUNTU_TC_URL)
        self.webview.show()
        self.webview.grab_focus()

    def on_notebook_main_switch_page(self, notebook, label, tab_number):
        # Recalculate next button
        self.info_loop(None)

    def _verify_email_entry(self, email):
        """Return True if the email address looks valid"""
        return '@' in email

    def _verify_password_entry(self, password):
        """Return True if there is a valid password"""
        return len(password) > 7

    def info_loop(self, widget):
        """Run each time the user inputs something to make controlls
           sensitive or insensitive
        """
        complete = False
        current_page = self.notebook_main.get_current_page()
        if current_page == PAGE_REGISTER:
            email = self.entry_email1.get_text()
            password = self.u1_password.get_text()
            password2 = self.u1_verified_password.get_text()
            complete = (
                self._verify_email_entry(email) and
                self._verify_password_entry(password) and
                (password == password2) and
                len(self.u1_name.get_text()) > 0 and
                self.u1_tc_check.get_active()
            )
        elif current_page == PAGE_LOGIN:
            email = self.entry_email.get_text()
            password = self.u1_password_existing.get_text()
            complete = (
                self.u1_new_account.get_active() or
                (self._verify_email_entry(email) and
                 self._verify_password_entry(password)))
        self.controller.allow_go_forward(complete)
        self.controller.allowed_go_backward = True
        self.controller.allow_change_step(True)
        self.controller.allow_go_backward(True)


class Install(plugin.InstallPlugin):

    def install(self, target, progress, *args, **kwargs):
        self.configure_oauth_token(target)

    def _get_target_uid(self, target_path, target_user):
        # stolen from: plugininstall.py, is there a better way?
        p = subprocess.Popen(
            ['chroot', target_path, 'sudo', '-u', target_user, '--',
             'id', '-u'], stdout=subprocess.PIPE, universal_newlines=True)
        uid = int(p.communicate()[0].strip('\n'))
        return uid

    def _get_casper_user_keyring_file_path(self):
        # stolen (again) from pluginstall.py
        try:
            casper_user = pwd.getpwuid(999).pw_name
        except KeyError:
            # We're on a weird system where the casper user isn't uid 999
            # just stop there
            return ""
        casper_user_home = os.path.expanduser('~%s' % casper_user)
        keyring_file = os.path.join(casper_user_home, ".local", "share",
                                    "keyrings", "login.keyring")
        return keyring_file

    # XXX: I am untested
    def configure_oauth_token(self, target):
        target_user = self.db.get('passwd/username')
        uid = self._get_target_uid(target, target_user)
        keyring_file = self._get_casper_user_keyring_file_path()
        if os.path.exists(keyring_file) and uid:
            encryptpath = os.path.join(target, 'home', target_user,
                                       '.ectryptfs')
            try:
                os.stat(encryptpath)
            except OSError:
                syslog.syslog(
                    "encrypted home directory not supported, skip copy")
                return
            targetpath = os.path.join(
                target, 'home', target_user, '.local', 'share', 'keyrings',
                'login.keyring')
            # skip copy if the target already exists, this can happen
            # if e.g. the user selected reinstall-with-keep-home
            if os.path.exists(targetpath):
                syslog.syslog("keyring path: '%s' already exists, skip copy" %
                              targetpath)
                return
            basedir = os.path.dirname(targetpath)
            # ensure we have the basedir with the righ permissions
            if not os.path.exists(basedir):
                basedir_in_chroot = os.path.join(
                    "home", target_user, ".local", "share", "keyrings")
                subprocess.call(
                    ["chroot", target,  "sudo", "-u", target_user, "--",
                     "mkdir", "-p", basedir_in_chroot])
            shutil.copy2(keyring_file, targetpath)
            os.lchown(targetpath, uid, uid)
            os.chmod(targetpath, 0o600)
            os.chmod(basedir, 0o700)
