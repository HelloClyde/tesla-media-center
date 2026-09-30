"""Moving-vehicle constraint +7d3c78, after upstream selection.

Flag names retain native argument identities pending caller semantics.
Gyro and auxiliary offset must use the native sensor coordinate convention.
"""
import numpy as np
from vdr_preintegration import skew


def vehicle_observation(state, gyro, flag4=False, flag5=False):
    r, c = np.asarray(state.pose.rotation), np.asarray(state.calibration)
    v = np.asarray(state.pose.velocity)
    omega = np.asarray(gyro)-state.pose.gyro_bias
    offset_cross = np.asarray(skew(state.auxiliary))
    transform = c.T @ r.T
    modeled = transform @ v + offset_cross @ c.T @ omega
    h = np.zeros((3, 21))
    h[:, 3:6] = transform
    h[:, 9:12] = -offset_cross @ c.T
    h[:, 15:18] = c.T @ skew(r.T @ v) + offset_cross @ c.T @ skew(omega)
    h[:, 18:21] = -np.asarray(skew(c.T @ omega))
    variance = (.02 if flag5 else .001) if flag4 else .1
    return h[1:, :], -modeled[1:], np.full(2, variance)
