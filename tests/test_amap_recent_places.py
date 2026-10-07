import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from ffvideo import amap_recent_places


AIRPORT = {'id': 'airport', 'name': '杭州萧山国际机场', 'address': '机场路',
           'location': [120.43, 30.23], 'entrance': [120.431, 30.231]}


class AmapRecentPlacesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patched = patch.object(amap_recent_places, 'data_path', side_effect=lambda *parts: self.root.joinpath(*parts))
        patched.start()
        self.addCleanup(patched.stop)
        app = Flask(__name__)
        app.secret_key = 'recent-test'
        amap_recent_places.add_routes(app)
        self.client = app.test_client()
        self.url = '/api/amap-app/recent-places'
        self.file = self.root / 'amap' / 'recent-places.json'

    def login(self, client=None):
        with (client or self.client).session_transaction() as session:
            session['last_visit'] = 1

    def add(self, place):
        return self.client.post(self.url, json={'action': 'add', 'place': place})

    def test_requires_login_and_persists_places_and_entrances_across_clients(self):
        self.assertEqual(self.client.get(self.url).json['status'], 'need_login')
        self.assertEqual(self.add(AIRPORT).json['status'], 'need_login')
        self.assertFalse(self.file.exists())
        self.login()
        response = self.add({**AIRPORT, 'unused': 'discard'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data']['places'], [AIRPORT])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(self.file.read_text(encoding='utf-8')), {'places': [AIRPORT]})
        other = self.client.application.test_client()
        self.login(other)
        self.assertEqual(other.get(self.url).json['data']['places'], [AIRPORT])
        self.assertFalse((self.root / 'amap' / 'favorites.json').exists())

    def test_retains_ten_newest_and_moves_a_repeat_to_front(self):
        self.login()
        for index in range(12):
            result = self.add({**AIRPORT, 'id': f'place-{index}'})
            self.assertEqual(result.status_code, 200)
        self.assertEqual([p['id'] for p in result.json['data']['places']],
                         [f'place-{i}' for i in range(11, 1, -1)])
        result = self.add({**AIRPORT, 'id': 'place-5', 'address': '更新地址'})
        places = result.json['data']['places']
        self.assertEqual(len(places), 10)
        self.assertEqual(places[0]['id'], 'place-5')
        self.assertEqual(places[0]['address'], '更新地址')
        self.assertEqual(len({p['id'] for p in places}), 10)

    def test_distinct_coordinate_searches_do_not_overwrite_each_other(self):
        self.login()
        a = {**AIRPORT, 'id': 'coordinate', 'location': [120.1, 30.1]}
        b = {**AIRPORT, 'id': 'coordinate', 'location': [120.2, 30.2]}
        self.add(a)
        self.add(b)
        places = self.add(a).json['data']['places']
        self.assertEqual([p['location'] for p in places], [a['location'], b['location']])
        self.assertEqual(len({p['id'] for p in places}), 2)

    def test_invalid_or_corrupt_data_does_not_erase_history(self):
        self.login()
        self.add(AIRPORT)
        original = self.file.read_bytes()
        self.assertEqual(self.add({**AIRPORT, 'location': [True, 30]}).status_code, 400)
        self.assertEqual(self.client.post(self.url, json={'action': 'unknown'}).status_code, 400)
        self.assertEqual(self.file.read_bytes(), original)
        self.file.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.add(AIRPORT).status_code, 500)
        self.assertEqual(self.file.read_text(encoding='utf-8'), '{broken')

    def test_clear_is_persistent_and_oversized_requests_are_rejected(self):
        self.login()
        self.add(AIRPORT)
        self.assertEqual(self.client.post(self.url, data='x' * 8193).status_code, 413)
        self.assertEqual(self.client.get(self.url).json['data']['places'], [AIRPORT])
        self.assertEqual(self.client.post(self.url, json={'action': 'clear'}).json['data']['places'], [])
        self.assertEqual(self.client.get(self.url).json['data']['places'], [])


if __name__ == '__main__':
    unittest.main()
