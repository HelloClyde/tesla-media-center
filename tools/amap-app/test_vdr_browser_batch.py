import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from vdr_browser_batch import BrowserVdrBatch


def engine(session):
    return BrowserVdrBatch(session, rotation=[[1,0,0],[0,1,0],[0,0,1]],
        acceleration_sign=1, accuracy_to_sigma=1, maximum_gap=80)


def sample(elapsed, gps=False):
    result = dict(elapsed=elapsed, angularVelocity=[0,0,0], acceleration=[.2,.3,9.8])
    if gps:
        result['gps'] = dict(elapsed=elapsed, longitude=120, latitude=30,
            altitude=0, accuracy=1, heading=90, speed=5)
    return result


class BrowserBatchTest(unittest.TestCase):
    def test_pending_gps_waits_for_next_grid_tick_across_batches(self):
        session = Mock(manager=SimpleNamespace(state=2), output=None)
        batch = engine(session)
        result = batch.consume_batch([sample(0), sample(20, True)])
        self.assertEqual(result['integrated'], 1)
        self.assertIsNone(session.push.call_args.args[3])
        batch.consume_batch([sample(40)])
        gps = session.push.call_args.args[3]
        self.assertEqual(gps.timestamp, 21)
        self.assertEqual(gps.direction, 0)
        self.assertEqual(session.push.call_args.args[0], 41)

    def test_bad_tail_does_not_integrate_or_advance_adapter(self):
        session = Mock(manager=SimpleNamespace(state=2), output=None)
        batch = engine(session)
        with self.assertRaises(ValueError):
            batch.consume_batch([sample(0), sample(200)])
        session.push.assert_not_called()
        self.assertEqual(batch.adapter.last_timestamp, -1)
        self.assertEqual(batch.consume_batch([sample(0)])['integrated'], 1)


if __name__ == '__main__':
    unittest.main()
