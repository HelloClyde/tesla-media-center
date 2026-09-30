import unittest
import numpy as np
from vdr_running_states import fallback_transition, TransitionRequest, aligned_transition
from vdr_state_transition import ManagerState
from vdr_calibration_observer import CalibrationObserver
from vdr_orientation_quality import OrientationQualityObserver


class RunningStatesTest(unittest.TestCase):
    def test_upgrade_restores_before_notification_and_disables_calibration(self):
        events = []
        record = object()
        calibration, quality = CalibrationObserver(), OrientationQualityObserver()
        for observer in (calibration, quality):
            observer.transition(1000, 8)
        request = fallback_transition(20, np.eye(3), retain_on_quality_loss=False,
            select_history=lambda: record, maximum_attitude_difference=lambda _: 10.,
            threshold=5., reinitialize=lambda r: events.append(('restore', r)),
            notify_reinitialized=lambda: events.append(('notification',)))
        self.assertEqual(events, [('restore', record), ('notification',)])
        self.assertEqual(request, TransitionRequest(16, 0, 1))
        state = ManagerState(8, 1000, 0, 1000)
        state.transition(request.state, 2000, request.reason, request.forced,
            lambda *args: None, [calibration.transition, quality.transition], lambda *args: None)
        self.assertFalse(calibration.enabled)
        self.assertTrue(quality.enabled)
        self.assertEqual(aligned_transition(0), TransitionRequest(32, 16))

    def test_no_restore_without_large_difference_and_eligible_history(self):
        events = []
        def request(quality, preferred, record, delta, retain=False):
            return fallback_transition(quality, preferred, retain_on_quality_loss=retain,
                select_history=lambda: record, maximum_attitude_difference=lambda _: delta,
                threshold=5., reinitialize=lambda r: events.append(r),
                notify_reinitialized=lambda: events.append('event'))
        self.assertEqual(request(1, np.eye(3), object(), 5.), TransitionRequest(16))
        self.assertEqual(request(1, np.eye(3), None, 6.), TransitionRequest(8, 2))
        self.assertEqual(request(1, np.full((3,3),100.), None, 0.), TransitionRequest(8, 0))
        self.assertEqual(request(0, np.eye(3), None, 0.), TransitionRequest(2, 0, 3))
        self.assertEqual(request(0, np.eye(3), None, 0., True), TransitionRequest(32, 8))
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
