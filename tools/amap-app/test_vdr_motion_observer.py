"""Integration regression for manager -> replay -> motion publication."""
import unittest
import numpy as np
from vdr_motion_observer import MotionObserver, MotionWindow
from vdr_state_transition import ManagerState
from vdr_window_dispatch import DispatchWindow, SamplePair, dispatch_window
from vdr_window_producer import empty_integration


class MotionObserverTest(unittest.TestCase):
    def test_state_replay_publication_and_bias_retention(self):
        observer = MotionObserver()
        manager = ManagerState(1, 0, 0, 0)
        manager.transition(2, 1000, 0, 0, lambda *args: None,
                           [observer.transition], lambda *args: None)
        self.assertTrue(observer.enabled)
        for window_index in range(8):
            timestamp = 1000 + window_index * 500
            integrated = empty_integration(timestamp)
            payload = MotionWindow(integrated)
            dispatch = DispatchWindow(None, payload, [
                SamplePair(timestamp + index * 20, (0., 0., 0.), (0., 0., 9.8))
                for index in range(25)])
            dispatch_window(dispatch, [observer], lambda *args: None, lambda: None)
        self.assertEqual((payload.motion, payload.stable), (0, 1))
        self.assertGreater(payload.detail, 0)
        observer.detector.bias[:] = (.001, .002, .003)
        observer.detector.bias_count = 30
        # Moving among active states must not reset the classifier.
        manager.transition(16, 5000, 0, 0, lambda *args: None,
                           [observer.transition], lambda *args: None)
        self.assertEqual(observer.detector.classifier.count, 25)
        manager.transition(1, 6000, 0, 0, lambda *args: None,
                           [observer.transition], lambda *args: None)
        self.assertFalse(observer.enabled)
        self.assertEqual(observer.detector.classifier.count, 0)
        self.assertEqual(observer.detector.detail, -1)
        np.testing.assert_array_equal(observer.detector.bias, (.001, .002, .003))
        self.assertEqual(observer.detector.bias_count, 30)


if __name__ == '__main__':
    unittest.main()
