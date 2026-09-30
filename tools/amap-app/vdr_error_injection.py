"""State correction at libamaploc +78c0e4; no measurement estimator here."""
from copy import deepcopy
from vdr_error_exponential import error_exponential
from vdr_preintegration import multiply, transform, rotation_and_right_jacobian


def inject_error(state, error, flags=0x7f):
    """Return a corrected InitializedPose, preserving fields not selected."""
    if len(error) != 21:
        raise ValueError('Native state correction requires 21 entries')
    result = deepcopy(state)
    pose = result.pose
    if flags & 7 == 7:
        rotation, columns = error_exponential(error[:9])
        pose.rotation = multiply(rotation, pose.rotation)
        pose.velocity = [a+b for a,b in zip(transform(rotation, pose.velocity), columns[0])]
        pose.position = [a+b for a,b in zip(transform(rotation, pose.position), columns[1])]
    if flags & 8:
        pose.gyro_bias = [a+b for a,b in zip(pose.gyro_bias, error[9:12])]
    if flags & 16:
        pose.accel_bias = [a+b for a,b in zip(pose.accel_bias, error[12:15])]
    if flags & 32:
        rotation, _ = rotation_and_right_jacobian(error[15:18])
        result.calibration = multiply(rotation, result.calibration)
    if flags & 64:
        result.auxiliary = tuple(a+b for a,b in zip(result.auxiliary, error[18:21]))
    return result
