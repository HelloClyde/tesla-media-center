"""Continuous producer/observers/state/filter/output integration.

Synthetic native-frame samples; root notification/reset auxiliary hooks are
explicit test stubs. This does not assert production/browser parity.
"""
import copy
import unittest
import numpy as np
from vdr_window_producer import WindowProducer
from vdr_prepared_window import prepare_window, empty_gps
from vdr_window_lifecycle import WindowLifecycle
from vdr_motion_observer import MotionObserver
from vdr_calibration_observer import CalibrationObserver
from vdr_orientation_quality import OrientationQualityObserver
from vdr_direction_observer import DirectionObserver
from vdr_state_transition import ManagerState
from vdr_state_controller import StateConfiguration, StateController
from vdr_quality_manager import QualityManager
from vdr_filter_manager import FilterManager
from vdr_gap_policy import GapPolicy
from vdr_window_observation import WindowObservation, FilterGps
from vdr_initialization_replay import ReplayWindow
from vdr_output_status import OutputStatus


class SessionPipelineTest(unittest.TestCase):
    def test_raw_paired_samples_initialize_and_publish_without_manual_pose(self):
        state = ManagerState(1, -1, 0, -1)
        observers = [OrientationQualityObserver(), DirectionObserver(),
                     MotionObserver(), CalibrationObserver()]
        quality = QualityManager(dict(means=[0.]*55, scales=[1.]*55,
                                      coefficients=[0.]*55, bias=0.))
        records, history, outputs, transitions = [], [], [], []
        observation = WindowObservation(config=0, flag1=False, flag2=False)

        def transition(new, timestamp, reason, forced):
            state.transition(new, timestamp, reason, forced,
                lambda *args: transitions.append(args),
                [observer.transition for observer in observers], lambda *_: None)

        controller = StateController(state, records, history, quality,
            StateConfiguration(False, True, True, True, 10000, 5., False, .01, .1),
            can_replay=lambda t: any(w.integrated.timestamp == t for w in history),
            transition=transition, notify_reinitialized=lambda *_: None,
            reset_manager=lambda: None)
        filters = FilterManager(None, quality, prepare_observation=observation,
            state_handler=controller, gap_handler=GapPolicy(enabled=False),
            bias_publisher=lambda *_: None)
        producer = WindowProducer()
        status = OutputStatus()

        def retain(window):
            gps, options = observation(window)
            history.append(ReplayWindow(copy.deepcopy(window.integrated), gps,
                                         options, direction=window.direction))

        def publish(timestamp, window):
            if status.active:
                pose = filters.output
                outputs.append((timestamp, pose.frame.unproject(*pose.pose.position)))

        lifecycle = WindowLifecycle(manager=state, observers=observers, records=records,
            filter_manager=filters, transition=transition, observer_tail=lambda *_: None,
            empty_gps_factory=empty_gps, bias_feedback=producer.feedback_bias,
            retain_window=retain, output_status=lambda t, w: status.update(
                state.state, t, quality.scores.ready, window=w), publish_output=publish)
        producer.on_publish = lambda primary, tail: lifecycle.process(
            prepare_window(primary), tail)
        for step in range(1100):
            timestamp = 1000 + step*40
            gps = (FilterGps(timestamp, 120.+step*.000003, 30., speed=7.2,
                             direction=0., position_sigma=1.) if step % 25 == 0 else None)
            producer.push(timestamp, (0., 0., 0.), (.2, .3, (9.80665**2-.13)**.5), gps)
        self.assertIn(state.state, (8, 16), (transitions, observers[0].counter, observers[0].detector.status, observers[0].orientation.q, list(observers[0].detector.postures)[-1:], len(records), [(r.timestamp,r.eligible) for r in records[-5:]]))
        self.assertGreater(len(outputs), 20)
        self.assertTrue(np.isfinite([point for _, point in outputs]).all())
        self.assertGreater(producer.gyro_history.total_weight, 20)
        self.assertGreater(producer.last_bias_refresh, 0)
        self.assertEqual([event[1] >> 8 for event in transitions if event[1] >> 8 != 4][:2], [2, 8])


if __name__ == '__main__':
    unittest.main()
