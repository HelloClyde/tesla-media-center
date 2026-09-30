import unittest
from unittest.mock import Mock
from flask import Flask
from ffvideo.amap_inertial import add_amap_inertial_routes


class InertialTransportTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.engine = Mock()
        self.engine.consume_batch.return_value = {'state': 2, 'output': None}
        self.factory = Mock(return_value=self.engine)
        self.app.config['AMAP_VDR_FACTORY'] = self.factory
        add_amap_inertial_routes(self.app)
        self.client = self.login()

    def login(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['last_visit'] = 1
        return client

    def create(self):
        response = self.client.post('/api/amap-app/inertial/sessions')
        return '/api/amap-app/inertial/sessions/' + response.json['data']['id']

    def test_auth_and_owner_isolation(self):
        self.assertEqual(self.app.test_client().post('/api/amap-app/inertial/sessions').json['status'], 'need_login')
        self.factory.assert_not_called()
        path = self.create()
        self.assertEqual(self.login().delete(path).status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 200)
        self.assertEqual(self.client.delete(path).status_code, 404)

    def test_retries_do_not_duplicate_integration(self):
        path = self.create()
        payload = {'sequence': 0, 'samples': [{'timestamp': 1000}]}
        first = self.client.post(path, json=payload)
        repeated = self.client.post(path, json=payload)
        self.assertEqual(first.json, repeated.json)
        self.engine.consume_batch.assert_called_once()
        payload['samples'][0]['timestamp'] = 1001
        self.assertEqual(self.client.post(path, json=payload).status_code, 409)
        payload['sequence'] = 2
        self.assertEqual(self.client.post(path, json=payload).status_code, 409)

    def test_unconfigured_factory_and_failed_session(self):
        path = self.create()
        self.engine.consume_batch.side_effect = ValueError('invalid sample')
        payload = {'sequence': 0, 'samples': [{}]}
        self.assertEqual(self.client.post(path, json=payload).status_code, 400)
        self.assertEqual(self.client.post(path, json=payload).status_code, 404)
        self.app.config.pop('AMAP_VDR_FACTORY')
        self.assertFalse(self.client.get('/api/amap-app/inertial/status').json['data']['available'])
        self.assertEqual(self.client.post('/api/amap-app/inertial/sessions').status_code, 503)

    def test_failed_replacement_preserves_existing_session(self):
        path = self.create()
        self.factory.side_effect = RuntimeError('internal factory detail')
        with self.assertLogs(self.app.logger, level='ERROR'):
            response = self.client.post('/api/amap-app/inertial/sessions')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('internal factory detail', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response = self.client.post(path, json={'sequence': 0, 'samples': [{}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_input_format_mismatch_preserves_existing_session(self):
        path = self.create()
        response = self.client.post('/api/amap-app/inertial/sessions', json={'format': 'browser'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post(path, json={'sequence': 0, 'samples': [{}]}).status_code, 200)
        self.engine.input_format = 'browser'
        response = self.client.post('/api/amap-app/inertial/sessions', json={'format': 'browser'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data']['format'], 'browser')


if __name__ == '__main__':
    unittest.main()
