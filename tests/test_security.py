import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify
from ffvideo.local_video import add_local_video_route
from ffvideo.gba import add_gba_route
from ffvideo.security import LoginThrottle, install_security
import flask_app


def authenticate(client):
    with client.session_transaction() as session:
        session['last_visit'] = 1


class ApiBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'unit-test-only'
        install_security(self.app)
        self.app.add_url_rule('/api/new-route', view_func=lambda: jsonify(secret='private'))
        self.client = self.app.test_client()

    def test_auth_backstop_covers_new_routes_and_head_requests(self):
        for method in ['get', 'head']:
            self.assertEqual(getattr(self.client, method)('/api/new-route').status_code, 401)
        authenticate(self.client)
        response = self.client.get('/api/new-route')
        self.assertEqual(response.json['secret'], 'private')
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_cross_origin_requests_cannot_use_an_existing_session(self):
        authenticate(self.client)
        for headers in [{'Origin': 'https://attacker.test'}, {'Origin': 'null'},
                        {'Origin': 'http://localhost:4000'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.client.get('/api/new-route', headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/api/new-route', headers={'Origin': 'http://localhost'}).status_code, 200)
        self.assertEqual(self.client.get('/api/new-route', headers={'Origin': 'http://127.0.0.1:3000'}).status_code, 200)
        self.assertEqual(self.client.get('/api/new-route', headers={'Host': 'tmc.example', 'Origin': 'https://tmc.example',
            'X-Forwarded-Proto': 'https'}).status_code, 401)
        self.assertEqual(self.client.get('/api/new-route', headers={'Host': 'tmc.example', 'Origin': 'https://attacker.test',
            'X-Forwarded-Proto': 'https'}).status_code, 403)


class FileBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'video'
        self.video.mkdir()
        (self.video / 'normal.mp4').write_bytes(b'video-fixture')
        (self.root / 'secret.txt').write_bytes(b'private-fixture')
        self.app = Flask(__name__)
        self.app.secret_key = 'unit-test-only'
        add_local_video_route(self.app)
        add_gba_route(self.app)
        self.client = self.app.test_client()

    def test_local_video_requires_login_and_cannot_escape_its_root(self):
        with patch('ffvideo.local_video.get_config_by_key', return_value=str(self.video)):
            self.assertEqual(self.client.get('/api/video/list').json['status'], 'need_login')
            self.assertEqual(self.client.get('/api/video/files/normal.mp4').json['status'], 'need_login')
            authenticate(self.client)
            with self.client.get('/api/video/files/normal.mp4') as response:
                self.assertEqual(response.data, b'video-fixture')
            self.assertEqual(self.client.get('/api/video/files/../secret.txt').status_code, 403)
            self.assertEqual(self.client.get('/api/video/list?path=..').status_code, 403)
            self.assertEqual(self.client.get('/api/video/files/../video-other/secret.txt').status_code, 403)

    def test_links_cannot_bypass_video_and_gba_path_checks(self):
        link = self.video / 'linked.mp4'
        try:
            link.symlink_to(self.root / 'secret.txt')
        except OSError:
            self.skipTest('Creating symlinks is not available on this host')
        authenticate(self.client)
        with patch('ffvideo.local_video.get_config_by_key', return_value=str(self.video)), \
             patch('ffvideo.gba.get_gba_root_path', return_value=str(self.video)):
            self.assertEqual(self.client.get('/api/video/files/linked.mp4').status_code, 403)
            self.assertEqual(self.client.get('/api/gba/files/linked.mp4').status_code, 403)

    def test_gba_files_and_save_mutations_require_login(self):
        for method, path in [('get', '/api/gba/list'), ('get', '/api/gba/files/private.gba'),
                             ('get', '/api/gba/remote/game'), ('get', '/api/gba/saves/game'),
                             ('put', '/api/gba/saves/game'), ('delete', '/api/gba/saves/game'),
                             ('get', '/api/gba/states/game'), ('get', '/api/gba/states/game/1'),
                             ('put', '/api/gba/states/game/1'), ('delete', '/api/gba/states/game/1')]:
            with self.subTest(method=method, path=path):
                self.assertEqual(getattr(self.client, method)(path).json['status'], 'need_login')

    def test_oversized_gba_saves_are_rejected_without_modifying_existing_file(self):
        authenticate(self.client)
        target = self.root / 'game.sav'
        target.write_bytes(b'original')
        with patch('ffvideo.gba.get_save_file_path', return_value=str(target)):
            self.assertEqual(self.client.put('/api/gba/saves/game', data=b'x' * (2 * 1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(target.read_bytes(), b'original')

    def test_precompressed_static_files_cannot_escape_web_root(self):
        web_root = self.root / 'web' / 'dist'
        web_root.mkdir(parents=True)
        (web_root / 'normal.js').write_bytes(b'normal')
        (web_root / 'normal.js.gz').write_bytes(b'compressed-fixture')
        (self.root / 'secret.txt.gz').write_bytes(b'compressed-private')
        with patch.object(flask_app.app, 'root_path', str(self.root)):
            client = flask_app.app.test_client()
            response = client.get('/normal.js', headers={'Accept-Encoding': 'gzip'})
            self.assertEqual(response.data, b'compressed-fixture')
            self.assertEqual(response.headers['Content-Encoding'], 'gzip')
            response.close()
            self.assertEqual(client.get('/../../secret.txt', headers={'Accept-Encoding': 'gzip'}).status_code, 403)


class LoginTest(unittest.TestCase):
    def test_login_throttle_expires_and_clears_after_success(self):
        now = [0]
        limiter = LoginThrottle(clock=lambda: now[0])
        with patch.dict(flask_app.app.extensions, {'login_throttle': limiter}), \
             patch('flask_app.get_config_by_key', return_value='test-password'):
            client = flask_app.app.test_client()
            for _ in range(10):
                self.assertEqual(client.post('/api/login', json={'password': 'wrong'}).status_code, 401)
            blocked = client.post('/api/login', json={'password': 'test-password'})
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers['Retry-After'], '60')
            now[0] = 61
            self.assertEqual(client.post('/api/login', json={'password': 'test-password'}).status_code, 200)
            self.assertEqual(limiter.retry_after('127.0.0.1'), 0)
            self.assertEqual(client.get('/api/config').status_code, 200)

    def test_malformed_login_and_cross_site_login_are_rejected(self):
        with patch.dict(flask_app.app.extensions, {'login_throttle': LoginThrottle()}):
            client = flask_app.app.test_client()
            for data in [None, [], {'password': None}]:
                self.assertEqual(client.post('/api/login', json=data).status_code, 400)
            self.assertEqual(client.post('/api/login', json={'password': '\ud800'}).status_code, 400)
            self.assertEqual(client.post('/api/login', data=b'x' * 2049, content_type='application/json',
                environ_overrides={'CONTENT_LENGTH': '', 'wsgi.input_terminated': True}).status_code, 413)
            self.assertEqual(client.post('/api/login', json={'password': 'x'}, headers={'Origin': 'https://attacker.test'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
