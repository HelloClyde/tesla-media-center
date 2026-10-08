import threading
import time
import types
import os
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.douyin import add_routes


class DouyinAuthTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__); self.app.secret_key = 'test'; add_routes(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as s: s['last_visit'] = 1
        self.headers = {'X-Requested-With': 'Douyin'}
        self.accounts = self.app.extensions['douyin_accounts']

    def seed(self, cookies=None):
        entry = dict(state='confirmed' if cookies else 'waiting', cookies=cookies or [], qrcode='qr',
                     message='', expires=time.time()+600, touched=time.time(), cancel=threading.Event())
        self.accounts.entries['test-key'] = entry
        with self.client.session_transaction() as s: s['douyin_account'] = 'test-key'
        return entry

    def test_requires_site_login_and_mutation_header(self):
        other = self.app.test_client()
        self.assertEqual(other.get('/api/douyin/auth').json['status'], 'need_login')
        self.assertEqual(self.client.post('/api/douyin/auth/qrcode').status_code, 403)
        self.assertEqual(self.client.delete('/api/douyin/auth').status_code, 403)

    def test_isolation_and_no_credential_disclosure(self):
        self.seed([{'name':'sessionid','value':'secret', 'domain':'.douyin.com', 'path':'/'}])
        r = self.client.get('/api/douyin/auth')
        self.assertTrue(r.json['data']['loggedIn']); self.assertNotIn(b'secret', r.data)
        self.assertIn('no-store', r.headers['Cache-Control'])
        other = self.app.test_client()
        with other.session_transaction() as s: s['last_visit'] = 1
        self.assertFalse(other.get('/api/douyin/auth').json['data']['loggedIn'])
        with patch('ffvideo.douyin.read_page', return_value={'items': []}) as read:
            self.client.get('/api/douyin/home')
            self.assertEqual(read.call_args.kwargs['cookies'][0]['value'], 'secret')
            other.get('/api/douyin/home')
            self.assertEqual(read.call_args.kwargs['cookies'], [])

    def test_cancel_cannot_restore_credentials(self):
        entry = self.seed()
        self.client.delete('/api/douyin/auth/qrcode', headers=self.headers)
        self.assertTrue(entry['cancel'].is_set())
        self.accounts.update(entry, cookies=[{'value':'late'}])
        self.assertFalse(entry['cookies']); self.assertFalse(self.accounts.entries)

    def test_close_preserves_confirmed_logout_removes(self):
        entry = self.seed([{'name':'sessionid', 'value':'secret'}])
        self.client.delete('/api/douyin/auth/qrcode', headers=self.headers)
        self.assertTrue(self.client.get('/api/douyin/auth').json['data']['loggedIn'])
        self.client.delete('/api/douyin/auth', headers=self.headers)
        self.assertTrue(entry['cancel'].is_set()); self.assertFalse(self.accounts.entries)
        self.assertFalse(self.client.get('/api/douyin/auth').json['data']['loggedIn'])

    def test_expiration_and_creation(self):
        entry = self.seed(); entry['expires'] = time.time()-1
        self.assertEqual(self.client.get('/api/douyin/auth/qrcode').json['data']['state'], 'expired')
        self.assertTrue(entry['cancel'].is_set())
        with patch('ffvideo.douyin_auth.threading.Thread') as worker:
            response = self.client.post('/api/douyin/auth/qrcode', headers=self.headers)
            self.assertEqual(response.json['data']['state'], 'loading')
            worker.return_value.start.assert_called_once()

    def test_http_auth_accepts_confirmed_session_cookie(self):
        entry = self.seed()
        cookie = types.SimpleNamespace(name='sessionid', value='secret', domain='.douyin.com',
                                       path='/', secure=True, has_nonstandard_attr=lambda _: True)
        http_client = MagicMock()
        http_client.cookies.jar = []
        http_module = types.ModuleType('tools.douyin.visitor_probe')
        http_module.create_visitor_session = MagicMock(return_value=http_client)
        http_module.get_qrcode = MagicMock(return_value={'qrcode': 'aGVsbG8=', 'token': 'qr-token'})
        http_module.check_qrcode = MagicMock(return_value={
            'status': 'confirmed', 'redirect_url': 'https://login.douyin.com/finish?ticket=secret'})
        def finish(_client, _url):
            http_client.cookies.jar = [cookie]
        http_module.finish_qrcode_login = MagicMock(side_effect=finish)
        self.accounts.slots.acquire()
        with patch.dict('sys.modules', {'tools.douyin.visitor_probe': http_module}):
            self.accounts.run_http(entry)
        self.assertEqual(entry['state'], 'confirmed')
        self.assertTrue(entry['qrcode'] == '')
        self.assertEqual(entry['cookies'][0]['name'], 'sessionid')
        http_module.finish_qrcode_login.assert_called_once_with(
            http_client, 'https://login.douyin.com/finish?ticket=secret')
        http_client.close.assert_called_once()

    def test_qr_redirect_only_follows_official_hosts(self):
        from tools.douyin.visitor_probe import finish_qrcode_login
        client = MagicMock()
        client.get.side_effect = [
            types.SimpleNamespace(status_code=302, headers={'Location': 'https://www.douyin.com/'}),
            types.SimpleNamespace(status_code=200, headers={}),
        ]
        finish_qrcode_login(client, 'https://login.douyin.com/finish?ticket=secret')
        self.assertEqual(client.get.call_count, 2)
        with self.assertRaisesRegex(ValueError, 'official domains'):
            finish_qrcode_login(client, 'https://example.com/finish')
        self.assertEqual(client.get.call_count, 2)

    def test_http_auth_is_selected_by_default(self):
        entry = self.seed()
        with patch.dict(os.environ):
            os.environ.pop('TMC_DOUYIN_HTTP_AUTH', None)
            with patch.object(self.accounts, 'run_http') as run_http:
                self.accounts.run(entry)
                run_http.assert_called_once_with(entry)

    def test_browser_cache_separates_accounts(self):
        from ffvideo import douyin_browser as browser
        with browser._cache_lock: browser._cache.clear()
        with patch.object(browser, '_read_page', side_effect=[{'items': ['one']}, {'items': ['two']}, {'items': []}]) as read:
            one = [{'name': 'sessionid', 'value': 'one'}]
            two = [{'name': 'sessionid', 'value': 'two'}]
            self.assertEqual(browser.read_page('test', cookies=one)['items'], ['one'])
            self.assertEqual(browser.read_page('test', cookies=two)['items'], ['two'])
            self.assertEqual(browser.read_page('test')['items'], [])
            self.assertEqual(browser.read_page('test', cookies=one)['items'], ['one'])
            self.assertEqual(read.call_count, 3)
        with browser._cache_lock: browser._cache.clear()
    def test_comments_are_authenticated_and_use_current_credentials(self):
        self.assertEqual(self.app.test_client().get('/api/douyin/comments?vid=7674149236469451482').json['status'], 'need_login')
        self.assertEqual(self.client.get('/api/douyin/comments?vid=invalid').status_code, 400)
        self.seed([{'name':'sessionid','value':'secret'}])
        with patch('ffvideo.douyin.read_page', return_value={'items':[{'id':'1','author':'test','text':'hello','likes':2}]}) as read:
            result = self.client.get('/api/douyin/comments?vid=7674149236469451482')
            self.assertEqual(result.json['data']['items'][0]['text'], 'hello')
            self.assertEqual(read.call_args.kwargs['source'], 'comments')
            self.assertEqual(read.call_args.kwargs['cookies'][0]['value'], 'secret')
