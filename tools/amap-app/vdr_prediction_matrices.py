"""Native +78baec state/noise Jacobians for positive integration duration."""
import numpy as np
from vdr_preintegration import advance_pose, rotation_and_right_jacobian, skew, signed32


def prediction_matrices(pose, integrated, gravity):
    dt = signed32(integrated.timestamp-integrated.initial_timestamp)*.001
    if dt <= 0:
        raise ValueError('Prediction requires a positive integration interval')
    predicted = advance_pose(pose, integrated, gravity)
    r = np.asarray(pose.rotation)
    jrg = np.asarray(integrated.rotation_gyro_derivative)
    phi = jrg @ (np.asarray(pose.gyro_bias)-integrated.gyro_bias)
    correction, right = rotation_and_right_jacobian(phi)
    a = r @ integrated.rotation @ correction @ right @ jrg
    b = np.asarray(skew(predicted.velocity)) @ a + r @ integrated.velocity_gyro_derivative
    c = np.asarray(skew(predicted.position)) @ a + r @ integrated.position_gyro_derivative
    f = np.zeros((9, 15))
    f[:, :9] = np.eye(9)
    f[3:6, :3] = skew(np.asarray(gravity)*dt)
    f[6:9, :3] = skew(np.asarray(gravity)*.5*dt*dt)
    f[6:9, 3:6] = np.eye(3)*dt
    f[:3, 9:12] = a
    f[3:6, 9:12] = b
    f[6:9, 9:12] = c
    f[3:6, 12:15] = r @ integrated.velocity_accel_derivative
    f[6:9, 12:15] = r @ integrated.position_accel_derivative
    return f, -f[:, 9:15]/dt
