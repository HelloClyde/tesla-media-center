"""Triggered calibration covariance inflation at +7d6258..+7d643c."""
import numpy as np


def inflate_calibration_covariance(covariance, rotation_change):
    p = np.asarray(covariance, dtype=float)
    diagonal = np.diag(p)[15:18]
    if p.shape != (21, 21) or np.any(diagonal <= 0):
        raise ValueError('Expected 21-state covariance with positive calibration variances')
    factors = np.ones(21)
    factors[15:18] = np.sqrt(1. + (.5*rotation_change)**2/diagonal)
    return (p*factors[:, None])*factors[None, :]
