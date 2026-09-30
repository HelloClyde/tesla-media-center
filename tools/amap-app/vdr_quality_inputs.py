"""Pose/vector projections feeding quality histories; native field units."""
import math
import numpy as np
from vdr_posture_quality import vector_angle


def grouped_norms(values, offset=0):
    """776ff4: six Euclidean norms over consecutive groups of three."""
    values = np.asarray(values, dtype=float)[offset:offset + 18]
    if values.size != 18:
        raise ValueError('Expected eighteen values after the input offset')
    return np.sqrt(np.sum(values.reshape(6, 3) ** 2, axis=1))


def vehicle_velocity(state):
    return np.asarray(state.calibration).T @ np.asarray(state.pose.rotation).T @ np.asarray(state.pose.velocity)


def vehicle_angles(state):
    rotation = np.asarray(state.pose.rotation) @ np.asarray(state.calibration)
    return np.degrees([math.atan2(rotation[2, 1], rotation[2, 2]),
                       math.atan2(-rotation[2, 0], math.hypot(rotation[2, 1], rotation[2, 2])),
                       math.atan2(rotation[1, 0], rotation[0, 0])])


def collect_quality_inputs(histories, current, predicted, oldest, direction,
                           covariance, residual):
    """777cd4..777fdc feed ordering after upstream prediction/history shift.

Residual[0] is the native category marker; it must not be synthesized from
browser GPS quality. All poses are already in the native local frame.
"""
    histories[0].push([*predicted.pose.gyro_bias, *predicted.pose.accel_bias])
    histories[1].push(vehicle_velocity(predicted)[1:3])
    histories[2].push(vehicle_angles(predicted)[:2])
    histories[3].push(vehicle_velocity(oldest)[1:3])
    histories[4].push(vehicle_angles(oldest)[:2])
    histories[5].push([predicted.frame.unproject(*predicted.pose.position)[2]])
    histories[6].push([abs(vector_angle(np.asarray(current.pose.rotation)[2],
                                        np.asarray(predicted.pose.rotation)[2]))])
    if direction >= 0:
        delta = (direction - vehicle_angles(current)[2] + 180.) % 360. - 180.
        histories[7].push([abs(delta)])
    norm_residual = grouped_norms(residual, 1)
    norm_covariance = grouped_norms(np.diag(covariance))
    if abs(residual[0] - 1.) <= 1e-15:
        histories[8].push(norm_residual)
        histories[10].push(norm_covariance)
    elif abs(residual[0]) <= 1e-15:
        histories[9].push(norm_residual)
        histories[11].push(norm_covariance)
