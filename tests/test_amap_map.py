import gzip
import json
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from ffvideo import amap_map


class MapTest(unittest.TestCase):
    def test_lane_cache_is_separate_and_cleared_with_base_map(self):
        base = {'level': 15, 'x': 26978, 'y': 9118, 'buildings': []}
        lanes = {'level': 15, 'x': 26978, 'y': 9118, 'laneBoundaries': [[[116.3, 39.9], [116.31, 39.91]]]}
        self.disk.write((15, 26978, 9118), base, 0)
        payload = {'layer': 'lanes', 'level': 15, 'tiles': [[26978, 9118]]}
        with patch.object(amap_map.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({'tiles': [lanes]}).encode())) as run:
            first = self.client.post('/api/amap-app/map', json=payload)
            second = self.client.post('/api/amap-app/map', json=payload)
            self.assertEqual(first.json['data']['tiles'], [lanes])
            self.assertEqual(second.json, first.json)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(json.loads(run.call_args.kwargs['input'])['layer'], 'lanes')
        self.assertEqual(self.disk.read([(15, 26978, 9118)])[0][(15, 26978, 9118)], base)
        self.assertEqual(self.disk.status()['count'], 2)
        self.client.delete('/api/amap-app/cache')
        self.assertEqual(self.disk.status()['count'], 0)

    def test_lane_request_is_bounded(self):
        with patch.object(amap_map.subprocess, 'run') as run:
            for payload in [dict(layer='other', tiles=[[0, 0]]),
                            dict(layer='lanes', level=14, tiles=[[0, 0]]),
                            dict(layer='lanes', level=15, tiles=[[0, 0], [1, 0]])]:
                self.assertEqual(self.client.post('/api/amap-app/map', json=payload).status_code, 400)
            run.assert_not_called()

    def test_building_level_uses_own_cache(self):
        tile = {'level': 15, 'x': 26985, 'y': 9103, 'buildings': [{'id': '7', 'parts': []}]}
        self.disk.write((15, 26985, 9103), tile, 0)
        with patch.object(amap_map.subprocess, 'run') as run:
            response = self.client.post('/api/amap-app/map', json={'level': 15, 'tiles': [[26985, 9103]]})
            run.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data']['tiles'][0]['buildings'], tile['buildings'])
        self.assertEqual(self.disk.read([(14, 26985, 9103)])[0], {})

    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        app.config['AMAP_CACHE_PATH'] = str(Path(temporary.name) / 'map.sqlite3')
        self.disk = amap_map.MapCache(app.config['AMAP_CACHE_PATH'])
        amap_map.add_amap_map_route(app)
        self.app, self.client = app, app.test_client()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1

    def test_map_response_gzip_negotiation(self):
        tile = {'level': 3, 'x': 1, 'y': 2, 'surfaces': [{'name': '道路', 'coordinates': [[116.123, 39.45]] * 500}]}
        self.disk.write((3, 1, 2), tile, 0)
        payload = {'level': 3, 'tiles': [[1, 2]]}
        with patch.object(amap_map.subprocess, 'run') as run:
            plain = self.client.post('/api/amap-app/map', json=payload)
            compressed = self.client.post('/api/amap-app/map', json=payload, headers={'Accept-Encoding': 'gzip, deflate, br'})
            disabled = self.client.post('/api/amap-app/map', json=payload, headers={'Accept-Encoding': 'gzip;q=0, identity;q=1'})
            run.assert_not_called()
        self.assertEqual(compressed.headers['Content-Encoding'], 'gzip')
        self.assertEqual(json.loads(gzip.decompress(compressed.data)), plain.json)
        self.assertLess(len(compressed.data), len(plain.data) / 2)
        self.assertEqual(int(compressed.headers['Content-Length']), len(compressed.data))
        self.assertIn('Accept-Encoding', compressed.headers['Vary'])
        self.assertNotIn('Content-Encoding', disabled.headers)
        self.assertNotIn('Content-Encoding', self.client.get('/api/amap-app/cache', headers={'Accept-Encoding': 'gzip'}).headers)

    def test_cache_settings_api(self):
        for method in ['get', 'put', 'delete']:
            response = getattr(self.app.test_client(), method)('/api/amap-app/cache', json={})
            self.assertEqual(response.json['status'], 'need_login')
        self.assertEqual(self.client.put('/api/amap-app/cache', json={'ttlHours': 0, 'maxMB': 16}).status_code, 400)
        response = self.client.put('/api/amap-app/cache', json={'ttlHours': 24, 'maxMB': 32})
        self.assertEqual(response.json['data']['ttlHours'], 24)
        self.disk.write((3, 1, 2), {'x': 1, 'y': 2}, response.json['data']['generation'])
        self.assertEqual(self.client.get('/api/amap-app/cache').json['data']['count'], 1)
        self.assertEqual(self.client.delete('/api/amap-app/cache').json['data']['count'], 0)

    def test_auth_and_batch_validation(self):
        with patch.object(amap_map.subprocess, 'run') as run:
            self.assertEqual(self.app.test_client().post('/api/amap-app/map', json={}).json['status'], 'need_login')
            for payload in [{}, {'tiles': [[True, 0]]}, {'tiles': [[16384, 0]]}, {'tiles': [[0, 0]] * 25}]:
                self.assertEqual(self.client.post('/api/amap-app/map', json=payload).status_code, 400)
            run.assert_not_called()

    def test_cache_and_failed_tile_not_cached(self):
        good = {'x': 1, 'y': 2, 'collection': {'type': 'FeatureCollection', 'features': []}}
        result = {'tiles': [good, {'x': 2, 'y': 2, 'error': 'unsupported-tile'}]}
        with patch.object(amap_map.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(result).encode())) as run:
            self.assertEqual(self.client.post('/api/amap-app/map', json={'tiles': [[1, 2], [2, 2]]}).json['status'], 'ok')
            self.client.post('/api/amap-app/map', json={'tiles': [[1, 2]]})
            self.assertEqual(run.call_count, 1)
            self.assertNotIn((14, 2, 2), self.disk.read([(14, 2, 2)])[0])

    def test_zoom_cache_isolation_and_partial_layer_retry(self):
        tile = {'x': 1, 'y': 2, 'collection': {'type': 'FeatureCollection', 'features': []}, 'missingLayers': ['surfaces']}
        with patch.object(amap_map.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({'tiles': [tile]}).encode())) as run:
            first = self.client.post('/api/amap-app/map', json={'level': 12, 'tiles': [[1, 2]]})
            self.assertEqual(first.json['data']['tiles'][0]['missingLayers'], ['surfaces'])
            self.client.post('/api/amap-app/map', json={'level': 12, 'tiles': [[1, 2]]})
            self.assertEqual(run.call_count, 2)
            self.client.post('/api/amap-app/map', json={'level': 14, 'tiles': [[1, 2]]})
            self.assertEqual(run.call_count, 3)
            self.assertEqual(self.disk.status()['count'], 0)
            self.assertEqual(self.client.post('/api/amap-app/map', json={'level': 12, 'tiles': [[4096, 0]]}).status_code, 400)
            self.assertEqual(self.client.post('/api/amap-app/map', json={'level': 13, 'tiles': [[1, 2]]}).status_code, 400)

    def test_busy_worker_returns_pending_and_cached_tiles_remain_available(self):
        tile = {'level': 3, 'x': 6, 'y': 2, 'surfaces': []}
        self.disk.write((3, 6, 2), tile, self.disk.status()['generation'])
        with amap_map.LOCK, patch.object(amap_map.subprocess, 'run') as run:
            cached = self.client.post('/api/amap-app/map', json={'level': 3, 'tiles': [[6, 2]]})
            self.assertEqual(cached.status_code, 200)
            self.assertEqual(cached.json['data']['tiles'], [tile])
            pending = self.client.post('/api/amap-app/map', json={'level': 6, 'tiles': [[52, 17]]})
            self.assertEqual(pending.status_code, 202)
            self.assertTrue(pending.json['data']['pending'])
            run.assert_not_called()
        ready = {'level': 6, 'x': 52, 'y': 17, 'collection': {'type': 'FeatureCollection', 'features': []}}
        with patch.object(amap_map.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({'tiles': [ready]}).encode())) as run:
            response = self.client.post('/api/amap-app/map', json={'level': 6, 'tiles': [[52, 17]]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['data']['tiles'], [ready])
            self.assertEqual(run.call_count, 1)

    def test_missing_dependency_logged_without_raw_stderr(self):
        error = amap_map.subprocess.CalledProcessError(1, ['helper'], stderr=b"private signed-url\nModuleNotFoundError: No module named 'unicorn'")
        with patch.object(amap_map.subprocess, 'run', side_effect=error), self.assertLogs(self.app.logger, level='ERROR') as logs:
            response = self.client.post('/api/amap-app/map', json={'tiles': [[1, 2]]})
        self.assertEqual(response.status_code, 502)
        self.assertIn('missing_module=unicorn', ' '.join(logs.output))
        self.assertNotIn('signed-url', ' '.join(logs.output) + response.text)

    def test_helper_reason_in_server_logs_only(self):
        result = {'error': 'map-unavailable', 'diagnostic': {'reason': 'missing-runtime'}}
        with patch.object(amap_map.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(result).encode())), self.assertLogs(self.app.logger, level='ERROR') as logs:
            response = self.client.post('/api/amap-app/map', json={'tiles': [[1, 2]]})
        self.assertEqual(response.status_code, 502)
        self.assertIn('missing-runtime', ' '.join(logs.output))
        self.assertNotIn('missing-runtime', response.text)

    def test_helper_failure_is_sanitized(self):
        with patch.object(amap_map.subprocess, 'run', side_effect=OSError('private upstream details')):
            response = self.client.post('/api/amap-app/map', json={'tiles': [[1, 2]]})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('private', response.text)


if __name__ == '__main__':
    unittest.main()
