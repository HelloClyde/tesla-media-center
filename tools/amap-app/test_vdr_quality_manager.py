import unittest
from types import SimpleNamespace
import numpy as np
from vdr_quality_manager import QualityManager
from vdr_pose_initialization import initialize_pose
from vdr_window_producer import empty_integration
from vdr_window_gps import WindowGps
from vdr_preintegration import advance_pose
from vdr_feature_history import quality_features
from vdr_local_frame import INITIAL_GRAVITY


class QualityManagerTest(unittest.TestCase):
    def test_continuous_real_pose_features_reach_scoring_then_reset(self):
        # Scoring coefficients are a test fixture; pose/statistics are real.
        parameters=dict(means=[0.]*55,scales=[1.]*55,coefficients=[0.]*55,bias=2.)
        manager=QualityManager(parameters)
        state=initialize_pose(1000,0.,10.,(120.,30.,0.),np.eye(3).tolist(),np.eye(3).tolist(),[0.]*3)
        evaluations=[]
        for timestamp in range(1500,31000,500):
            integrated=empty_integration(timestamp-500)
            for tick in range(timestamp-480,timestamp+1,20):
                integrated.advance(tick,(0.,0.,0.),(0.,0.,9.80665))
            window=SimpleNamespace(integrated=integrated,direction=0.,
                gps=WindowGps(timestamp,120.,30.,speed=10.))
            if manager.advance(state,window,np.eye(21),np.zeros(19)):
                evaluations.append(timestamp)
            state.pose=advance_pose(state.pose,integrated,INITIAL_GRAVITY)
        self.assertTrue(evaluations)
        self.assertEqual(manager.scores.primary,-1.)
        self.assertEqual(manager.scores.secondary,2.)
        self.assertEqual(quality_features(manager.histories).shape,(55,))
        self.assertTrue(np.isfinite(quality_features(manager.histories)).all())
        manager.reset()
        self.assertFalse(manager.scores.ready)
        self.assertEqual(manager.poses,[None,None])
        self.assertTrue(all(not h.ready for h in manager.histories))


if __name__=='__main__':
    unittest.main()
