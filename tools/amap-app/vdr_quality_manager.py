"""777ba0 continuous pose history, feature collection and scoring callback.

Inputs are native windows/residual categories, not browser GPS substitutes.
"""
import copy
from vdr_feature_history import FeatureHistory, quality_features
from vdr_quality_inputs import collect_quality_inputs
from vdr_quality_scores import QualityScores
from vdr_preintegration import advance_pose, signed32
from vdr_local_frame import INITIAL_GRAVITY, METRES_PER_DEGREE


def valid_pose(state):
    return state is not None and ((state.frame.east_scale > 0 and METRES_PER_DEGREE > 0) or state.flags != 0)


class QualityManager:
    def __init__(self, parameters, *, backend=None, gravity=INITIAL_GRAVITY):
        self.scores = QualityScores(parameters, backend=backend)
        self.gravity = gravity
        self.histories = [FeatureHistory(20 if i == 0 else 10, dimensions)
                          for i, dimensions in enumerate((6,2,2,2,2,1,1,1,6,6,6,6))]
        self.reset()

    def reset(self):
        self.poses = [None, None]
        self.last_shift = -1
        self.scores.reset()
        for history in self.histories:
            history.reset()

    def before_predict(self, engine, window):
        """Callback usable by initialize_from_windows and ordinary prediction.

        The vector belongs to the filter's previous observation. Its first
        value stays -1 until an observation actually publishes a correction.
        """
        return self.advance(engine.correction.state, window,
                            engine.correction.covariance, engine.correction.quality_residual)

    def advance(self, current, window, covariance, residual):
        if not valid_pose(current):
            return False
        self.scores.activate()
        predicted = copy.deepcopy(current)
        predicted.pose = advance_pose(predicted.pose, window.integrated, self.gravity)
        for pose in self.poses:
            if valid_pose(pose):
                pose.pose = advance_pose(pose.pose, window.integrated, self.gravity)
        timestamp = window.integrated.timestamp
        if signed32(timestamp - self.last_shift) > 5000:
            self.poses[0] = copy.deepcopy(self.poses[1])
            self.poses[1] = copy.deepcopy(current)
            self.last_shift = timestamp
        if not valid_pose(self.poses[0]):
            return False
        collect_quality_inputs(self.histories, current, predicted, self.poses[0],
                               window.direction, covariance, residual)
        validity = False if window.gps is None else window.gps.valid
        gps_valid = validity() if callable(validity) else bool(validity)
        return self.scores.evaluate(timestamp, gps_valid,
            [self.histories[i].ready for i in (0,7,9)],
            lambda: quality_features(self.histories))
