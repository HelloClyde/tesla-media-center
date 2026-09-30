import unittest
from vdr_browser_input import BrowserInput
from vdr_batch import NativeVdrBatch
from test_vdr_session import create_session
from test_vdr_batch import sample

IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


class BrowserInputTest(unittest.TestCase):
    def test_heading_clock_and_units(self):
        for heading, direction in [(0, 90), (90, 0), (180, 270), (270, 180), (None, -1)]:
            adapter = BrowserInput(IDENTITY, 1, .5)
            result = adapter.convert(dict(elapsed=100.8, angularVelocity=[1, 2, 3],
                acceleration=[4, 5, 6]), dict(elapsed=80.2, longitude=120, latitude=30,
                altitude=5, speed=10, accuracy=4, heading=heading))
            self.assertEqual(result['timestamp'], 101)
            self.assertEqual(result['gps']['timestamp'], 81)
            self.assertEqual(result['gps']['direction'], direction)
            self.assertEqual(result['gps']['position_sigma'], 2)
            self.assertEqual(result['gyro'], [1, 2, 3])

    def test_installation_and_missing_values(self):
        with self.assertRaises(ValueError):
            BrowserInput([[1, 0, 0], [0, 1, 0], [0, 0, -1]], 1, 1)
        adapter = BrowserInput([[0, -1, 0], [1, 0, 0], [0, 0, 1]], -1, 1)
        incoming = dict(elapsed=0, angularVelocity=[1, 2, 3], acceleration=[4, 5, 6])
        with self.assertRaises(ValueError):
            adapter.convert(incoming, dict(elapsed=0, longitude=120, latitude=30,
                altitude=None, speed=10, accuracy=2, heading=0))
        self.assertEqual(adapter.last_timestamp, -1)
        result = adapter.convert(incoming)
        self.assertEqual(result['gyro'], [-2, 1, 3])
        self.assertEqual(result['acceleration'], [5, -4, -6])
        with self.assertRaises(ValueError):
            adapter.convert(incoming)

    def test_browser_shaped_stream_reaches_real_session(self):
        adapter = BrowserInput(IDENTITY, 1, 1)
        engine = NativeVdrBatch(create_session())
        for start in range(0, 1100, 100):
            batch = []
            for step in range(start, start + 100):
                native = sample(step)
                fix = native.get('gps')
                browser_fix = None if fix is None else dict(elapsed=fix['timestamp']-1,
                    longitude=fix['longitude'], latitude=fix['latitude'], altitude=fix['altitude'],
                    speed=fix['speed'], accuracy=fix['position_sigma'], heading=90)
                batch.append(adapter.convert(dict(elapsed=native['timestamp']-1,
                    acceleration=native['acceleration'], angularVelocity=native['gyro']), browser_fix))
            result = engine.consume_batch(batch)
        self.assertEqual(result['state'], 8)
        self.assertIsNotNone(result['output'])


if __name__ == '__main__':
    unittest.main()
