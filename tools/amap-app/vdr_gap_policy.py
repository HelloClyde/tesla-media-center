"""77b728 gate and ordinary 7d6f00 diagonal covariance inflation."""
import numpy as np


def inflate_gap_covariance(covariance):
    result = np.array(covariance, dtype=float, copy=True)
    if result.shape != (21, 21):
        raise ValueError('Expected a 21x21 covariance')
    result[np.arange(9), np.arange(9)] += [100000.]*3 + [250000.]*3 + [2000000.]*3
    return result


class GapPolicy:
    def __init__(self, *, enabled):
        self.enabled = enabled

    def __call__(self, engine, window):
        if self.enabled and window.maximum_sample_gap >= 301:
            engine.correction.covariance = inflate_gap_covariance(engine.correction.covariance)
