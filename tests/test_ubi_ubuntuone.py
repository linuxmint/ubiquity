#!/usr/bin/python3

import http.client
import json
import oauthlib
import unittest

from mock import call, DEFAULT, Mock, patch, PropertyMock, sentinel
from gi.repository import Gtk

from ubiquity import plugin_manager


ubi_ubuntuone = plugin_manager.load_plugin('ubi-ubuntuone')


class TokenNameTestCase(unittest.TestCase):

    def test_simple_token_name(self):
        name = ubi_ubuntuone.get_token_name('simple')
        self.assertEqual(name, "Ubuntu One @ simple")

    def test_complex_token_name(self):
        name = ubi_ubuntuone.get_token_name('simple @ complex')
        self.assertEqual(name, "Ubuntu One @ simple AT complex")


class BaseTestPageGtk(unittest.TestCase):

    def setUp(self):
        mock_controller = Mock()
        mock_controller.oem_config = False
        self.page = ubi_ubuntuone.PageGtk(mock_controller, ui=Mock())
        self.page.db = Mock(name='db')
        self.page.plugin_set_online_state(True)


class TestPageGtk(BaseTestPageGtk):

    def test_ui_visible(self):
        self.page.plugin_get_current_page()
        self.assertTrue(self.page.entry_email.get_property("visible"))

    def test_init_ui(self):
        self.page.plugin_get_current_page()
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_LOGIN)

    def test_switch_pages(self):
        self.page.plugin_get_current_page()
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_LOGIN)
        self.page.plugin_on_next_clicked()
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_REGISTER)
        # How to "click" the tc label?
        self.page.on_u1_terms_activate_link(None, None)
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_TC)
        self.page.plugin_on_back_clicked()
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_REGISTER)
        self.page.plugin_on_back_clicked()
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_LOGIN)

    def test_verify_email_entry(self):
        self.assertFalse(self.page._verify_email_entry("meep"))
        self.assertTrue(self.page._verify_email_entry("mup.frb@example.com"))
        self.assertTrue(self.page._verify_email_entry("mup@example"))
        self.assertTrue(self.page._verify_email_entry("mup\@foo.com@example"))

    def test_verify_password_entry(self):
        self.assertFalse(self.page._verify_password_entry(""))
        self.assertTrue(self.page._verify_password_entry("xxxx1234"))


class RegisterTestCase(BaseTestPageGtk):

    def setUp(self):
        super().setUp()
        self.page.notebook_main.set_current_page(
            ubi_ubuntuone.PAGE_REGISTER)
        self.page.info_loop(None)

    def test_allow_go_forward_not_without_any_password(self):
        self.assertEqual(
            self.page.notebook_main.get_current_page(),
            ubi_ubuntuone.PAGE_REGISTER)
        self.page.entry_email1.set_text("foo")
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_allow_go_foward_not_without_matching_password(self):
        self.page.entry_email1.set_text("foo@bar.com")
        self.page.u1_name.set_text("Joe Bloggs")
        self.page.u1_password.set_text("pw12345678")
        self.page.u1_verified_password.set_text("12345678pwd")
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_allow_go_foward_not_without_name(self):
        self.page.entry_email1.set_text("foo@bar.com")
        self.page.u1_password.set_text("pw12345678")
        self.page.u1_verified_password.set_text("pw12345678")
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_allow_go_foward_not_too_short(self):
        self.page.entry_email1.set_text("foo@bar.com")
        self.page.u1_name.set_text("Joe Bloggs")
        self.page.u1_password.set_text("pw")
        self.page.u1_verified_password.set_text("pw")
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_allow_go_foward_not_tc(self):
        self.page.entry_email1.set_text("foo@bar.com")
        self.page.u1_name.set_text("Joe Bloggs")
        self.page.u1_password.set_text("pw12345678")
        self.page.u1_verified_password.set_text("pw12345678")
        self.page.u1_tc_check.set_active(False)
        self.page.u1_tc_check.toggled()
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_allow_go_foward(self):
        self.page.entry_email1.set_text("foo@bar.com")
        self.page.u1_name.set_text("Joe Bloggs")
        self.page.u1_password.set_text("pw12345678")
        self.page.u1_verified_password.set_text("pw12345678")
        self.page.u1_tc_check.set_active(True)
        self.page.u1_tc_check.toggled()
        self.page.controller.allow_go_forward.assert_called_with(True)


