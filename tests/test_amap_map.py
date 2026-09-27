import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from ffvideo import amap_map


class MapTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        amap_map.add_amap_map_route(app)
        self.app, self.client = app, app.test_client()
        amap_map.CACHE.clear()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1

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
            self.assertNotIn((14, 2, 2), amap_map.CACHE)

    def test_zoom_cache_isolation_and_partial_layer_retry(self):
        tile = {'x': 1, 'y': 2, 'collection': {'type': 'FeatureCollection', 'features': []}, 'missingLayers': ['surfaces']}
        with patch.object(amap_map.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({'tiles': [tile]}).encode())) as run:
            first = self.client.post('/api/amap-app/map', json={'level': 12, 'tiles': [[1, 2]]})
            self.assertEqual(first.json['data']['tiles'][0]['missingLayers'], ['surfaces'])
            self.client.post('/api/amap-app/map', json={'level': 12, 'tiles': [[1, 2]]})
            self.assertEqual(run.call_count, 2)
            self.client.post('/api/amap-app/map', json={'level': 14, 'tiles': [[1, 2]]})
            self.assertEqual(run.call_count, 3)
            self.assertIn((12, 1, 2), amap_map.CACHE)
            self.assertIn((14, 1, 2), amap_map.CACHE)
            self.assertEqual(self.client.post('/api/amap-app/map', json={'level': 12, 'tiles': [[4096, 0]]}).status_code, 400)
            self.assertEqual(self.client.post('/api/amap-app/map', json={'level': 13, 'tiles': [[1, 2]]}).status_code, 400)

    def test_busy_worker_returns_pending_and_cached_tiles_remain_available(self):
        tile = {'level': 3, 'x': 6, 'y': 2, 'surfaces': []}
        amap_map.CACHE[(3, 6, 2)] = (time.monotonic(), tile)
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
