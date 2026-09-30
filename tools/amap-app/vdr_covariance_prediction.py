"""Ordinary +7d5c20 prediction with adaptive calibration disabled.

The calibration-enabled post-prediction adaptation remains unimplemented.
History queue management is the caller's responsibility.
"""
from copy import deepcopy
import numpy as np
from vdr_prediction_matrices import prediction_matrices
from vdr_preintegration import advance_pose, signed32
from vdr_process_noise import scale_process_noise


def predict(state, covariance, base_noise, integrated, gravity):
    p = np.asarray(covariance, dtype=float)
    q = np.asarray(base_noise, dtype=float)
    if p.shape != (21, 21) or q.shape != (18, 18):
        raise ValueError('Expected 21x21 state and 18x18 noise covariance')
    f, g = prediction_matrices(state.pose, integrated, gravity)
    transition = np.eye(21)
    transition[:9, :15] = f
    updated = transition @ p @ transition.T
    q = scale_process_noise(q, signed32(integrated.timestamp-integrated.initial_timestamp)*.001)
    updated[:9, :9] += g @ q[:6, :6] @ g.T
    updated[9:, 9:] += q[6:, 6:]
    result = deepcopy(state)
    result.pose = advance_pose(state.pose, integrated, gravity)
    return result, updated
