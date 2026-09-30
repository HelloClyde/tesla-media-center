"""Gyro recovery gate +7bf980, used by initialization-quality observer.

Thresholds are native units; this module does not infer browser gyro units.
"""
from dataclasses import dataclass
from vdr_sample_calibration import f32
from vdr_state_transition import signed32


@dataclass
class GyroQualityGate:
    trigger_threshold: float = 1.5
    recovery_threshold: float = .25
    recovery_delay: int = 3000
    status: int = -1
    last_trigger: int = -1000

    def advance(self, timestamp, gyro):
        timestamp = signed32(timestamp)
        values = [abs(f32(value)) for value in gyro]
        if len(values) != 3:
            raise ValueError('Expected three native gyro components')
        if all(value > f32(self.trigger_threshold) for value in values):
            self.status, self.last_trigger = 0, timestamp
        if self.last_trigger < 0:
            return True
        if (signed32(timestamp - self.last_trigger) > self.recovery_delay
                and all(value < f32(self.recovery_threshold) for value in values)):
            self.last_trigger = -1000
            return True
        return False
