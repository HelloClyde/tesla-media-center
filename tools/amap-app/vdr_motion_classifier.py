"""IMU motion classifier +7bb434/+7bb58c/+7bb84c.

Inputs are native internal gyro and acceleration samples. GPS speed is not
an input to this classifier. The nominal constructor window is 25 samples.
"""
import math
import numpy as np
from vdr_preintegration import signed32


class MotionClassifier:
    def __init__(self):
        self.reset()

    def reset(self):
        self.raw = np.zeros((3, 4))
        self.filtered = np.zeros((25, 4))
        self.count = 0
        self.dirty = False
        self.accel_std = self.accel_range = -1.
        self.gyro_std = np.zeros(3)
        self.gyro_range = np.zeros(3)
        self.motion = self.stable = -1

    def push(self, gyro, accel):
        self.raw[:-1] = self.raw[1:]
        self.raw[-1] = [*gyro, math.sqrt(sum(value*value for value in accel))]
        if self.count:
            self.filtered[:-1] = self.filtered[1:]
        x = self.raw
        y = self.filtered
        if self.count == 0:
            y[-1] = x[-1]
        elif self.count == 1:
            y[-1] = .20657208382614792*x[-1] + .41314416765229584*x[-2] - y[-2]
        else:
            y[-1] = (.20657208382614792*x[-1] + .41314416765229584*x[-2]
                     + .20657208382614792*x[-3]
                     - (-.3695273773512414)*y[-2] - .19581571265583306*y[-3])
        self.count = min(25, self.count+1)
        self.dirty = True

    def evaluate(self):
        if self.dirty and self.count >= 25:
            deviations = np.std(self.filtered, axis=0)
            ranges = np.ptp(self.filtered, axis=0)
            self.accel_std, self.accel_range = float(deviations[3]), float(ranges[3])
            self.gyro_std, self.gyro_range = deviations[:3], ranges[:3]
            self.motion = int(not (self.accel_std < .02 and self.accel_range < .05
                                   and max(self.gyro_std) < .003490658503988659))
            self.stable = int(self.motion == 0 and max(self.gyro_range) < .003490658503988659)
            self.dirty = False
        return self.motion, self.stable


class MotionDetector:
    """Wrapper +779f3c/+77a100: window labels and optional gyro-bias estimate."""
    def __init__(self):
        self.classifier = MotionClassifier()
        self.detail = -1
        self.bias = np.zeros(3)
        self.bias_count = 0
        self.last_mean = np.zeros(3)
        self.last_bias_timestamp = 0

    def reset(self):
        # +77a0a0 deliberately retains the accumulated bias fields.
        self.classifier.reset()
        self.detail = -1

    def publish(self, integrated, *, estimate_bias=False, sample_vectors=()):
        motion, stable = self.classifier.evaluate()
        if motion == -1:
            self.detail = -1
        elif motion == 1:
            self.detail = 0
        else:
            self.detail = min(100, 1 if self.detail < 1 else self.detail+1)
        diagnostics = np.zeros(7)
        if len(sample_vectors):
            diagnostics[:3] = np.sum(np.asarray(sample_vectors, dtype=np.float32).astype(float), axis=0)
            diagnostics[3] = len(sample_vectors)
            # Native diagnostic fields are updated only after the first full window.
            if self.classifier.count >= 25:
                diagnostics[4:] = [self.classifier.accel_std, self.classifier.accel_range,
                                   max(self.classifier.gyro_std)]
        output_bias = None
        if estimate_bias:
            if signed32(integrated.timestamp-self.last_bias_timestamp) >= 1200001:
                self.bias[:] = 0.
                self.bias_count = 0
            if stable == 1 and integrated.count >= 5:
                mean = np.asarray(integrated.mean_gyro)
                if np.max(np.abs(mean-self.last_mean)) > .001:
                    self.bias[:] = 0.
                    self.bias_count = 0
                else:
                    total = signed32(self.bias_count+integrated.count)
                    self.bias += (mean-self.bias)*integrated.count/total
                    self.bias_count = total
                self.last_mean = mean.copy()
                self.last_bias_timestamp = integrated.timestamp
            if self.bias_count >= 25:
                output_bias = self.bias.copy()
        return motion, self.detail, stable, output_bias, diagnostics
