"""Measurement correction math at +7d5810 (research, requires NumPy).

Inputs H, residual and measurement covariance are already constructed.
This does not construct GPS observations or predict covariance.
"""
from dataclasses import dataclass, field
import numpy as np
from vdr_error_injection import inject_error
from vdr_rotation_normalization import normalize_rotation
from vdr_observation_stack import stack_observations
from vdr_reanchor import reanchor
from vdr_calibration_transition import calibration_transition
from vdr_observation_dispatch import observation_blocks


def measurement_update(state, covariance, observation_matrix, residual,
                       measurement_covariance, calibrate=True):
    p = np.asarray(covariance, dtype=float)
    h = np.asarray(observation_matrix, dtype=float)
    r = np.asarray(measurement_covariance, dtype=float)
    residual = np.asarray(residual, dtype=float).reshape(-1)
    if p.shape != (21, 21) or h.ndim != 2 or h.shape[1] != 21:
        raise ValueError('Expected 21-state covariance and observation matrix')
    if r.shape != (h.shape[0], h.shape[0]) or residual.size != h.shape[0]:
        raise ValueError('Observation dimensions disagree')
    innovation_covariance = h @ p @ h.T + r
    gain = np.linalg.solve(innovation_covariance.T, (p @ h.T).T).T
    error = gain @ residual
    updated_state = inject_error(state, error.tolist(), 0x7f if calibrate else 7)
    remainder = np.eye(21) - gain @ h
    updated_covariance = remainder @ p @ remainder.T + gain @ r @ gain.T
    updated_covariance = (updated_covariance + updated_covariance.T) * .5
    return updated_state, updated_covariance, error


@dataclass
class CorrectionFilter:
    """Native correction state and counter; prediction/input lifecycle pending."""
    state: object
    covariance: object
    count: int = 0
    calibrate: bool = True
    # 7d6ea8 invalidates category; 7d68e4 stores GPS-use +21-state correction.
    quality_residual: object = field(default_factory=lambda: np.r_[-1., np.zeros(21)])

    def transition_calibration(self, requested, installation_variance):
        self.covariance, self.calibrate = calibration_transition(
            self.covariance, self.calibrate, requested, installation_variance)

    def reanchor(self):
        self.state, self.covariance, changed = reanchor(self.state, self.covariance)
        return changed

    def update_observations(self, blocks):
        observation = stack_observations(blocks)
        return None if observation is None else self.update(*observation)

    def correct_prepared_frame(self, gps, **selection):
        """Correct an eligible native frame after timestamp/history preparation.

        This does not derive native motion classification or fabricate IMU.
        The caller remains responsible for eligibility and calibration exit.
        """
        self.reanchor()
        blocks, used_gps = observation_blocks(
            self.state, gps, calibrate=self.calibrate, **selection)
        error = self.update_observations(blocks)
        if error is not None:
            self.quality_residual = np.r_[float(used_gps), error]
        return error, used_gps

    def update(self, observation_matrix, residual, measurement_covariance):
        state, covariance, error = measurement_update(
            self.state, self.covariance, observation_matrix, residual,
            measurement_covariance, self.calibrate)
        count = ((self.count + 1 + 2**31) % 2**32) - 2**31
        if count % 100 == 0:
            state.pose.rotation = normalize_rotation(state.pose.rotation)
        if count % 1000 == 0:
            state.calibration = normalize_rotation(state.calibration)
        self.state, self.covariance, self.count = state, covariance, count
        return error
