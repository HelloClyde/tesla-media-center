"""Stored stationary attitude constraint at +7d43dc.

The caller selects the reference from its stationary rotation history.
This function does not classify the vehicle as stationary.
"""
import math
import struct
import numpy as np


def stationary_attitude_observation(state, reference_rotation):
    difference = np.asarray(reference_rotation) @ np.asarray(state.pose.rotation).T
    scalar = math.sqrt(np.trace(difference) + 1.) * .5
    residual = np.array([difference[2, 1]-difference[1, 2],
                         difference[0, 2]-difference[2, 0],
                         difference[1, 0]-difference[0, 1]]) * (.5/scalar)
    h = np.zeros((3, 21))
    h[:, :3] = np.eye(3)
    variance = struct.unpack('<d', struct.pack('<Q', 0x3eb92a737110e454))[0]
    return h, residual, np.full(3, variance)
