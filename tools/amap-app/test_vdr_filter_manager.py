import unittest
import numpy as np
from vdr_filter_manager import FilterManager
from vdr_initialization_replay import ReplayWindow, initialize_and_replay
from vdr_pose_initialization import initialize_pose
from vdr_quality_manager import QualityManager
from vdr_observation_dispatch import GpsObservation
from vdr_window_producer import empty_integration


def window(start, end):
    integrated = empty_integration(start)
    for tick in range(start+20, end+1, 20):
        integrated.advance(tick, (0., 0., 0.), (0., 0., 9.80665))
    return ReplayWindow(integrated, GpsObservation(),
                        {'calibration_state': 0, 'motion': 1})


class FilterManagerTest(unittest.TestCase):
    def test_lookahead_does_not_feed_back_into_filter(self):
        quality = QualityManager(dict(means=[0.]*55, scales=[1.]*55,
                                      coefficients=[0.]*55, bias=0.))
        pose = initialize_pose(1000, 0., 10., (120., 30., 0.),
                               np.eye(3).tolist(), np.eye(3).tolist(), [0.]*3)
        engine = initialize_and_replay(pose, [], before_predict=quality.before_predict)
        manager = FilterManager(engine, quality,
            prepare_observation=lambda w: (w.gps, w.observation),
            state_handler=lambda *_: None, gap_handler=lambda *_: None,
            bias_publisher=lambda *_: None)
        first, tail = window(1000, 1500), window(1500, 1700)
        manager.before_predict(first)
        manager.predict(first)
        manager.observe(first, tail)
        np.testing.assert_allclose(manager.state.pose.position[:2], [5., 0.], atol=1e-8)
        np.testing.assert_allclose(manager.output.pose.position[:2], [7., 0.], atol=1e-8)
        self.assertEqual(manager.output_timestamp, 1700)
        second = window(1500, 2000)
        manager.before_predict(second)
        manager.predict(second)
        manager.observe(second, window(2000, 2000))
        np.testing.assert_allclose(manager.state.pose.position[:2], [10., 0.], atol=1e-8)
        np.testing.assert_allclose(manager.output.pose.position[:2], [10., 0.], atol=1e-8)
        manager.output.pose.position[0] = 999
        self.assertAlmostEqual(manager.state.pose.position[0], 10.)
        before = engine.correction.covariance.copy()
        manager.output_covariance[0, 0] = -999
        np.testing.assert_array_equal(engine.correction.covariance, before)


if __name__ == '__main__':
    unittest.main()
