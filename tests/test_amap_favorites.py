import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from ffvideo import amap_favorites


AIRPORT = {'id': 'airport', 'name': '杭州萧山国际机场', 'address': '机场路',
           'location': [120.43, 30.23], 'entrance': [120.431, 30.231]}
HOME = {'id': 'home', 'name': '家', 'address': '', 'location': [120.2, 30.2]}


class AmapFavoritesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        path_patch = patch.object(amap_favorites, 'data_path', side_effect=lambda *parts: root.joinpath(*parts))
        path_patch.start()
        self.addCleanup(path_patch.stop)
        app = Flask(__name__)
        app.secret_key = 'favorites-test'
        amap_favorites.add_routes(app)
        self.client = app.test_client()
        self.file = root / 'amap' / 'favorites.json'

    def login(self, client=None):
        with (client or self.client).session_transaction() as session:
            session['last_visit'] = 1

    def test_login_required_and_shared_server_persistence(self):
        self.assertEqual(self.client.get('/api/amap-app/favorites').json['status'], 'need_login')
        self.assertFalse(self.file.exists())
        self.login()
        response = self.client.post('/api/amap-app/favorites', json={'action': 'add', 'place': {**AIRPORT, 'unused': 'discard'}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data']['places'], [AIRPORT])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(self.file.read_text(encoding='utf-8')), {'places': [AIRPORT]})

        other = self.client.application.test_client()
        self.login(other)
        self.assertEqual(other.get('/api/amap-app/favorites').json['data']['places'], [AIRPORT])
        imported = other.post('/api/amap-app/favorites', json={'action': 'import', 'places': [AIRPORT, HOME]})
        self.assertEqual(imported.json['data']['places'], [AIRPORT, HOME])
        removed = self.client.post('/api/amap-app/favorites', json={'action': 'remove', 'id': 'airport'})
        self.assertEqual(removed.json['data']['places'], [HOME])

    def test_invalid_input_and_corrupt_file_do_not_erase_favorites(self):
        self.login()
        self.client.post('/api/amap-app/favorites', json={'action': 'add', 'place': AIRPORT})
        original = self.file.read_bytes()
        invalid = self.client.post('/api/amap-app/favorites', json={'action': 'add',
                                   'place': {**HOME, 'location': [True, 30.2]}})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.file.read_bytes(), original)
        self.file.write_text('{broken', encoding='utf-8')
        failed = self.client.post('/api/amap-app/favorites', json={'action': 'add', 'place': HOME})
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(self.file.read_text(encoding='utf-8'), '{broken')

    def test_import_refuses_overflow_without_dropping_browser_or_server_places(self):
        self.login()
        self.client.post('/api/amap-app/favorites', json={'action': 'add', 'place': AIRPORT})
        original = self.file.read_bytes()
        legacy = [{**HOME, 'id': f'home-{index}'} for index in range(100)]
        response = self.client.post('/api/amap-app/favorites', json={'action': 'import', 'places': legacy})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.file.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
