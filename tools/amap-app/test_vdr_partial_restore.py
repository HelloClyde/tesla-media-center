import unittest
import numpy as np
from vdr_filter import VdrFilter
from vdr_filter_update import CorrectionFilter
from vdr_pose_initialization import initialize_pose


class PartialRestoreTest(unittest.TestCase):
    def test_recovery_retains_position_time_bias_and_observation_history(self):
        original = initialize_pose(1000, 0., 10., (120.,30.,0.),
                                   np.eye(3).tolist(), np.eye(3).tolist(), [.1,.2,.3])
        incoming = initialize_pose(2000, 90., 1., (130.,40.,1.),
                                   np.eye(3).tolist(), np.eye(3).tolist(), [9.,9.,9.])
        original.pose.position = [10.,20.,30.]
        engine = VdrFilter(CorrectionFilter(original, np.eye(21), count=17, calibrate=False),
                           last_timestamp=1500, stationary_rotations=[np.eye(3).tolist()])
        engine.restore_recovery(incoming, np.eye(21)*.4, 0x61,
                                gyro_bias_variance=1e-7, accel_bias_variance=1e-4)
        self.assertEqual(engine.correction.state.pose.position, [10.,20.,30.])
        self.assertEqual(engine.correction.state.pose.gyro_bias, [.1,.2,.3])
        self.assertEqual(engine.last_timestamp,1500)
        self.assertEqual(engine.correction.count,17)
        self.assertEqual(len(engine.stationary_rotations),1)
        self.assertTrue(engine.correction.calibrate)
        np.testing.assert_array_equal(engine.correction.state.pose.rotation,incoming.pose.rotation)


if __name__ == '__main__':
    unittest.main()
