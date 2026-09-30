"""Zero-velocity observation +7d4274, after native stationary selection."""
import numpy as np


def stationary_observation(state):
    h = np.zeros((3, 21))
    h[:, 3:6] = np.eye(3)
    return h, -np.asarray(state.pose.velocity), np.full(3, .0004)
