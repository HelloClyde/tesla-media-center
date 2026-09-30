"""Local origin reset and covariance transform +7d5560/+78b39c."""
from copy import deepcopy
import math
import numpy as np
from vdr_local_frame import LocalFrame
from vdr_preintegration import skew


def reanchor(state, covariance):
    result = deepcopy(state)
    p = np.array(covariance, dtype=float, copy=True)
    shift = state.pose.position
    if math.sqrt(sum(v*v for v in shift)) < 100.:
        return result, p, False
    result.frame = LocalFrame(*state.frame.unproject(*shift))
    result.pose.position = [0., 0., 0.]
    transform = np.eye(21)
    transform[6:9, :3] = -np.asarray(skew(shift))
    return result, transform @ p @ transform.T, True
