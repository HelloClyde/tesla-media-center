import math
import unittest
from unittest.mock import Mock
from test_vdr_session import create_session
from vdr_batch import NativeVdrBatch


def sample(step):
    timestamp = 1000 + step * 40
    result = dict(timestamp=timestamp, gyro=[0., 0., 0.],
                  acceleration=[.2, .3, math.sqrt(9.80665**2 - .13)])
    if step % 25 == 0:
        result['gps'] = dict(timestamp=timestamp, longitude=120. + step * .000003,
                             latitude=30., altitude=0., speed=7.2,
                             direction=0., position_sigma=1.)
    return result


class NativeBatchTest(unittest.TestCase):
    def test_entire_batch_validated_before_integration(self):
        engine = Mock()
        adapter = NativeVdrBatch(engine)
        invalid = sample(1)
        invalid['gyro'][0] = float('nan')
        with self.assertRaises(ValueError):
            adapter.consume_batch([sample(0), invalid])
        engine.push.assert_not_called()
        self.assertEqual(adapter.last_timestamp, -1)

    def test_gps_and_timestamp_validation(self):
        engine = Mock()
        adapter = NativeVdrBatch(engine)
        for field, value in [('timestamp', 1001), ('latitude', 91),
                             ('speed', -1), ('direction', 360),
                             ('position_sigma', -1)]:
            invalid = sample(0)
            invalid['gps'][field] = value
            with self.assertRaises(ValueError):
                adapter.consume_batch([invalid])
        with self.assertRaises(ValueError):
            adapter.consume_batch([sample(1), sample(0)])
        engine.push.assert_not_called()

    def test_continuous_real_session_and_snapshot(self):
        engine = create_session()
        adapter = NativeVdrBatch(engine)
        for start in range(0, 1100, 100):
            result = adapter.consume_batch([sample(i) for i in range(start, start + 100)])
            self.assertEqual(result['accepted'], 100)
        self.assertEqual(result['state'], 8)
        self.assertTrue(math.isfinite(result['output']['longitude']))
        result['output']['longitude'] = -999
        self.assertNotEqual(engine.output['longitude'], -999)
        with self.assertRaises(ValueError):
            adapter.consume_batch([sample(1099)])
        self.assertEqual(adapter.last_timestamp, sample(1099)['timestamp'])


if __name__ == '__main__':
    unittest.main()
