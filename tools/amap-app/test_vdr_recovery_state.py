import unittest
from types import SimpleNamespace
from vdr_state_transition import ManagerState
from vdr_recovery_state import recover
import numpy as np
from vdr_recovery_candidate import restore_fallback, AlignedRecovery
from vdr_filter import VdrFilter
from vdr_filter_update import CorrectionFilter
from vdr_pose_initialization import initialize_pose


class RecoveryTest(unittest.TestCase):
    def test_aligned_candidate_writes_installation_uncertainty_and_expires(self):
        state = initialize_pose(1000,0.,10.,(120.,30.,0.),
                                np.eye(3).tolist(),np.eye(3).tolist(),[0.,0.,0.])
        engine = VdrFilter(CorrectionFilter(state,np.eye(21),calibrate=False))
        estimator = AlignedRecovery()
        window = SimpleNamespace(integrated=SimpleNamespace(timestamp=2000),direction=90.)
        self.assertTrue(estimator.restore(engine,window,np.eye(21),
            gyro_bias_variance=1e-7,accel_bias_variance=1e-4))
        np.testing.assert_allclose(np.diag(engine.correction.covariance)[15:18],
                                   (1+np.sqrt(estimator.variance))**2)
        np.testing.assert_array_equal(engine.correction.state.pose.rotation,np.eye(3))
        self.assertTrue(engine.correction.calibrate)
        window.direction = -1.
        window.integrated.timestamp = 4000
        before = engine.correction.covariance.copy()
        self.assertFalse(estimator.restore(engine,window,np.eye(21),
            gyro_bias_variance=1e-7,accel_bias_variance=1e-4))
        np.testing.assert_array_equal(engine.correction.covariance,before)

    def test_fallback_recovery_installs_real_candidate_before_state_change(self):
        state = initialize_pose(1000, 0., 10., (120.,30.,0.),
                                np.eye(3).tolist(), np.eye(3).tolist(), [0.,0.,0.])
        state.pose.position = [12.,3.,0.]
        engine = VdrFilter(CorrectionFilter(state, np.eye(21), calibrate=False))
        manager = ManagerState(32,1000,8,1000)
        window = SimpleNamespace(integrated=SimpleNamespace(timestamp=2000,mean_accel=(.2,.3,9.8)),
                                 direction=90.,quality=6,missing_fix=False,missing_duration=0)
        def install(window):
            restore_fallback(engine,window,np.eye(21),gyro_bias_variance=1e-7,
                             accel_bias_variance=1e-4)
        def transition(request):
            self.assertTrue(engine.correction.calibrate)
            manager.transition(request.state,2000,request.reason,request.forced,
                               lambda *args: None,[],lambda *args: None)
        recover(manager,window,allow_fallback_recovery=True,tolerate_missing=False,
                recovery_timeout=10000,restore_aligned=lambda _: False,
                restore_fallback=install,transition=transition)
        self.assertEqual(manager.state,8)
        self.assertEqual(engine.correction.state.pose.position,[12.,3.,0.])
        np.testing.assert_array_equal(np.diag(engine.correction.covariance)[15:18], [.001]*3)
        self.assertFalse(np.allclose(engine.correction.state.pose.rotation,np.eye(3)))

    def test_success_changes_deadline_before_timeout_check(self):
        for reason, quality, restored in ((16, 1, 16), (8, 6, 8)):
            manager = ManagerState(32, 1000, reason, 1000)
            window = SimpleNamespace(integrated=SimpleNamespace(timestamp=20000),
                quality=quality, direction=0., missing_fix=False, missing_duration=0)
            events = []
            def transition(request):
                events.append(request.state)
                manager.transition(request.state, 20000, request.reason, request.forced,
                                   lambda *args: None, [], lambda *args: None)
            def restore(window):
                events.append('restore')
                return True
            recover(manager, window, allow_fallback_recovery=True, tolerate_missing=False,
                    recovery_timeout=10000, restore_aligned=restore,
                    restore_fallback=restore, transition=transition)
            self.assertEqual(events, ['restore', restored])
            self.assertEqual(manager.state, restored)

    def test_nan_direction_does_not_restore_fallback(self):
        events = []
        window = SimpleNamespace(integrated=SimpleNamespace(timestamp=1001),
            quality=6, direction=float('nan'), missing_fix=False, missing_duration=0)
        recover(ManagerState(32, 1000, 8, 1000), window,
                allow_fallback_recovery=True, tolerate_missing=False, recovery_timeout=10000,
                restore_aligned=lambda _: False, restore_fallback=lambda _: events.append('restore'),
                transition=events.append)
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
