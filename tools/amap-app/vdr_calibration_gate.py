"""Adaptive calibration trigger +7bdc40 and histories +7bdbe8."""
from vdr_weighted_history import WeightedHistory


class CalibrationGate:
    def __init__(self):
        self.motion = WeightedHistory(.8)
        self.errors = WeightedHistory(.9)

    def reset(self):
        self.motion.reset()
        self.errors.reset()

    def update(self, first_error, second_error, motion):
        triggered = False
        if self.motion.total_weight >= 5.:
            a, b = self.errors.mean()
            old_motion = self.motion.mean()[0]
            triggered = (motion > 2.*old_motion and a < 1.4 and b < 1.4
                         and ((first_error >= 2. and abs(first_error) > 2.*a)
                              or (second_error >= 2. and abs(second_error) > 2.*b)))
        self.motion.add([motion])
        self.errors.add([abs(first_error), abs(second_error)])
        return triggered
