"""Offline contract tests: auth isolation, QR lifecycle and private credential storage."""
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from flask import Flask
from qqmusic_api import Credential
from ffvideo import qqmusic


class QQMusicTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = patch.object(qqmusic, 'STORE', Path(self.directory.name))
        self.store.start()
        qqmusic.PENDING.clear()
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.testing = True
        qqmusic.add_qqmusic_route(self.app)
        self.client = self.app.test_client()
        self.other = self.app.test_client()
        for client in (self.client, self.other):
            with client.session_transaction() as session:
                session['last_visit'] = int(time.time())
            client.get('/api/qqmusic/account')

    def tearDown(self):
        self.store.stop()
        self.directory.cleanup()

    def test_requires_app_login(self):
        client = self.app.test_client()
        for method, path in [('get', 'account'), ('get', 'search?q=test'), ('get', 'play?mid=test'),
                             ('post', 'login'), ('post', 'login/status'), ('post', 'logout')]:
            self.assertEqual(getattr(client, method)('/api/qqmusic/' + path).json['status'], 'need_login')

    def test_invalid_input_does_not_call_upstream(self):
        with patch.object(qqmusic, 'run') as run:
            for path in ['search?q=&page=1', 'search?q=test&page=0', 'play?mid=../../config.json', 'play?mid=test&quality=invalid']:
                self.assertEqual(self.client.get('/api/qqmusic/' + path).status_code, 400)
            run.assert_not_called()

    def test_quality_and_unavailable_source(self):
        file = SimpleNamespace(media_mid='media', size_128mp3=100, size_320mp3=200, size_flac=300)
        song = SimpleNamespace(
            get_detail=AsyncMock(return_value=SimpleNamespace(track=SimpleNamespace(file=file))),
            get_song_urls=AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(purl='song.mp3')])) ,
            get_cdn_dispatch=AsyncMock(return_value=SimpleNamespace(sip=['https://sjy6.stream.qqmusic.qq.com/'])))
        client = SimpleNamespace(song=song)
        with patch.object(qqmusic, 'run', side_effect=lambda sid, operation: asyncio.run(operation(client))):
            for quality, (file_type, _, _) in qqmusic.QUALITIES.items():
                result = self.client.get('/api/qqmusic/play?mid=test&quality=' + quality)
                self.assertEqual(result.json['data']['quality'], quality)
                self.assertEqual(song.get_song_urls.call_args.kwargs['file_type'], file_type)
            song.get_song_urls.reset_mock()
            file.size_flac = 0
            self.assertEqual(self.client.get('/api/qqmusic/play?mid=test&quality=lossless').status_code, 400)
            song.get_song_urls.assert_not_called()

    def test_login_isolation_encryption_and_logout(self):
        qr = SimpleNamespace(data=b'qr', mimetype='image/png')
        with patch.object(qqmusic, 'run', return_value=qr):
            response = self.client.post('/api/qqmusic/login', json={})
            token = response.json['data']['token']
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.other.post('/api/qqmusic/login/status', json={'token': token}).json['data']['state'], 'TIMEOUT')
        cred = Credential(musicid=123, musickey='private-music-key', musickeyCreateTime=int(time.time()), keyExpiresIn=3600)
        result = SimpleNamespace(event=SimpleNamespace(name='DONE'), credential=cred)
        with patch.object(qqmusic, 'run', return_value=result):
            self.assertEqual(self.client.post('/api/qqmusic/login/status', json={'token': token}).json['data']['state'], 'DONE')
        data = self.client.get('/api/qqmusic/account').json['data']
        self.assertEqual(data, {'loggedIn': True, 'account': '123'})
        self.assertFalse(self.other.get('/api/qqmusic/account').json['data']['loggedIn'])
        self.assertNotIn(b'private-music-key', next(Path(self.directory.name).iterdir()).read_bytes())
        self.client.post('/api/qqmusic/logout', json={})
        self.assertFalse(self.client.get('/api/qqmusic/account').json['data']['loggedIn'])

    def test_upstream_errors_do_not_leak_credentials(self):
        with patch.object(qqmusic, 'run', side_effect=RuntimeError('secret-token')):
            result = self.client.post('/api/qqmusic/login', json={})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('secret-token', result.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
