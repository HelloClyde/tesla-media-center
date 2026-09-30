"""Position observation at +7d46fc, after upstream GPS eligibility gates.

Coordinates must use the same datum as the initialized local frame. The
native caller's quality field is supplied as sigma; browser accuracy has
not been established to have identical statistical semantics.
"""
import numpy as np
from vdr_preintegration import skew


def position_observation(state, longitude, latitude, altitude, sigma):
    position = np.asarray(state.pose.position, dtype=float)
    h = np.zeros((3, 21))
    h[:, :3] = -np.asarray(skew(position))
    h[:, 6:9] = np.eye(3)
    observed = np.asarray(state.frame.project(longitude, latitude, altitude))
    residual = observed - position
    variances = np.full(3, sigma * sigma)
    return h, residual, variances


def horizontal_position_observation(state, longitude, latitude, altitude, sigma):
    """Type-8 observation +7d4874 keeps only the horizontal rows."""
    h, residual, variances = position_observation(state, longitude, latitude, altitude, sigma)
    return h[:2], residual[:2], variances[:2]