class LoginTestCase(BaseTestPageGtk):

    def setUp(self):
        super().setUp()
        self.page.notebook_main.set_current_page(
            ubi_ubuntuone.PAGE_LOGIN)
        self.page.info_loop(None)

    def test_login_allow_go_forward_not_email(self):
        self.page.entry_email.set_text("foo")
        self.page.u1_password_existing.set_text("pass1234")
        self.page.u1_existing_account.set_active(True)
        self.page.u1_existing_account.toggled()
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_login_allow_go_forward_new(self):
        self.page.u1_new_account.set_active(True)
        self.page.u1_new_account.toggled()
        self.page.controller.allow_go_forward.assert_called_with(True)

    def test_login_allow_go_foward_not_short(self):
        self.page.entry_email.set_text("foo@bar.com")
        self.page.u1_password_existing.set_text("pass")
        self.page.u1_existing_account.set_active(True)
        self.page.u1_existing_account.toggled()
        self.page.controller.allow_go_forward.assert_called_with(False)

    def test_login_allow_go_foward(self):
        self.page.entry_email.set_text("foo@bar.com")
        self.page.u1_password_existing.set_text("pass1234")
        self.page.u1_existing_account.set_active(True)
        self.page.u1_existing_account.toggled()
        self.page.controller.allow_go_forward.assert_called_with(True)


@patch('syslog.syslog', new=print)
@patch.object(ubi_ubuntuone, 'get_token_name')
@patch('gi.repository.Gtk')
class NextButtonActionTestCase(BaseTestPageGtk):

    def _call_register(self, mock_token_name, create_success=True):
        mock_token_name.return_value = 'tokenname'

        self.page.notebook_main.set_current_page(ubi_ubuntuone.PAGE_REGISTER)
        self.page.entry_email1.set_text("foo@bar.com")
        self.page.u1_name.set_text("Joe Bloggs")
        self.page.u1_password.set_text("pw12345678")
        self.page.u1_verified_password.set_text("pw12345678")
        self.page.u1_tc_check.set_active(True)
        self.page.u1_tc_check.toggled()
        self.page.controller.allow_go_forward.assert_called_with(True)

        def set_page_register_success(*args, **kwargs):
            self.page.account_creation_successful = create_success

        with patch.multiple(
                self.page,
                register_new_sso_account=DEFAULT,
                login_to_sso=DEFAULT) as mocks:
            mr = mocks['register_new_sso_account']
            mr.side_effect = set_page_register_success

            self.page.plugin_on_next_clicked()

            # TODO displayname is temporarily just the email, pending UI
            mr.assert_called_once_with("foo@bar.com", "pw12345678",
                                       "Joe Bloggs")

            if create_success:
                ml = mocks['login_to_sso']
                ml.assert_called_once_with(
                    "foo@bar.com", "pw12345678", 'tokenname',
                    ubi_ubuntuone.PAGE_REGISTER)

    def test_call_register_success(self, mock_gtk, mock_token_name):
        self._call_register(mock_token_name)

    def test_call_register_err(self, mock_gtk, mock_token_name):
        self._call_register(mock_token_name, create_success=False)

    def test_call_login(self, mock_gtk, mock_token_name):
        mock_token_name.return_value = 'tokenname'

        self.page.notebook_main.set_current_page(ubi_ubuntuone.PAGE_LOGIN)
        self.page.entry_email.set_text("foo@bar.com")
        self.page.u1_existing_account.set_active(True)
        self.page.u1_password_existing.set_text("pass1234")

        with patch.object(self.page, 'login_to_sso') as mock_login:
            self.page.plugin_on_next_clicked()
            mock_login.assert_called_once_with("foo@bar.com", "pass1234",
                                               'tokenname',
                                               ubi_ubuntuone.PAGE_LOGIN)


