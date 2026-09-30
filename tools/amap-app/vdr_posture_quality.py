"""Posture stability detector7bf738/7bfa44, before quality-counter publication."""
import math
from collections import deque
import numpy as np
from vdr_gyro_quality_gate import GyroQualityGate
from vdr_state_transition import signed32


def vector_angle(first, second):
    dot = sum(a * b for a, b in zip(first, second))
    denominator = math.sqrt(sum(v * v for v in first)) * math.sqrt(sum(v * v for v in second)) + 1e-8
    ratio = dot / denominator
    return math.acos(ratio) * 180. / math.pi if -1 <= ratio <= 1 else math.nan


class PostureQuality:
    def __init__(self):
        self.gyro = GyroQualityGate()
        self.postures = deque(maxlen=25)
        self.changes = deque(maxlen=25)
        self.last_evaluation = -1000

    @property
    def status(self):
        return self.gyro.status

    def stability(self):
        if len(self.postures) < 25:
            return -1
        mean = np.mean(self.postures, axis=0)
        angles = [vector_angle(value, mean) for value in self.postures]
        return int(np.std(self.changes) < 2 and np.std(angles) < 3 and max(angles) < 15)

    def advance(self, timestamp, gyro, posture):
        timestamp = signed32(timestamp)
        posture = tuple(posture)
        previous = self.postures[-1] if self.postures else posture
        self.changes.append(vector_angle(previous, posture))
        self.postures.append(posture)
        recovered = self.gyro.advance(timestamp, gyro)
        if signed32(timestamp - self.last_evaluation) >= 1000:
            self.last_evaluation = timestamp
            stable = self.stability()
            self.gyro.status = int(stable == 1 and recovered)
            if self.gyro.status:
                self.gyro.last_trigger = -1000
            elif stable == 0:
                self.gyro.last_trigger = timestamp
        return self.status
