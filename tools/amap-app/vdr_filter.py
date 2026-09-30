"""Initialized ordinary VDR prediction and observation engine.

This composes translated +7d5c20 and +7d64a0. Native sensor preprocessing,
initial alignment, process-global replay and output road matching are separate.
"""
from dataclasses import dataclass, field
from vdr_observation_lifecycle import ObservationLifecycle
from vdr_covariance_prediction import predict
from vdr_adaptive_prediction import predict_adaptive
from vdr_calibration_gate import CalibrationGate
from vdr_filter_initialization import initial_covariances
from vdr_local_frame import INITIAL_GRAVITY
from vdr_partial_restore import restore_partial


@dataclass
class VdrFilter(ObservationLifecycle):
    base_noise: object = field(default_factory=lambda: initial_covariances()[1])
    gravity: tuple = INITIAL_GRAVITY
    gate: CalibrationGate = field(default_factory=CalibrationGate)

    def restore_recovery(self, state, covariance, mask, *,
                         gyro_bias_variance, accel_bias_variance):
        """Install native recovery state without clearing observation history."""
        restore_partial(self.correction, state, covariance, mask,
                        gyro_bias_variance=gyro_bias_variance,
                        accel_bias_variance=accel_bias_variance)

    def predict(self, integrated):
        """Consume an upstream-approved, positive-duration IMU window."""
        current = self.correction
        if current.calibrate:
            state, covariance, adjusted = predict_adaptive(
                current.state, current.covariance, self.base_noise, integrated, self.gravity, self.gate)
        else:
            state, covariance = predict(
                current.state, current.covariance, self.base_noise, integrated, self.gravity)
            adjusted = False
        current.state, current.covariance = state, covariance
        return adjusted

    def process_window(self, integrated, gps, **observation):
        """Run prediction then observation; upstream owns window eligibility."""
        self.predict(integrated)
        return self.observe(integrated, gps, **observation)
