import unittest
from types import SimpleNamespace
import numpy as np
from vdr_state_controller import StateController, StateConfiguration
from vdr_state_transition import ManagerState
from vdr_initialization_history import record_from_window
from vdr_initialization_replay import ReplayWindow
from vdr_filter_manager import FilterManager
from vdr_quality_manager import QualityManager
from vdr_observation_dispatch import GpsObservation
from vdr_window_observation import FilterGps, WindowObservation
from vdr_window_producer import empty_integration
from vdr_gap_policy import GapPolicy


class StateControllerTest(unittest.TestCase):
    def test_start_initialize_lose_quality_and_recover_real_filter(self):
        self.exercise(16)

    def test_fallback_recovery_then_upgrade_to_aligned(self):
        self.exercise(8)

    def exercise(self, running_state):
        manager = ManagerState(2, 1000, 0, 1000)
        quality = QualityManager(dict(means=[0.]*55, scales=[1.]*55,
                                      coefficients=[0.]*55, bias=0.))
        records, history, transitions = [], [], []

        def transition(state, timestamp, reason, forced):
            manager.transition(state, timestamp, reason, forced,
                lambda *args: transitions.append(args), [], lambda *_: None)

        config = StateConfiguration(False, True, True, True, 10000, 5., False, .01, .1)
        controller = StateController(manager, records, history, quality, config,
            can_replay=lambda t: any(w.integrated.timestamp == t for w in history),
            transition=transition,
            notify_reinitialized=lambda *_: None, reset_manager=lambda: None)
        observation = WindowObservation(config=0, flag1=False, flag2=False)
        filters = FilterManager(None, quality, prepare_observation=observation,
            state_handler=controller, gap_handler=GapPolicy(enabled=True),
            bias_publisher=lambda *_: None)

        def feed(timestamp, score):
            integrated = empty_integration(timestamp-500)
            for tick in range(timestamp-480, timestamp+1, 20):
                integrated.advance(tick, (0., 0., 0.), (0., 0., 9.80665))
            gps = FilterGps(timestamp, 120., 30., speed=10., kind=-1)
            window = SimpleNamespace(integrated=integrated, gps=gps, quality=score,
                direction=0., preferred=(np.eye(3) if running_state == 16 else np.full((3,3),1000.)), fallback=np.eye(3),
                gyro_bias=[0.]*3, missing_fix=False, missing_duration=0, motion=1, detail=0)
            records.append(record_from_window(window))
            prepared_gps, options = observation(window)
            history.append(ReplayWindow(integrated, prepared_gps, options))
            filters.before_predict(window)
            filters.predict(window)
            filters.handle_state(window)
            filters.observe(window, SimpleNamespace(integrated=empty_integration()))
            return window

        feed(1500, 20)
        self.assertEqual(manager.state, 4)
        self.assertIsNone(filters.engine)
        feed(2000, 21)
        self.assertEqual(manager.state, running_state)
        self.assertIsNotNone(filters.engine)
        self.assertEqual(filters.engine.last_timestamp, 2000)
        original = filters.engine
        feed(2500, 0)
        self.assertEqual((manager.state, manager.reason), (32, running_state))
        feed(3000, 6)
        self.assertEqual(manager.state, running_state)
        self.assertIs(filters.engine, original)
        self.assertTrue(np.isfinite(filters.engine.correction.covariance).all())
        self.assertTrue(np.isfinite(filters.output.pose.position).all())
        self.assertEqual(len(transitions), 4)
        if running_state == 8:
            running_state = 16
            feed(3500, 7)
            self.assertEqual(manager.state, 16)
            # This fixture's fallback attitude differs by more than 5 degrees;
            # native upgrades by full historical replay, not partial restore.
            self.assertIsNot(filters.engine, original)
            self.assertEqual(transitions[-1][-1], 1)
            self.assertEqual(filters.engine.last_timestamp, 3500)


if __name__ == '__main__':
    unittest.main()
