"""Orientation observation from libamaploc +7d4a0c.

Direction is the native east-based angle in degrees, not H5 compass heading.
A negative direction selects tilt-only correction. None means native gate rejection.
"""
import math
import struct
import numpy as np


def heading_observation(state, direction=-1., supplied_variance=-1., flag=False):
    r = np.asarray(state.pose.rotation)
    attitude = r @ np.asarray(state.calibration)
    if direction < 0:
        horizontal = attitude[:2, 0]
        length = np.linalg.norm(horizontal)
        if length < .01:
            return None
        cosine, sine = horizontal / length
    else:
        angle = direction * .017453292519943295
        cosine, sine = math.cos(angle), math.sin(angle)
    target = np.array([[cosine, -sine, 0.], [sine, cosine, 0.], [0., 0., 1.]])
    difference = target @ attitude.T
    trace = np.trace(difference)
    if trace < 2.24:
        return None
    scalar = math.sqrt(trace + 1.) * .5
    residual = np.array([difference[2, 1]-difference[1, 2],
                         difference[0, 2]-difference[2, 0],
                         difference[1, 0]-difference[0, 1]]) * (.5/scalar)
    h = np.zeros((3, 21))
    h[:, :3] = np.eye(3)
    h[:, 15:18] = r
    variances = np.array([struct.unpack('<d', struct.pack('<Q', 0x3f53f6a1db141fb9))[0],
                          .01949551486634935, .08803443431835876])
    if direction < 0:
        rows = [0] if flag else [0, 1]
    elif flag:
        rows = [0, 2]
    else:
        rows = [0, 1, 2]
        if supplied_variance > 0:
            variances[2] = supplied_variance
    return h[rows], residual[rows], variances[rows]
