import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

import requests
from bilibili_api import Credential
from bilibili_api.exceptions import ResponseCodeException
from flask import Flask

from ffvideo.bili_auth import BilibiliAuthError, BilibiliQrLogin, PASSPORT
from ffvideo import bv


class Reply:
    def __init__(self, data=None, cookies=None, status=200, location=None):
        self.data = data
        self.cookies = cookies or {}
        self.status_code = status
        self.headers = {'Location': location} if location else {}

    def json(self):
        return {'code': 0, 'data': self.data}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass


class Session:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.headers = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.replies)
        if isinstance(response, Exception):
            raise response
        for name, value in response.cookies.items():
            self.cookies.set(name, value, domain='passport.bilibili.com')
        return response

    def close(self):
        pass


COOKIES = {'SESSDATA': 'test%2Csession', 'bili_jct': 'test-csrf', 'DedeUserID': '1234'}


def login_with(replies):
    session = Session(replies)
    with patch('ffvideo.bili_auth.requests.Session', return_value=session):
        login = BilibiliQrLogin()
    login.key = 'test-qr-key'
    return login, session


class QrLoginTest(unittest.TestCase):
    def test_generates_qr_in_memory(self):
        login, session = login_with([Reply({'url': 'https://account.bilibili.com/h5/account-h5/auth/scan-web?key=test', 'qrcode_key': 'new-key'})])
        self.assertTrue(login.generate_qrcode().startswith('data:image/png;base64,iVBOR'))
        self.assertEqual(login.key, 'new-key')
        self.assertEqual(session.calls[0][0], PASSPORT + 'generate')

    def test_waiting_states_do_not_create_credentials(self):
        login, session = login_with([Reply({'code': code}) for code in (86101, 86090, 86038)])
        self.assertEqual([login.check_state() for _ in range(3)], ['scan', 'confirm', 'timeout'])
        self.assertIsNone(login.credential)
        self.assertEqual(len(session.calls), 3)

    def test_reads_success_cookies_from_poll_headers(self):
        login, session = login_with([Reply({'code': 0, 'url': '', 'refresh_token': 'refresh'}, cookies=COOKIES)])
        self.assertEqual(login.check_state(), 'done')
        self.assertEqual(login.get_credential().sessdata, COOKIES['SESSDATA'])
        self.assertEqual(login.get_credential().ac_time_value, 'refresh')
        self.assertEqual(login.check_state(), 'done')
        self.assertEqual(len(session.calls), 1)

    def test_follows_cross_domain_ticket_and_keeps_cookies_on_redirect(self):
        ticket = 'https://passport.biligame.com/x/passport-login/web/crossDomain?ticket=private'
        login, session = login_with([Reply({'code': 0, 'url': ticket, 'refresh_token': 'refresh'}),
                                    Reply(cookies=COOKIES, status=302, location='https://www.bilibili.com/')])
        self.assertEqual(login.check_state(), 'done')
        self.assertEqual(login.get_credential().dedeuserid, '1234')
        self.assertEqual(session.calls[1][0], ticket)
        self.assertIn('Mozilla', session.headers['User-Agent'])
        self.assertFalse(session.calls[1][1]['allow_redirects'])
        self.assertEqual(len(session.calls), 2)

    def test_legacy_cookie_url_remains_supported(self):
        login, session = login_with([Reply({'code': 0, 'url': 'https://passport.biligame.com/crossDomain?' + urlencode(COOKIES)})])
        self.assertEqual(login.check_state(), 'done')
        self.assertEqual(login.get_credential().sessdata, COOKIES['SESSDATA'])
        self.assertEqual(len(session.calls), 1)

    def test_cross_domain_retry_does_not_reuse_consumed_qr_key(self):
        ticket = 'https://passport.biligame.com/x/passport-login/web/crossDomain?ticket=private'
        login, session = login_with([Reply({'code': 0, 'url': ticket}), requests.Timeout(ticket), Reply(cookies=COOKIES)])
        with self.assertRaises(BilibiliAuthError) as error:
            login.check_state()
        self.assertNotIn('private', str(error.exception))
        self.assertEqual(login.check_state(), 'done')
        self.assertEqual([url for url, _ in session.calls].count(PASSPORT + 'poll'), 1)

    def test_rejects_incomplete_and_unknown_success_responses(self):
        for data in [{'code': 0, 'url': '', 'refresh_token': 'only-refresh'}, {'code': 12345}]:
            login, _session = login_with([Reply(data)])
            with self.assertRaises(BilibiliAuthError):
                login.check_state()
            self.assertIsNone(login.credential)

    def test_rejects_untrusted_ticket_and_redirect_hosts(self):
        for url in ['https://attacker.test/ticket', 'http://passport.bilibili.com/ticket',
                    'https://passport.biligame.com:8443/ticket', 'https://user@passport.bilibili.com/ticket']:
            login, session = login_with([Reply({'code': 0, 'url': url})])
            with self.assertRaises(BilibiliAuthError):
                login.check_state()
            self.assertEqual(len(session.calls), 1)
        login, session = login_with([Reply({'code': 0, 'url': 'https://passport.biligame.com/ticket'}),
                                    Reply(status=302, location='https://attacker.test/steal')])
        with self.assertRaises(BilibiliAuthError):
            login.check_state()
        self.assertEqual(len(session.calls), 2)


