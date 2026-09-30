"""Ordinary filter 7d7060 partial restoration used by recovery masks60/61.

Unlike full restoration this neither resets the manager nor replays history.
Only mounting rotation, optionally attitude, covariance and calibration mode
change. Incoming auxiliary/bias/position/velocity values are not copied.
"""
import copy
import numpy as np


def restore_partial(correction, incoming, incoming_covariance, mask, *,
                    gyro_bias_variance, accel_bias_variance):
    if mask not in (0x60, 0x61):
        raise ValueError('Only verified recovery masks 0x60 and 0x61 are supported')
    covariance = np.array(correction.covariance, dtype=float, copy=True)
    covariance[9:, :] = 0.
    covariance[:, 9:] = 0.
    covariance[9:12, 9:12] = np.eye(3) * gyro_bias_variance
    covariance[12:15, 12:15] = np.eye(3) * accel_bias_variance
    for index in range(15, 18):
        covariance[index, index] = incoming_covariance[index, index]
    correction.state.calibration = copy.deepcopy(incoming.calibration)
    if mask & 1:
        correction.state.pose.rotation = copy.deepcopy(incoming.pose.rotation)
    correction.covariance = covariance
    correction.calibrate = True
