"""Fallback recovery preparation at 77c194..77c280 (reason8, mask61)."""
import copy
import math
import numpy as np
import struct
from vdr_state_transition import signed32
from vdr_initial_attitude import attitude_from_acceleration


def fallback_candidate(current_state, mean_accel, direction, base_covariance,
                       *, preserve_covariance=False):
    state = copy.deepcopy(current_state)
    calibration = np.asarray(attitude_from_acceleration(*mean_accel))
    angle = direction * math.pi / 180.
    c, s = math.cos(angle), math.sin(angle)
    yaw = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    state.pose.rotation = (yaw @ calibration.T).tolist()
    state.calibration = calibration.tolist()
    covariance = np.array(base_covariance, dtype=float, copy=True)
    if not preserve_covariance:
        covariance[:] = 0.
        for index in range(15, 18):
            covariance[index, index] = .001
    return state, covariance


def restore_fallback(engine, window, base_covariance, *, preserve_covariance=False,
                     gyro_bias_variance, accel_bias_variance):
    state, covariance = fallback_candidate(engine.correction.state,
        window.integrated.mean_accel, window.direction, base_covariance,
        preserve_covariance=preserve_covariance)
    engine.restore_recovery(state, covariance, 0x61,
                            gyro_bias_variance=gyro_bias_variance,
                            accel_bias_variance=accel_bias_variance)


class AlignedRecovery:
    """7bde00/7bde68: last direction/attitude estimate, valid for under 2 s."""
    def __init__(self):
        self.direction = -1.
        self.last_direction = 0
        self.timestamp = 0
        self.calibration = np.zeros((3, 3))
        self.variance = np.array([0., 0., struct.unpack('<d', bytes.fromhex('91714fe65c31bf3f'))[0]])
        self.ready = False

    def reset(self):
        # 7bde54 retains matrix and variance while invalidating timing.
        self.direction = -1.
        self.last_direction = self.timestamp = 0
        self.ready = False

    def advance(self, timestamp, direction, rotation):
        self.timestamp = signed32(timestamp)
        if direction >= 0:
            self.direction = direction
            self.last_direction = self.timestamp
            angle = direction * math.pi / 180.
            c, s = math.cos(angle), math.sin(angle)
            yaw = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            self.calibration = np.asarray(rotation).T @ yaw
        self.ready = self.last_direction > 0 and self.timestamp < signed32(self.last_direction + 2000)
        return self.ready

    def restore(self, engine, window, base_covariance, *, preserve_covariance=False,
                gyro_bias_variance, accel_bias_variance):
        if not self.advance(window.integrated.timestamp, window.direction,
                            engine.correction.state.pose.rotation):
            return False
        state = copy.deepcopy(engine.correction.state)
        state.calibration = self.calibration.tolist()
        covariance = np.array(base_covariance, copy=True)
        if not preserve_covariance:
            covariance[:] = 0.
            with np.errstate(invalid='ignore'):
                variance = (np.sqrt(np.diag(engine.correction.covariance)[:3]) + np.sqrt(self.variance)) ** 2
            for index in range(3):
                covariance[15 + index, 15 + index] = variance[index]
        engine.restore_recovery(state, covariance, 0x60,
                                gyro_bias_variance=gyro_bias_variance,
                                accel_bias_variance=accel_bias_variance)
        return True
