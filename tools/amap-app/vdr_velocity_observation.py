"""Native horizontal velocity observation +7d4084 after GPS quality gates.

Direction is native angle from local east, not browser compass heading.
"""
import math
import numpy as np
from vdr_preintegration import skew


def velocity_observation(state, speed, direction_degrees):
    velocity = np.asarray(state.pose.velocity)
    h = np.zeros((2, 21))
    h[:, :3] = -np.asarray(skew(velocity))[:2, :]
    h[:, 3:5] = np.eye(2)
    corrected = speed - .8333333333333333 if speed > 8.88888888888889 else speed
    angle = direction_degrees*math.pi/180.
    measured = np.array([corrected*math.cos(angle), corrected*math.sin(angle)])
    return h, measured-velocity[:2], np.ones(2)
