"""Process-noise scaling expression at +7da3a8 called from +7d5f1c.

Base covariance calibration and noise projection are separate native steps.
"""
import numpy as np


def scale_process_noise(base_covariance, seconds):
    return np.asarray(base_covariance, dtype=float) * seconds / 25.
