"""Native preintegration concatenation +7cfbdc for equal reference biases."""
import copy
import numpy as np
from vdr_preintegration import Preintegration, skew, signed32, rotation_and_right_jacobian


def rebase_bias(integrated, gyro_bias, accel_bias):
    """+7cf4a0 updates deltas and the rotational bias Jacobian."""
    result = copy.deepcopy(integrated)
    if result.count:
        dg = np.asarray(gyro_bias)-integrated.gyro_bias
        da = np.asarray(accel_bias)-integrated.accel_bias
        phi = np.asarray(integrated.rotation_gyro_derivative)@dg
        rotation, jacobian = rotation_and_right_jacobian(phi)
        result.rotation = (np.asarray(integrated.rotation)@rotation).tolist()
        result.velocity = (np.asarray(integrated.velocity)+np.asarray(integrated.velocity_gyro_derivative)@dg+np.asarray(integrated.velocity_accel_derivative)@da).tolist()
        result.position = (np.asarray(integrated.position)+np.asarray(integrated.position_gyro_derivative)@dg+np.asarray(integrated.position_accel_derivative)@da).tolist()
        result.rotation_gyro_derivative = (np.asarray(jacobian)@integrated.rotation_gyro_derivative).tolist()
    result.gyro_bias, result.accel_bias = list(gyro_bias), list(accel_bias)
    return result


def compose(first, second):
    """+7cfaa0 aligns the older window's biases to the newer window first."""
    if not first.count:
        return copy.deepcopy(second)
    if not second.count:
        return copy.deepcopy(first)
    differences = np.r_[np.asarray(first.gyro_bias)-second.gyro_bias,
                        np.asarray(first.accel_bias)-second.accel_bias]
    if np.any(np.abs(differences) >= 2.220446049250313e-16):
        first = rebase_bias(first, second.gyro_bias, second.accel_bias)
    return compose_same_bias(first, second)


def compose_same_bias(first, second):
    """Combine consecutive windows; bias alignment belongs to +7cfaa0."""
    if np.any(np.abs(np.r_[np.asarray(first.gyro_bias)-second.gyro_bias,
                          np.asarray(first.accel_bias)-second.accel_bias]) >= 2.220446049250313e-16):
        raise ValueError('Reference biases must be aligned before composition')
    if not first.count:
        return copy.deepcopy(second)
    if not second.count:
        return copy.deepcopy(first)
    a, b = first, second
    ra, rb = np.asarray(a.rotation), np.asarray(b.rotation)
    ja, jb = np.asarray(a.rotation_gyro_derivative), np.asarray(b.rotation_gyro_derivative)
    vg, va = np.asarray(a.velocity_gyro_derivative), np.asarray(a.velocity_accel_derivative)
    dt = signed32(b.timestamp-b.initial_timestamp)*.001
    count = signed32(a.count+b.count)
    result = Preintegration(
        rotation_gyro_derivative=(rb.T@ja+jb).tolist(),
        velocity_gyro_derivative=(vg-ra@skew(b.velocity)@ja+ra@b.velocity_gyro_derivative).tolist(),
        velocity_accel_derivative=(va+ra@b.velocity_accel_derivative).tolist(),
        position_gyro_derivative=(np.asarray(a.position_gyro_derivative)+vg*dt-ra@skew(b.position)@ja+ra@b.position_gyro_derivative).tolist(),
        position_accel_derivative=(np.asarray(a.position_accel_derivative)+va*dt+ra@b.position_accel_derivative).tolist(),
        rotation=(ra@rb).tolist(),
        velocity=(np.asarray(a.velocity)+ra@b.velocity).tolist(),
        position=(np.asarray(a.position)+np.asarray(a.velocity)*dt+ra@b.position).tolist(),
        gyro_bias=a.gyro_bias[:], accel_bias=a.accel_bias[:],
        timestamp=b.timestamp, initial_timestamp=a.initial_timestamp, count=count,
        latest_gyro=list(b.latest_gyro))
    for name in ('mean_gyro', 'mean_accel'):
        setattr(result, name, ((np.asarray(getattr(a,name))*a.count+np.asarray(getattr(b,name))*b.count)/count).tolist())
    return result
