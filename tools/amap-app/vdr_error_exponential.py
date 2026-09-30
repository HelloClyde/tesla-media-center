"""Native +763b88: rotation and translated columns of a state increment.

Research primitive only; this does not compute a GPS correction or run a
navigation filter. Input consists of rotation error followed by 3-vectors.
"""
from vdr_preintegration import rotation_and_right_jacobian, transpose, transform


def error_exponential(values):
    if len(values) < 3 or len(values) % 3:
        raise ValueError('Expected rotation followed by complete 3-vectors')
    rotation, right = rotation_and_right_jacobian(values[:3])
    left = transpose(right)
    columns = [transform(left, values[i:i + 3])
               for i in range(3, len(values), 3)]
    return rotation, columns
