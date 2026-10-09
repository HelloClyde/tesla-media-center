import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from ffvideo import tesla_appearance


VIN = '5YJYGDEE0MF123456'
RECORD = {
    'appearance': {'color': '#AaBbCc', 'finish': 'satin', 'plate': '沪AD12345', 'plateStyle': 'green'},
    'manualModel': 'modely-high',
}


class TeslaAppearanceTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'appearance.json'
        self.storage = patch.object(tesla_appearance, 'appearance_path', return_value=self.path)
        self.linked = patch.object(tesla_appearance, '_linked', side_effect=lambda vin: vin == VIN)
        self.storage.start()
        self.linked.start()
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        tesla_appearance.add_routes(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1

    def tearDown(self):
        self.linked.stop()
        self.storage.stop()
        self.folder.cleanup()

    def test_per_vin_save_and_migration_does_not_overwrite(self):
        url = f'/api/tesla/appearance/{VIN}'
        self.assertEqual(self.client.get(url).status_code, 204)
        self.assertEqual(self.client.put(url, json=RECORD, headers={'If-None-Match': '*'}).status_code, 200)
        loaded = self.client.get(url)
        self.assertEqual(loaded.json['data']['appearance']['color'], '#aabbcc')
        self.assertEqual(self.client.put(url, json=RECORD, headers={'If-None-Match': '*'}).status_code, 412)
        self.assertEqual(self.client.get('/api/tesla/appearance/default').status_code, 204)
        self.assertEqual(self.client.put('/api/tesla/appearance/default', json=RECORD).status_code, 200)

    def test_selected_vin_is_shared(self):
        url = '/api/tesla/appearance/selection'
        self.assertEqual(self.client.get(url).json['data']['selectedVin'], '')
        self.assertEqual(self.client.put(url, json={'selectedVin': VIN}).status_code, 200)
        self.assertEqual(self.client.get(url).json['data']['selectedVin'], VIN)
        self.assertEqual(self.client.put(url, json={'selectedVin': VIN}, headers={'If-None-Match': '*'}).status_code, 412)

    def test_scene_settings_live_on_server(self):
        url = '/api/tesla/appearance/scene'
        self.assertEqual(self.client.get(url).status_code, 204)
        settings = {'weatherMode': 'rain', 'sceneNight': True}
        self.assertEqual(self.client.put(url, json=settings, headers={'If-None-Match': '*'}).status_code, 200)
        self.assertEqual(self.client.get(url).json['data'], settings)
        self.assertEqual(self.client.put(url, json=settings, headers={'If-None-Match': '*'}).status_code, 412)
        self.assertEqual(self.client.put(url, json={'weatherMode': 'storm', 'sceneNight': True}).status_code, 400)

    def test_rejects_invalid_and_unlinked(self):
        self.assertEqual(self.client.put(f'/api/tesla/appearance/{VIN}', json={**RECORD, 'appearance': {**RECORD['appearance'], 'color': 'red'}}).status_code, 400)
        self.assertEqual(self.client.put('/api/tesla/appearance/5YJYGDEE0MF000000', json=RECORD).status_code, 404)
        self.assertEqual(self.client.put('/api/tesla/appearance/selection', json={'selectedVin': '5YJYGDEE0MF000000'}).status_code, 400)

    def test_requires_tmc_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get(f'/api/tesla/appearance/{VIN}').json['status'], 'need_login')
        self.assertEqual(guest.put(f'/api/tesla/appearance/{VIN}', json=RECORD).json['status'], 'need_login')
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
