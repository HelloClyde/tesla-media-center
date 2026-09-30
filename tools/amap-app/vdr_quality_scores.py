"""777a9c score cadence and embedded linear evaluation.

Feature generation and three history-ready flags come from the upstream
manager. An unavailable neural model remains -1, independently of linear score.
"""
from vdr_quality_inference import quality_inference
from vdr_state_transition import signed32


class QualityScores:
    def __init__(self, parameters, *, interval=1000, backend=None):
        self.parameters = parameters
        self.interval = interval
        self.backend = backend
        self.reset()

    def reset(self):
        self.primary = self.secondary = -1.
        self.last_evaluation = -1
        self.ready = False

    def activate(self):
        # 777bf0: only the first valid-pose callback initializes scores.
        if not self.ready:
            self.ready = True
            self.primary, self.secondary = .1, 0.

    def evaluate(self, timestamp, gps_valid, ready_flags, features):
        if not all(ready_flags):
            return False
        timestamp = signed32(timestamp)
        if not gps_valid and signed32(timestamp - self.last_evaluation) < self.interval:
            return False
        values = features()
        self.primary = quality_inference(values, self.backend)
        if gps_valid:
            if len(values) < 55:
                raise ValueError('Native linear score requires 55 features')
            p = self.parameters
            score = p['bias']
            for value, mean, scale, coefficient in zip(values[:55], p['means'], p['scales'], p['coefficients']):
                score += (value - mean) / scale * coefficient
            self.secondary = 0. if score < 0 else score
        self.last_evaluation = timestamp
        return True
