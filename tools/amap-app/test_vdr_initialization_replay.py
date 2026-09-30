import unittest
import numpy as np
from types import SimpleNamespace
from vdr_initialization_history import record_from_window
from vdr_initialization_handoff import initialize_from_windows
from vdr_initialization_replay import ReplayWindow, initialize_and_replay
from vdr_pose_initialization import initialize_pose
from vdr_window_producer import empty_integration
from vdr_observation_dispatch import GpsObservation
from vdr_quality_manager import QualityManager


class InitializationReplayTest(unittest.TestCase):
    def test_replay_with_real_quality_callback_uses_observation_corrections(self):
        manager = QualityManager(dict(means=[0.]*55,scales=[1.]*55,
                                      coefficients=[0.]*55,bias=2.))
        initialized = initialize_pose(1000,0.,10.,(120.,30.,0.),
                                      np.eye(3).tolist(),np.eye(3).tolist(),[0.]*3)
        history=[]
        for timestamp in range(1500,31000,500):
            integrated=empty_integration(timestamp-500)
            for tick in range(timestamp-480,timestamp+1,20):
                integrated.advance(tick,(0.,0.,0.),(0.,0.,9.80665))
            history.append(ReplayWindow(integrated,GpsObservation(),
                {'motion':1,'direction':0.},direction=0.))
        engine=initialize_and_replay(initialized,history,before_predict=manager.before_predict)
        self.assertEqual(engine.last_timestamp,30500)
        self.assertTrue(manager.histories[9].ready)
        self.assertGreater(manager.scores.last_evaluation,1000)
        self.assertEqual(engine.correction.quality_residual.shape,(22,))
        self.assertEqual(engine.correction.quality_residual[0],0.)
        self.assertTrue(np.isfinite(engine.correction.quality_residual).all())

    def test_historical_pose_advances_without_double_integrating_initial_window(self):
        identity = np.eye(3).tolist()
        initialized = initialize_pose(1000, 0., 10., (120., 30., 0.),
                                      identity, identity, (0., 0., 0.))
        history = []
        for timestamp in range(500, 3500, 500):
            integrated = empty_integration(timestamp - 500)
            for time in range(timestamp - 480, timestamp + 1, 20):
                integrated.advance(time, (0., 0., 0.), (0., 0., 9.80665))
            history.append(ReplayWindow(integrated, GpsObservation(),
                                        {'calibration_state': 0, 'motion': 1}))
        predicted = []
        engine = initialize_and_replay(initialized, history,
                                      before_predict=lambda _, w: predicted.append(w.integrated.timestamp))
        self.assertEqual(predicted, [1500, 2000, 2500, 3000])
        self.assertEqual(engine.last_timestamp, 3000)
        # Two seconds at10m/s, not2.5s from replaying the initial window twice.
        np.testing.assert_allclose(engine.correction.state.pose.position[:2], [20., 0.], atol=1e-8)
        coordinates = engine.correction.state.frame.unproject(*engine.correction.state.pose.position)
        self.assertGreater(coordinates[0], 120.)
        self.assertAlmostEqual(coordinates[1], 30.)
        self.assertTrue(np.isfinite(engine.correction.covariance).all())

    def test_history_handoff_resets_then_replays_to_current_position(self):
        records, history = [], []
        for timestamp in range(500, 3500, 500):
            integrated = empty_integration(timestamp - 500)
            for time in range(timestamp - 480, timestamp + 1, 20):
                integrated.advance(time, (0., 0., 0.), (0., 0., 9.80665))
            current = SimpleNamespace(integrated=integrated, direction=0.,
                quality=0 if timestamp == 500 else 1,
                gps=SimpleNamespace(longitude=120., latitude=30., altitude=0., speed=10.),
                preferred=np.eye(3).tolist(), fallback=np.eye(3).tolist(),
                gyro_bias=[0., 0., 0.])
            records.append(record_from_window(current))
            history.append(ReplayWindow(integrated, GpsObservation(),
                {'calibration_state': 0, 'motion': 1}))
        events = []
        result = initialize_from_windows(records, history, current,
            can_replay=lambda timestamp: timestamp >= 1000,
            reset_manager=lambda: events.append('reset'),
            before_predict=lambda engine, window: events.append(window.integrated.timestamp))
        self.assertEqual(events, ['reset', 1500, 2000, 2500, 3000])
        self.assertEqual((result.initial_timestamp, result.state), (1000, 16))
        self.assertEqual(result.engine.last_timestamp, 3000)
        np.testing.assert_allclose(result.engine.correction.state.pose.position[:2], [20., 0.], atol=1e-8)
        # Snapshots must not alias later publication state.
        current.gyro_bias[0] = 9.
        self.assertEqual(records[-1].gyro_bias[0], 0.)
        current.quality = 0
        events.clear()
        self.assertIsNone(initialize_from_windows(records, history, current,
            can_replay=lambda timestamp: True, reset_manager=lambda: events.append('reset'),
            before_predict=lambda *args: events.append('predict')))
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
