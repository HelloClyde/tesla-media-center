"""Calibration observer wiring for native configuration byte8 bit3 clear.

Optional attitude adjustment (bit3) remains separate. Raw GPS and sensor
payloads here use native fields/units, not assumed browser equivalents.
"""
import numpy as np
from vdr_attitude_calibration import CalibrationWindow
from vdr_state_transition import ObserverActivation


class CalibrationObserver:
    replay_enabled = True

    def __init__(self, *, motion_estimates_bias=False):
        self.activation = ObserverActivation(mask=12)
        self.motion_estimates_bias = motion_estimates_bias
        self._reset()

    def _reset(self):
        self.window = CalibrationWindow()
        self.bias = np.zeros(3)
        self.bias_count = 0

    @property
    def enabled(self):
        return self.activation.enabled

    def transition(self, timestamp, state):
        self.activation.transition(timestamp, state, lambda _: None, lambda _: self._reset())

    def sample(self, timestamp, gps, gyro, accel):
        # 77a3c0 stops ingestion after the preferred solution becomes ready.
        if self.window.calibration.rotation is not None:
            return
        speed = None
        if gps is not None and gps.valid() and gps.position_sigma <= 20:
            if gps.speed > 0 or (gps.speed == 0 and gps.zero_speed_valid):
                speed = gps.speed
        self.window.advance(timestamp, np.asarray(gyro, dtype=np.float32).astype(float),
                            np.asarray(accel, dtype=np.float32).astype(float), speed)

    def publish(self, payload):
        if not self.motion_estimates_bias:
            if payload.stable == 1:
                count = payload.integrated.count
                total = (self.bias_count + count) & 0xffffffff
                # The native routine uses IEEE division, including a zero total.
                with np.errstate(divide='ignore', invalid='ignore'):
                    weight = np.divide(float(count), float(total))
                    self.bias += (np.asarray(payload.integrated.mean_gyro) - self.bias) * weight
                self.bias_count = total
            if self.bias_count >= 26:
                payload.gyro_bias = self.bias.copy()
        if self.window.calibration.rotation is not None:
            payload.preferred = np.asarray(self.window.calibration.rotation).copy()
        if self.window.fallback_ready:
            payload.fallback = (None if self.window.fallback_rotation is None
                                else np.asarray(self.window.fallback_rotation).copy())
