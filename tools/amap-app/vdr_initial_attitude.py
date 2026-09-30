"""Fallback attitude basis at libamaploc +762898.

Called with the accumulated accelerometer vector by +7bd1a4. This is a
basis construction, not the complete alignment estimator or GPS fusion.
Rows are returned as Python lists; native matrix storage is column-major.
"""
import math
from vdr_preintegration import rotation_and_right_jacobian


def align_vectors(source, target):
    """+7632c8: normalize, cross/acos rotation vector, then exponentiate.

    This primitive has no parallel/zero-vector recovery. Keep its non-finite
    result visible so an eventual runtime adapter can reject it explicitly.
    """
    def normalized(vector):
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else [math.nan] * 3

    a, b = normalized(source), normalized(target)
    cross = [a[1] * b[2] - a[2] * b[1],
             a[2] * b[0] - a[0] * b[2],
             a[0] * b[1] - a[1] * b[0]]
    dot = sum(x * y for x, y in zip(a, b))
    # ARM FMINNM selects the numeric operand when the other is NaN.
    dot = 1. if math.isnan(dot) else min(dot, 1.)
    angle = math.acos(dot) if dot >= -1. else math.nan
    norm = math.sqrt(sum(v * v for v in cross))
    vector = [angle * v / norm for v in cross] if norm else [math.nan] * 3
    return rotation_and_right_jacobian(vector)[0]


def attitude_from_acceleration(x, y, z):
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        if z < 0:
            return [[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]]
        return [[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]]

    def normalize(v):
        square = v[2] * v[2] + (v[0] * v[0] + v[1] * v[1])
        if square > 0:
            length = math.sqrt(square)
            return [a / length for a in v]
        return v

    up = normalize([x, y, z])
    side = normalize([-y, x, 0.])
    forward = [side[1] * up[2] - side[2] * up[1],
               side[2] * up[0] - side[0] * up[2],
               side[0] * up[1] - side[1] * up[0]]
    return [[forward[i], side[i], up[i]] for i in range(3)]
