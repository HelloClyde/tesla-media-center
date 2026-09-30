import unittest
import numpy as np
from vdr_initialization_history import (
    InitializationRecord, select_initialization_record, prepare_initialization,
)


class InitializationHistoryTest(unittest.TestCase):
    def test_uses_latest_calibration_with_historical_gps(self):
        unavailable = np.full((3, 3), 10000.)
        old = InitializationRecord(1000, 0., True, 10., (120., 30., 0.),
                                   unavailable, unavailable, [0., 0., 0.])
        latest = InitializationRecord(6000, -1., True, 0., (181., 91., 0.),
                                      unavailable, np.eye(3), [.01, .02, .03])
        pose, state = prepare_initialization([old, latest], lambda _: True,
            current_quality=20, preferred=latest.preferred, fallback=latest.fallback)
        self.assertEqual((pose.timestamp, state), (1000, 8))
        self.assertEqual(pose.frame.longitude, 120.)
        np.testing.assert_allclose(pose.calibration, np.eye(3))
        np.testing.assert_allclose(pose.pose.gyro_bias, latest.gyro_bias)

    def test_scan_stops_at_quality_break_and_skips_unavailable_heading(self):
        def record(timestamp, direction=0, eligible=True):
            return InitializationRecord(timestamp, direction, eligible, 10., (120., 30., 0.),
                                        np.eye(3).tolist(), np.eye(3).tolist(), [0., 0., 0.])
        records = [record(100), record(200, eligible=False), record(300),
                   record(400, -1), record(500), record(600, float('nan')), record(700)]
        checked = []
        def can_replay(timestamp):
            checked.append(timestamp)
            return timestamp != 300
        chosen = select_initialization_record(records, can_replay)
        self.assertEqual(chosen.timestamp, 500)
        self.assertEqual(checked, [700, 500, 300])
        result = prepare_initialization(records, can_replay, current_quality=3,
                                        preferred=[[999.] * 3] * 3, fallback=np.eye(3))
        state, mode = result
        self.assertEqual((state.timestamp, mode), (500, 8))
        np.testing.assert_allclose(state.pose.velocity, [10., 0., 0.])
        self.assertEqual(state.frame.unproject(*state.pose.position), (120., 30., 0.))
        self.assertIsNone(prepare_initialization(records, can_replay, current_quality=0,
                                                preferred=np.eye(3), fallback=np.eye(3)))


if __name__ == '__main__':
    unittest.main()
