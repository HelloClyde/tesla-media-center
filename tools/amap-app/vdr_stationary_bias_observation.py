"""Stationary gyro-bias observation +7d4564 (after caller time gate).

Requires actual native-convention IMU preintegration, not GPS-derived IMU.
"""
import math
import numpy as np
from vdr_preintegration import signed32


def native_rotation_log(rotation):
    """+763e60, retaining the original near-zero and trace=-1 branches."""
    r = np.asarray(rotation)
    trace = float(np.trace(r))
    if np.max(np.abs(r-np.eye(3))) <= 1e-12 or abs(trace-3.) < 2.220446049250313e-13:
        return np.zeros(3)
    if abs(trace+1.) <= 2.220446049250313e-16:
        return np.array([r[0, 2], r[1, 2], r[2, 2]+1.]) / math.sqrt(2.*(r[2, 2]+1.))
    angle = math.acos((trace-1.)*.5)
    vector = np.array([r[2, 1]-r[1, 2], r[0, 2]-r[2, 0], r[1, 0]-r[0, 1]])
    return vector * (.5 if abs(angle) < .0001 else angle*.5/math.sin(angle))


def stationary_bias_observation(state, integrated):
    correction = np.linalg.solve(np.asarray(integrated.rotation_gyro_derivative),
                                 native_rotation_log(np.asarray(integrated.rotation).T))
    residual = correction + integrated.gyro_bias - np.asarray(state.pose.gyro_bias)
    h = np.zeros((3, 21))
    h[:, 9:12] = np.eye(3)
    duration = signed32(integrated.timestamp-integrated.initial_timestamp)*.001
    return h, residual, np.full(3, duration*.0001/25.+1.5e-6)
