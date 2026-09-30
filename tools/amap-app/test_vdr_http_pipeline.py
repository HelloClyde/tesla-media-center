"""Real translated engine behind Flask routes; synthetic installation/profile.

This exercises the HTTP handler, not a browser or the APK's full manager.
"""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flask import Flask
from ffvideo.amap_inertial import add_amap_inertial_routes
from vdr_browser_input import BrowserInput
from vdr_batch import NativeVdrBatch
from vdr_browser_batch import BrowserVdrBatch
from test_vdr_session import create_session
from test_vdr_batch import sample


class HttpPipelineTest(unittest.TestCase):
    session_factory = staticmethod(create_session)
    browser_input = False

    def test_real_engine_retry_gps_loss_and_recovery(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        session = self.session_factory()
        app.config['AMAP_VDR_FACTORY'] = lambda: (
            BrowserVdrBatch(session, rotation=[[1,0,0],[0,1,0],[0,0,1]],
                acceleration_sign=1, accuracy_to_sigma=1, maximum_gap=80)
            if self.browser_input else NativeVdrBatch(session))
        add_amap_inertial_routes(app)
        client = app.test_client()
        with client.session_transaction() as auth:
            auth['last_visit'] = 1
        opened = client.post('/api/amap-app/inertial/sessions',
                             json={'format': 'browser' if self.browser_input else 'native'})
        self.assertEqual(opened.status_code, 200)
        path = '/api/amap-app/inertial/sessions/' + opened.json['data']['id']
        adapter = BrowserInput([[1, 0, 0], [0, 1, 0], [0, 0, 1]], 1, 1)
        results = []
        for sequence, start in enumerate(range(0, 1600, 100)):
            batch = []
            for step in range(start, start + 100):
                native = sample(step)
                # Simulated vertical road vibration distinguishes this moving
                # fixture from the perfectly stationary IMU used by unit tests.
                # Apply along gravity, with zero mean, not a fake forward force.
                vibration = .12 * math.sin(2 * math.pi * 2 * step * .04)
                native['acceleration'] = [v * (1 + vibration / 9.80665)
                                          for v in native['acceleration']]
                fix = native.get('gps') if not 1100 <= step < 1400 else None
                gps = None if fix is None else dict(elapsed=fix['timestamp']-1,
                    longitude=fix['longitude'], latitude=fix['latitude'], altitude=fix['altitude'],
                    speed=fix['speed'], accuracy=fix['position_sigma'], heading=90)
                browser_sample = dict(elapsed=native['timestamp']-1,
                    acceleration=native['acceleration'], angularVelocity=native['gyro'])
                if self.browser_input:
                    if gps is not None:
                        browser_sample['gps'] = gps
                    batch.append(browser_sample)
                else:
                    batch.append(adapter.convert(browser_sample, gps))
            body = dict(sequence=sequence, samples=batch)
            response = client.post(path, json=body)
            self.assertEqual(response.status_code, 200, response.json)
            before = (session.producer.last_timestamp, len(session.history), session.manager.state)
            retry = client.post(path, json=body)
            self.assertEqual(retry.json, response.json)
            self.assertEqual(before, (session.producer.last_timestamp, len(session.history), session.manager.state))
            result = response.json['data']['result']
            self.assertEqual(result['accepted'], 100)
            self.assertEqual(result['timestamp'], 1000 + (start+99)*40)
            results.append(result)
        for result in results[10:]:
            self.assertIsNotNone(result['output'], result)
            self.assertTrue(math.isfinite(result['output']['longitude']))
        self.assertTrue(any(result['output']['missing_fix'] for result in results[11:14]))
        self.assertFalse(results[-1]['output']['missing_fix'])
        # This fixture travels east at approximately 7.2 m/s. Verify that an
        # output is not merely a repeated last fix during the twelve-second gap.
        scale = math.cos(math.radians(30)) * 111319.49079327358
        travelled = (results[13]['output']['longitude'] - results[10]['output']['longitude']) * scale
        self.assertGreater(travelled, 60)
        self.assertLess(travelled, 110)
        final = results[-1]['output']
        expected_longitude = 120 + (final['timestamp'] - 1000) / 40 * .000003
        self.assertLess(abs(final['longitude'] - expected_longitude) * scale, 10)
        self.assertEqual(client.delete(path).status_code, 200)
        self.assertEqual(client.post(path, json=body).status_code, 404)


class BrowserHttpPipelineTest(HttpPipelineTest):
    browser_input = True


if __name__ == '__main__':
    unittest.main()