@patch('syslog.syslog', new=print)
@patch('gi.repository.Gtk')
class SSOAPITestCase(BaseTestPageGtk):

    def _call_handle_done(self, status, response_body, action, from_page):
        mock_session = Mock()
        mock_msg = Mock()
        cfgstr = ('response_body.flatten.return_value'
                  '.get_data.return_value.decode.return_value')
        cfg = {cfgstr: response_body}
        mock_msg.configure_mock(**cfg)
        mock_status_code = PropertyMock(return_value=status)
        type(mock_msg).status_code = mock_status_code

        info = {'action': action, 'from_page': from_page}
        self.page._handle_soup_message_done(mock_session, mock_msg, info)
        self.assertEqual(self.page.notebook_main.get_current_page(),
                         from_page)

    def test_handle_done_token_OK(self, mock_gtk):
        expected_body = "TESTBODY"
        self._call_handle_done(http.client.OK, expected_body,
                               ubi_ubuntuone.TOKEN_CALLBACK_ACTION,
                               ubi_ubuntuone.PAGE_LOGIN)
        self.assertEqual(self.page.oauth_token_json,
                         expected_body)

    def test_handle_done_token_CREATED(self, mock_gtk):
        expected_body = "TESTBODY"
        self._call_handle_done(http.client.CREATED,
                               expected_body,
                               ubi_ubuntuone.TOKEN_CALLBACK_ACTION,
                               ubi_ubuntuone.PAGE_LOGIN)
        self.assertEqual(self.page.oauth_token_json,
                         expected_body)

    def test_handle_done_ping_OK(self, mock_gtk):
        expected_body = "TESTBODY"
        self._call_handle_done(http.client.OK, expected_body,
                               ubi_ubuntuone.PING_CALLBACK_ACTION,
                               ubi_ubuntuone.PAGE_LOGIN)
        self.assertTrue(self.page.ping_successful)

    def test_handle_done_ping_CREATED(self, mock_gtk):
        expected_body = "TESTBODY"
        self._call_handle_done(http.client.CREATED,
                               expected_body,
                               ubi_ubuntuone.PING_CALLBACK_ACTION,
                               ubi_ubuntuone.PAGE_LOGIN)
        self.assertTrue(self.page.ping_successful)

    def test_handle_done_error_token(self, mock_gtk):
        expected_body = json.dumps({"message": "tstmsg"})
        # GONE or anything other than OK/CREATED:
        self._call_handle_done(http.client.GONE, expected_body,
                               ubi_ubuntuone.TOKEN_CALLBACK_ACTION,
                               ubi_ubuntuone.PAGE_LOGIN)
        self.assertEqual(self.page.oauth_token_json, None)
        self.assertEqual(self.page.label_global_error.get_text(),
                         "tstmsg")

    def test_handle_done_error_ping(self, mock_gtk):
        expected_body = "error"
        with patch.object(self.page.label_global_error,
                          'get_text') as mock_get_text:
            mock_get_text.return_value = "err"
            # GONE or anything other than OK/CREATED:
            self._call_handle_done(http.client.GONE, expected_body,
                                   ubi_ubuntuone.PING_CALLBACK_ACTION,
                                   ubi_ubuntuone.PAGE_LOGIN)
            self.assertFalse(self.page.ping_successful)
            self.assertEqual(self.page.label_global_error.get_text(),
                             "err")

    @patch('json.dumps')
    def test_login_to_sso(self, mock_json_dumps, mock_gtk):
        email = 'email'
        password = 'pass'
        token_name = 'tok'
        json_ct = 'application/json'
        expected_dict = {'email': email,
                         'password': password,
                         'token_name': token_name}
        # NOTE: in order to avoid failing tests when dict key ordering
        # changes, we pass the actual dict by mocking json.dumps. This
        # way we can compare the dicts instead of their
        # serializations.
        mock_json_dumps.return_value = expected_dict
        with patch.multiple(self.page, soup=DEFAULT, session=DEFAULT) as mocks:
            typeobj = type(mocks['soup'].MemoryUse)
            typeobj.COPY = PropertyMock(return_value=sentinel.COPY)
            self.page.login_to_sso(email, password, token_name,
                                   ubi_ubuntuone.PAGE_LOGIN)
            expected = [call.Message.new("POST",
                                         ubi_ubuntuone.UBUNTU_SSO_URL +
                                         'tokens/oauth'),
                        call.Message.new().set_request(json_ct,
                                                       sentinel.COPY,
                                                       expected_dict,
                                                       len(expected_dict)),
                        call.Message.new().request_headers.append('Accept',
                                                                  json_ct)]
            self.assertEqual(mocks['soup'].mock_calls,
                             expected)

            info = {'action': ubi_ubuntuone.TOKEN_CALLBACK_ACTION,
                    'from_page': ubi_ubuntuone.PAGE_LOGIN}

            e = [call.queue_message(mocks['soup'].Message.new.return_value,
                                    self.page._handle_soup_message_done,
                                    info)]

            self.assertEqual(mocks['session'].mock_calls, e)

    @patch('json.dumps')
    def test_register_new_sso_account(self, mock_json_dumps, mock_gtk):
        email = 'email'
        password = 'pass'
        displayname = 'mr tester'
        json_ct = 'application/json'
        expected_dict = {'email': email,
                         'displayname': displayname,
                         'password': password}

        # See test_login_to_sso for comment about patching json.dumps():
        mock_json_dumps.return_value = expected_dict
        with patch.multiple(self.page, soup=DEFAULT, session=DEFAULT) as mocks:
            typeobj = type(mocks['soup'].MemoryUse)
            typeobj.COPY = PropertyMock(return_value=sentinel.COPY)
            self.page.register_new_sso_account(email, password,
                                               displayname)
            expected = [call.Message.new("POST",
                                         ubi_ubuntuone.UBUNTU_SSO_URL +
                                         'accounts'),
                        call.Message.new().set_request(json_ct,
                                                       sentinel.COPY,
                                                       expected_dict,
                                                       len(expected_dict)),
                        call.Message.new().request_headers.append('Accept',
                                                                  json_ct)]
            self.assertEqual(mocks['soup'].mock_calls,
                             expected)

            info = {'action': ubi_ubuntuone.ACCOUNT_CALLBACK_ACTION,
                    'from_page': ubi_ubuntuone.PAGE_REGISTER}

            e = [call.queue_message(mocks['soup'].Message.new.return_value,
                                    self.page._handle_soup_message_done,
                                    info)]

            self.assertEqual(mocks['session'].mock_calls, e)

    @patch('json.loads')
    @patch.multiple(ubi_ubuntuone, Client=DEFAULT, get_ping_info=DEFAULT)
    def test_ping_u1_url(self, mock_json_loads,
                         mock_gtk, Client, get_ping_info):

        from_page = 1
        email = 'email'
        signed_url = "signed_url"
        signed_headers = {'a': 'b'}
        Client.return_value.sign.return_value = (signed_url,
                                                 signed_headers,
                                                 None)
        get_ping_info.return_value = ('url', {'C': 'D'})
        mock_json_loads.return_value = {'consumer_key': 'ck',
                                        'consumer_secret': 'cs',
                                        'token_key': 'tk',
                                        'token_secret': 'ts'}

        with patch.multiple(self.page, soup=DEFAULT, session=DEFAULT,
                            oauth_token_json=sentinel.token) as mocks:
            self.page.ping_u1_url(email, from_page)

            mock_json_loads.assert_called_once_with(sentinel.token)

            sigtype = oauthlib.oauth1.SIGNATURE_TYPE_AUTH_HEADER
            expected = [call('ck', 'cs', 'tk', 'ts',
                             signature_method=oauthlib.oauth1.SIGNATURE_HMAC,
                             signature_type=sigtype),
                        call().sign('url?C=D', 'GET')]
            self.assertEqual(Client.mock_calls, expected)

            expected = [call.Message.new("GET", signed_url),
                        call.Message.new().request_headers.append('a', 'b')]

            self.assertEqual(mocks['soup'].mock_calls,
                             expected)

            info = {'action': ubi_ubuntuone.PING_CALLBACK_ACTION,
                    'from_page': from_page}

            e = [call.queue_message(mocks['soup'].Message.new.return_value,
                                    self.page._handle_soup_message_done,
                                    info)]

            self.assertEqual(mocks['session'].mock_calls, e)


