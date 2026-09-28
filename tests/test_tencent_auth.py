import time
import unittest
from unittest.mock import patch
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.tencent_auth import add_routes


class TencentAuthTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.accounts = add_routes(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as s:
            s['last_visit'] = 1
        self.headers = {'X-Requested-With': 'TencentVideo'}

    def create(self):
        with patch('ffvideo.tencent_auth.api', return_value={'qr_code_id': 'test-qr', 'expire_time': time.time() + 180}):
            response = self.client.post('/api/tencent-video/auth/qrcode', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['data']['qrcode'].startswith('data:image/png;base64,'))

    def test_login_and_csrf_required(self):
        self.assertEqual(self.client.post('/api/tencent-video/auth/qrcode').status_code, 403)
        other = self.app.test_client()
        self.assertEqual(other.get('/api/tencent-video/auth').json['status'], 'need_login')

    def test_both_account_types_and_session_isolation(self):
        for third_type in (1, 2):
            self.create()
            login = {'error_code': 0, 'login_response': {'vuid': '123', 'vusession': 'SECRET',
                'vusession_expire_timestamp': time.time() + 1000, 'third_info': {'third_type': third_type},
                'user_info': {'user_nick': 'Test user'}}}
            with patch('ffvideo.tencent_auth.api', side_effect=[{'status': 3}, login]):
                result = self.client.post('/api/tencent-video/auth/qrcode/poll', headers=self.headers)
            self.assertEqual(result.json['data']['state'], 'confirmed')
            self.assertNotIn('SECRET', result.get_data(as_text=True))
            self.assertTrue(self.client.get('/api/tencent-video/auth').json['data']['loggedIn'])
            with self.client.session_transaction() as s:
                self.assertNotIn('SECRET', str(dict(s)))
            other = self.app.test_client()
            with other.session_transaction() as s:
                s['last_visit'] = 1
            self.assertFalse(other.get('/api/tencent-video/auth').json['data']['loggedIn'])
            self.client.delete('/api/tencent-video/auth', headers=self.headers)
            self.assertFalse(self.accounts.entries)

    def test_expiry_and_failed_exchange_never_login(self):
        self.create()
        with patch('ffvideo.tencent_auth.api', side_effect=[{'status': 3}, {'error_code': 123}]):
            result = self.client.post('/api/tencent-video/auth/qrcode/poll', headers=self.headers)
        self.assertEqual(result.status_code, 502)
        self.assertFalse(self.client.get('/api/tencent-video/auth').json['data']['loggedIn'])
        for entry in self.accounts.entries.values():
            entry['expires'] = time.time() - 1
        self.assertEqual(self.client.post('/api/tencent-video/auth/qrcode/poll', headers=self.headers).status_code, 410)

    def test_logout_during_exchange_does_not_restore_credentials(self):
        self.create()
        def upstream(method, body, guid):
            if method.endswith('QRCodeStatus'):
                return {'status': 3}
            self.accounts.entries.clear()
            return {'error_code': 0, 'login_response': {'vuid': '123', 'vusession': 'SECRET',
                'vusession_expire_timestamp': time.time() + 1000}}
        with patch('ffvideo.tencent_auth.api', side_effect=upstream):
            self.assertEqual(self.client.post('/api/tencent-video/auth/qrcode/poll', headers=self.headers).status_code, 410)
        self.assertFalse(self.accounts.entries)