class AuthPersistenceTest(unittest.TestCase):
    def test_incomplete_credential_does_not_overwrite_saved_login(self):
        with patch('ffvideo.bv.put_config_by_key') as write:
            with self.assertRaises(BilibiliAuthError):
                bv.save_bilibili_credential(Credential(ac_time_value='only-refresh'))
            write.assert_not_called()

    def test_transient_profile_failure_retains_saved_login(self):
        for error in [requests.Timeout('temporary'), ResponseCodeException(-412, 'risk control')]:
            with patch('ffvideo.bv.get_bilibili_credential', return_value=Credential(sessdata='session')), \
                 patch('ffvideo.bv.sync', side_effect=error), patch('ffvideo.bv.user.get_self_info', new=Mock(return_value=None)), \
                 patch('ffvideo.bv.clear_bilibili_credential') as clear:
                self.assertTrue(bv.get_bilibili_auth_status()['loggedIn'])
                clear.assert_not_called()

    def test_expired_login_is_cleared(self):
        with patch('ffvideo.bv.get_bilibili_credential', return_value=Credential(sessdata='session')), \
             patch('ffvideo.bv.sync', side_effect=ResponseCodeException(-101, 'not logged in')), \
             patch('ffvideo.bv.user.get_self_info', new=Mock(return_value=None)), patch('ffvideo.bv.clear_bilibili_credential') as clear:
            self.assertFalse(bv.get_bilibili_auth_status()['loggedIn'])
            clear.assert_called_once()

    def test_qr_route_reports_success_only_after_complete_credentials_are_saved(self):
        app = Flask(__name__)
        app.secret_key = 'unit-test-only'
        bv.add_bv_route(app)
        client = app.test_client()
        with client.session_transaction() as session:
            session['last_visit'] = 1
        pending = Mock()
        pending.check_state.return_value = 'done'
        for credential, expected_status in [(Credential(ac_time_value='only-refresh'), 502),
                                             (Credential(sessdata='session', bili_jct='csrf', dedeuserid='1234'), 200)]:
            pending.get_credential.return_value = credential
            with patch.object(bv, 'qr_login', pending), patch.object(bv, 'put_config_by_key') as write, \
                 patch.object(bv, 'get_bilibili_auth_status', return_value={'loggedIn': True, 'profile': None}):
                response = client.get('/api/bilibili/auth/qrcode/poll')
                self.assertEqual(response.status_code, expected_status)
                if expected_status == 200:
                    self.assertTrue(response.json['data']['loggedIn'])
                    self.assertEqual(write.call_count, 5)
                else:
                    write.assert_not_called()
                    self.assertEqual(response.json['status'], 'qrcode_poll_failed')


if __name__ == '__main__':
    unittest.main()