class CreateKeyringTestCase(BaseTestPageGtk):

    def test_duplicate_token_data_for_v1(self):
        token = dict(token_key="token_key",
                     token_name="token_name",
                     other_key="other")
        newtoken = self.page._duplicate_token_data_for_v1(token)
        self.assertEqual(newtoken["token"], "token_key")
        self.assertEqual(newtoken["name"], "token_name")
        self.assertEqual(newtoken["other_key"], "other")

    @patch('ubiquity.misc.drop_all_privileges', sentinel.drop_privs)
    @patch('subprocess.PIPE', sentinel.PIPE)
    @patch('subprocess.Popen')
    def test_create_keyring_urlencoded(self, mock_Popen):
        fake_token_dict = {'A': 'b/f'}
        d_json = json.dumps(fake_token_dict)
        self.page._user_password = "test password"
        with patch.object(self.page,
                          '_duplicate_token_data_for_v1') as mock_dup, \
                patch.dict('os.environ', {'U1_KEYRING_HELPER': 'cmd'}):
            mock_dup.side_effect = lambda x: x
            self.page._create_keyring_and_store_u1_token(d_json)
            mock_dup.assert_called_once_with(fake_token_dict)

        mock_Popen.assert_called_with(
            ['cmd'],
            stdin=sentinel.PIPE,
            stderr=sentinel.PIPE,
            stdout=sentinel.PIPE,
            preexec_fn=sentinel.drop_privs)
        mock_stdin = mock_Popen.return_value

        e = [call.communicate(input=b'test password\nA=b%2Ff\n')]
        mock_stdin.assert_has_calls(e)

if __name__ == '__main__':
    # run tests in a sourcetree with:
    """
    UBIQUITY_GLADE=./gui/gtk \
    UBIQUITY_PLUGIN_PATH=./ubiquity/plugins/ \
    PYTHONPATH=. python3 tests/test_ubi_ubuntuone.py
    """
    #from test.support import run_unittest
    # run_unittest()
    unittest.main()
