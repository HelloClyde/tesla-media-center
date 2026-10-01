import unittest
from unittest.mock import Mock, patch

from flask import Flask
from ffvideo import amap_traffic


class AmapTrafficTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        app.testing = True
        amap_traffic.add_amap_traffic_route(app)
        self.app = app
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1
        amap_traffic._cache.clear()

    def test_requires_login_and_web_service_key(self):
        self.assertEqual(self.app.test_client().post('/api/amap-app/traffic', json={'center': [116.4, 39.9]}).json['status'], 'need_login')
        with patch.object(amap_traffic, 'get_config_by_key', return_value=None), patch.dict(amap_traffic.os.environ, {}, clear=True):
            response = self.client.post('/api/amap-app/traffic', json={'center': [116.4, 39.9]})
        self.assertEqual(response.status_code, 409)

    def test_bounds_and_sanitized_live_roads_with_cache(self):
        self.assertEqual(self.client.post('/api/amap-app/traffic', json={'center': [0, 0]}).status_code, 400)
        upstream = Mock()
        upstream.json.return_value = {'status': '1', 'trafficinfo': {'roads': [
            {'status': '3', 'polyline': '116.40,39.90;116.41,39.91', 'name': '测试路', 'secret': 'not exposed'},
            {'status': '0', 'polyline': '116.4,39.9;116.5,39.9'},
        ]}}
        with patch.object(amap_traffic, 'get_config_by_key', return_value='test-key'), patch.object(amap_traffic.requests, 'get', return_value=upstream) as get:
            first = self.client.post('/api/amap-app/traffic', json={'center': [116.4, 39.9]})
            second = self.client.post('/api/amap-app/traffic', json={'center': [116.4, 39.9]})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json['data']['roads'], [{'status': 3, 'path': [[116.4, 39.9], [116.41, 39.91]], 'name': '测试路'}])
        self.assertEqual(second.json['data'], first.json['data'])
        get.assert_called_once()
        self.assertNotIn('test-key', str(first.json))


if __name__ == '__main__':
    unittest.main()
