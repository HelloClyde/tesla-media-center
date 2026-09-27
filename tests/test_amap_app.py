import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from ffvideo import amap_app


class AmapAppTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        app.testing = True
        amap_app.add_amap_app_route(app)
        self.app = app
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1
        self.payload = {'origin': [116.3975, 39.9087], 'destination': [116.41, 39.916]}

    def test_login_required_before_helper_or_validation(self):
        with patch.object(amap_app, 'invoke_helper') as helper:
            anonymous = self.app.test_client()
            self.assertEqual(anonymous.get('/api/amap-app/status').json['status'], 'need_login')
            self.assertEqual(anonymous.post('/api/amap-app/probe', json={}).json['status'], 'need_login')
            helper.assert_not_called()

    def test_ready_route_allowlist_and_geometry_validation(self):
        route = {'path': [[116.4, 39.9], [116.401, 39.9]], 'steps': [
            {'start': 0, 'end': 1, 'road': '示例路', 'private': 'hidden'}],
            'distance': 85, 'labels': ['方案一'], 'breaks': [], 'key': 'hidden'}
        data = {'state': 'ready', 'routes': [route], 'secret': 'hidden'}
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            result = amap_app.invoke_helper(self.payload)
        self.assertTrue(result['navigationAvailable'])
        self.assertNotIn('hidden', json.dumps(result))
        route['steps'][0]['end'] = 10
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            with self.assertRaises(ValueError):
                amap_app.invoke_helper(self.payload)

    def test_route_endpoint_requires_login(self):
        with patch.object(amap_app, 'invoke_helper') as helper:
            self.assertEqual(self.app.test_client().post('/api/amap-app/route', json=self.payload).json['status'], 'need_login')
            helper.assert_not_called()

    def test_invalid_coordinates_never_reach_upstream(self):
        bad = [None, [], [1], [True, 1], ['1', 1], [181, 0], [0, 91], [float('nan'), 0],
               [float('inf'), 0], [10**400, 0]]
        with patch.object(amap_app, 'invoke_helper') as helper:
            for origin in bad:
                response = self.client.post('/api/amap-app/probe', json={**self.payload, 'origin': origin})
                self.assertEqual(response.status_code, 400, str(origin))
            helper.assert_not_called()

    def test_identical_rounded_points(self):
        response = self.client.post('/api/amap-app/probe', json={'origin': [1, 2], 'destination': [1.00000001, 2]})
        self.assertEqual(response.status_code, 400)

    def test_non_object_and_oversized_requests(self):
        self.assertEqual(self.client.post('/api/amap-app/probe', json=[]).status_code, 400)
        self.assertEqual(self.client.post('/api/amap-app/probe', json={'extra': 'x'*5000}).status_code, 413)

    def test_only_coordinates_forwarded(self):
        with patch.object(amap_app, 'invoke_helper', return_value={'state': 'unsupported-response', 'navigationAvailable': False}) as helper:
            response = self.client.post('/api/amap-app/probe', json={**self.payload, 'url': 'http://localhost', 'command': 'bad'})
            helper.assert_called_once_with(self.payload)
            self.assertFalse(response.json['data']['navigationAvailable'])

    def test_timeout_releases_busy_lock_and_hides_detail(self):
        with patch.object(amap_app, 'invoke_helper', side_effect=subprocess.TimeoutExpired('secret-url', 40)):
            response = self.client.post('/api/amap-app/probe', json=self.payload)
        self.assertEqual(response.status_code, 504)
        self.assertNotIn('secret', response.get_data(as_text=True))
        self.assertFalse(amap_app.PROBE_LOCK.locked())

    def test_concurrent_requests_rejected(self):
        amap_app.PROBE_LOCK.acquire()
        try:
            with patch.object(amap_app, 'invoke_helper') as helper:
                self.assertEqual(self.client.post('/api/amap-app/probe', json=self.payload).status_code, 429)
                helper.assert_not_called()
        finally:
            amap_app.PROBE_LOCK.release()

    def test_missing_adapter_status_is_unavailable(self):
        with patch.object(amap_app, 'invoke_helper', side_effect=OSError('local-path')):
            response = self.client.get('/api/amap-app/status')
            self.assertEqual(response.json['data'], {'state': 'unavailable', 'navigationAvailable': False})

    def test_adapter_cannot_claim_navigation_ready_or_leak_material(self):
        data = {'state': 'partial', 'navigationAvailable': True, 'key': 'private', 'polyline': [[1, 2]],
                'routes': [{'labels': ['候选'], 'roads': ['道路'], 'distance': 123}],
                'checks': {'geometryCandidates': 2, 'geometryTotal': 2, 'framing': True, 'duration': True}}
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            result = amap_app.invoke_helper(self.payload)
        self.assertFalse(result['navigationAvailable'])
        self.assertFalse(result['checks']['completeGeometry'])
        self.assertFalse(result['checks']['duration'])
        for field in ('key', 'polyline', 'distance', 'private'):
            # distance may only occur in the fixed checks as False.
            if field == 'distance':
                self.assertNotIn(field, result['routes'][0])
            else:
                self.assertNotIn(field, json.dumps(result))

    def test_bad_adapter_contract_is_rejected(self):
        for data in [[], {'state': 'ready'}, {'state': 'partial', 'routes': [{'roads': [1]}]}]:
            with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
                with self.assertRaises(ValueError):
                    amap_app.invoke_helper(self.payload)


if __name__ == '__main__':
    unittest.main()
