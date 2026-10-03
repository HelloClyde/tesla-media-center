import base64
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
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
            {'start': 0, 'end': 1, 'road': '示例路', 'serviceArea': '长安服务区', 'actionCode': 3,
             'assistantActionCode': 6, 'private': 'hidden'}],
            'distance': 85, 'labels': ['方案一'], 'breaks': [], 'key': 'hidden',
            'duration': 8460, 'tolls': 71, 'tollCurrency': 'CNY',
            'trafficLights': [[116.401, 39.9]], 'trafficLightCount': 1}
        data = {'state': 'ready', 'routes': [route], 'secret': 'hidden'}
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            result = amap_app.invoke_helper(self.payload)
        self.assertTrue(result['navigationAvailable'])
        self.assertNotIn('hidden', json.dumps(result))
        self.assertEqual(result['routes'][0]['duration'], 8460)
        self.assertEqual(result['routes'][0]['tolls'], 71)
        self.assertEqual(result['routes'][0]['trafficLightCount'], 1)
        self.assertEqual(result['routes'][0]['trafficLights'], [[116.401, 39.9]])
        self.assertEqual(result['routes'][0]['steps'][0]['serviceArea'], '长安服务区')
        self.assertEqual(result['routes'][0]['steps'][0]['maneuver'], 'fork-middle')
        self.assertNotIn('actionCode', result['routes'][0]['steps'][0])
        self.assertNotIn('assistantActionCode', result['routes'][0]['steps'][0])
        for code, expected in ((7, 'fork-right'), (8, 'fork-left')):
            route['steps'][0]['assistantActionCode'] = code
            with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
                self.assertEqual(amap_app.invoke_helper(self.payload)['routes'][0]['steps'][0]['maneuver'], expected)
        route['steps'][0]['assistantActionCode'] = 0
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            self.assertEqual(amap_app.invoke_helper(self.payload)['routes'][0]['steps'][0]['maneuver'], 'bear-left')
        route['steps'][0]['actionCode'] = 4
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            self.assertEqual(amap_app.invoke_helper(self.payload)['routes'][0]['steps'][0]['maneuver'], 'bear-right')
        route['steps'][0]['serviceArea'] = '某某收费站'
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            with self.assertRaises(ValueError):
                amap_app.invoke_helper(self.payload)
        route['steps'][0]['serviceArea'] = '长安服务区'
        route.update(duration=-1, tolls=True)
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            invalid = amap_app.invoke_helper(self.payload)['routes'][0]
        self.assertIsNone(invalid['duration'])
        self.assertIsNone(invalid['tolls'])
        route['trafficLightCount'] = 2
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            with self.assertRaises(ValueError):
                amap_app.invoke_helper(self.payload)
        route['trafficLightCount'] = 1
        route['steps'][0]['end'] = 10
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(data).encode())):
            with self.assertRaises(ValueError):
                amap_app.invoke_helper(self.payload)

    def test_route_endpoint_requires_login(self):
        with patch.object(amap_app, 'invoke_helper') as helper:
            self.assertEqual(self.app.test_client().post('/api/amap-app/route', json=self.payload).json['status'], 'need_login')
            helper.assert_not_called()

    def test_only_verified_bounded_speed_sections_reach_navigation(self):
        route = {'path': [[120, 30], [120.01, 30.01]],
                 'steps': [{'start': 0, 'end': 1, 'road': '道路'}],
                 'distance': 1500, 'labels': [],
                 'speedLimits': [{'start': 100, 'end': 500, 'limit': 80, 'private': 'hidden'}],
                 'speedCameras': [{'at': 1000, 'type': 7, 'speed': [80, 255], 'private': 'hidden'}]}
        result = {'state': 'ready', 'routes': [route]}
        with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(result).encode())):
            cleaned = amap_app.invoke_helper(self.payload)
        self.assertEqual(cleaned['routes'][0]['speedLimits'], [{'start': 100, 'end': 500, 'limit': 80}])
        self.assertEqual(cleaned['routes'][0]['speedCameras'], [{'at': 1000, 'type': 7, 'speed': [80, 255]}])
        self.assertNotIn('hidden', json.dumps(cleaned))
        for invalid in (0, 161, 80.5, True):
            route['speedLimits'][0]['limit'] = invalid
            with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(result).encode())):
                with self.assertRaises(ValueError):
                    amap_app.invoke_helper(self.payload)
        route['speedLimits'][0]['limit'] = 80
        for invalid in ([255], [0], [80.5], [True], [161]):
            route['speedCameras'][0]['speed'] = invalid
            with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(result).encode())):
                with self.assertRaises(ValueError):
                    amap_app.invoke_helper(self.payload)

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

    def test_route_session_is_opaque_and_live_signals_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(amap_app, 'SESSION_DIR', Path(directory)):
                route = {'state': 'ready', 'rawRoute': base64.b64encode(b'route response').decode(),
                         'routes': [{'path': [[120, 30], [120.01, 30.01]],
                                     'steps': [{'start': 0, 'end': 1, 'road': '路'}],
                                     'distance': 1500, 'labels': [], 'trafficLights': [],
                                     'trafficLightCount': 0}]}
                live = {'state': 'ready', 'updatedAt': time.time() * 1000,
                        'lights': [{'point': [120.005, 30.005], 'phases': [
                            {'start': 1700000000, 'end': 1700000020, 'color': 'red'}],
                            'nodeId': 'hidden', 'linkId': 'hidden'}]}
                with patch.object(amap_app.subprocess, 'run', side_effect=[
                    SimpleNamespace(stdout=json.dumps(route).encode()),
                    SimpleNamespace(stdout=json.dumps(live).encode())]):
                    planned = self.client.post('/api/amap-app/route', json=self.payload)
                    token = planned.json['data']['routeToken']
                    self.assertNotIn('rawRoute', planned.get_data(as_text=True))
                    self.assertEqual(amap_app.load_route_session(token), route['rawRoute'])
                    signals = self.client.post('/api/amap-app/traffic-signals', json={
                        'routeToken': token, 'routeIndex': 0, 'position': [120, 30]})
                self.assertEqual(signals.status_code, 200)
                self.assertEqual(signals.json['data']['lights'][0]['phases'][0]['color'], 'red')
                self.assertNotIn('hidden', signals.get_data(as_text=True))
                self.assertEqual(self.client.post('/api/amap-app/traffic-signals', json={
                    'routeToken': '../other', 'routeIndex': 0, 'position': [120, 30]}).status_code, 400)

    def test_junction_image_uses_route_session_and_exposes_only_picture(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(amap_app, 'SESSION_DIR', Path(directory)):
                token = amap_app.save_route_session(base64.b64encode(b'route response').decode())
                picture = {'state': 'ready', 'width': 500, 'height': 320,
                           'roadJpeg': base64.b64encode(b'\xff\xd8\xffexample\xff\xd9').decode(),
                           'arrowPng': base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode(),
                           'naviId': 'private'}
                with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(
                        stdout=json.dumps(picture).encode())):
                    response = self.client.post('/api/amap-app/junction-image', json={
                        'routeToken': token, 'routeIndex': 0, 'stepIndex': 4})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['data']['width'], 500)
                self.assertNotIn('private', response.get_data(as_text=True))
                with patch.object(amap_app, 'invoke_helper') as helper:
                    invalid = self.client.post('/api/amap-app/junction-image', json={
                        'routeToken': token, 'routeIndex': 0, 'stepIndex': True})
                    self.assertEqual(invalid.status_code, 400)
                    helper.assert_not_called()

    def test_navigation_events_use_route_session_and_reject_unbounded_data(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(amap_app, 'SESSION_DIR', Path(directory)):
                token = amap_app.save_route_session(base64.b64encode(b'route response').decode())
                events = {'state': 'ready', 'speedSigns': [
                    {'at': 140.5, 'limit': 80, 'private': 'hidden'},
                    {'at': 450, 'limit': 60}],
                    'speedLimits': [{'start': 100, 'end': 420, 'limit': 80, 'private': 'hidden'}],
                    'speedCameras': [{'at': 400, 'type': 7, 'speed': [80, 255], 'private': 'hidden'}]}
                with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(
                        stdout=json.dumps(events).encode())):
                    response = self.client.post('/api/amap-app/navigation-events', json={
                        'routeToken': token, 'routeIndex': 0})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['data']['speedSigns'], [
                    {'at': 140.5, 'limit': 80}, {'at': 450, 'limit': 60}])
                self.assertEqual(response.json['data']['speedLimits'], [
                    {'start': 100, 'end': 420, 'limit': 80}])
                self.assertEqual(response.json['data']['speedCameras'], [
                    {'at': 400, 'type': 7, 'speed': [80, 255]}])
                self.assertNotIn('hidden', response.get_data(as_text=True))
                with patch.object(amap_app, 'invoke_helper') as helper:
                    invalid = self.client.post('/api/amap-app/navigation-events', json={
                        'routeToken': token, 'routeIndex': True})
                    self.assertEqual(invalid.status_code, 400)
                    helper.assert_not_called()
                for bad in ({'at': 450, 'limit': 255}, {'at': 100, 'limit': 60},
                            {'at': 460, 'limit': True}):
                    events['speedSigns'][-1] = bad
                    with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(
                            stdout=json.dumps(events).encode())):
                        with self.assertRaises(ValueError):
                            amap_app.invoke_helper({'action': 'navigation-events'})
                events['speedSigns'][-1] = {'at': 450, 'limit': 60}
                for bad in ({'start': 400, 'end': 100, 'limit': 80},
                            {'start': 100, 'end': 420, 'limit': 255}):
                    events['speedLimits'][0] = bad
                    with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(
                            stdout=json.dumps(events).encode())):
                        with self.assertRaises(ValueError):
                            amap_app.invoke_helper({'action': 'navigation-events'})
                events['speedLimits'][0] = {'start': 100, 'end': 420, 'limit': 80}
                for bad in ({'at': 400, 'type': 8, 'speed': [80]},
                            {'at': 400, 'type': 7, 'speed': [255]}):
                    events['speedCameras'][0] = bad
                    with patch.object(amap_app.subprocess, 'run', return_value=SimpleNamespace(
                            stdout=json.dumps(events).encode())):
                        with self.assertRaises(ValueError):
                            amap_app.invoke_helper({'action': 'navigation-events'})


if __name__ == '__main__':
    unittest.main()
