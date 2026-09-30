"""Calibration exit +7d6ca4; this function cannot enable calibration."""
import numpy as np


def calibration_transition(covariance, enabled, requested, installation_variance):
    covariance = np.array(covariance, dtype=float, copy=True)
    if enabled and not requested:
        covariance[:, 15:] = 0.
        covariance[15:, :] = 0.
        covariance[15:18, 15:18] = np.eye(3)*installation_variance
        return covariance, False
    return covariance, bool(enabled)
