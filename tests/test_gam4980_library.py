import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from ffvideo.gam4980 import add_gam4980_route


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'games'
        self.root.mkdir()
        (self.root / 'RPG').mkdir()
        (self.root / 'RPG' / '娴嬭瘯.GAM').write_bytes(bytes(100))
        (self.root / 'secret.txt').write_text('not a game')
        (self.root / 'bad.gam').write_bytes(b'x')
        self.patch = patch('ffvideo.gam4980.DEFAULT_GAME_ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        app = Flask(__name__)
        app.secret_key = 'test'
        add_gam4980_route(app)
        self.app, self.client = app, app.test_client()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1

    def test_list_and_download(self):
        data = self.client.get('/api/gam4980/list').json['data']
        self.assertEqual([i['name'] for i in data['items']], ['RPG', 'bad.gam'])
        self.assertFalse(data['items'][1]['playable'])
        item = self.client.get('/api/gam4980/list?path=RPG').json['data']['items'][0]
        response = self.client.get(item['url'])
        self.assertEqual(response.data, bytes(100))
        response.close()
        self.assertEqual(self.client.get('/api/gam4980/files/bad.gam').status_code, 413)
        self.assertEqual(self.client.get('/api/gam4980/files/secret.txt').status_code, 404)

    def test_auth_traversal_and_symlink(self):
        self.assertEqual(self.app.test_client().get('/api/gam4980/list').json['status'], 'need_login')
        self.assertEqual(self.client.get('/api/gam4980/list?path=../').status_code, 403)
        outside = Path(self.temp.name) / 'outside.gam'
        outside.write_bytes(bytes(100))
        (self.root / 'link.gam').symlink_to(outside)
        self.assertEqual(self.client.get('/api/gam4980/files/link.gam').status_code, 403)
        self.assertNotIn('link.gam', [i['name'] for i in self.client.get('/api/gam4980/list').json['data']['items']])

    def test_upload_validation_and_no_overwrite(self):
        url = '/api/gam4980/upload?name=test.gam'
        self.assertEqual(self.app.test_client().post(url, data=bytes(100)).json['status'], 'need_login')
        self.assertEqual(self.client.post(url, data=bytes(100)).status_code, 200)
        self.assertEqual((self.root / 'test.gam').read_bytes(), bytes(100))
        self.assertEqual(self.client.post(url, data=b'x'*100).status_code, 409)
        self.assertEqual((self.root / 'test.gam').read_bytes(), bytes(100))
        self.assertEqual(self.client.post('/api/gam4980/upload?name=../evil.gam', data=bytes(100)).status_code, 400)
        self.assertEqual(self.client.post('/api/gam4980/upload?name=evil.txt', data=bytes(100)).status_code, 400)
        self.assertEqual(self.client.post('/api/gam4980/upload?name=small.gam', data=b'x').status_code, 413)
        self.assertEqual(self.client.post('/api/gam4980/upload?name=large.gam', data=bytes(0x1e0001)).status_code, 413)
