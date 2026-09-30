"""Ordinary full-initialization replay order from +7d7060 (mask 0x7f).

History already contains prepared native windows. The manager's before-predict
callback is mandatory; callers must supply its implementation or an explicitly
chosen test stub. Partial-mask restoration is not represented here.
"""
import copy
from dataclasses import dataclass, field
from vdr_filter import VdrFilter
from vdr_filter_update import CorrectionFilter
from vdr_filter_initialization import initial_covariances


@dataclass
class ReplayWindow:
    integrated: object
    gps: object
    observation: dict = field(default_factory=dict)
    direction: float = -1.


def initialize_and_replay(initialized, history, *, before_predict):
    """Build the initialized ordinary filter and replay chronological history.

    Equal timestamp: observe only. Later: callback, predict, observe with
    force=True. Earlier windows are ignored. Never sort or deduplicate history:
    the native ring's existing order is part of the input contract.
    """
    covariance, noise = initial_covariances()
    engine = VdrFilter(CorrectionFilter(copy.deepcopy(initialized), covariance),
                       base_noise=noise)
    for window in history:
        timestamp = window.integrated.timestamp
        if timestamp < initialized.timestamp:
            continue
        if timestamp > initialized.timestamp:
            before_predict(engine, window)
            engine.predict(window.integrated)
        observation = dict(window.observation)
        observation['force'] = True
        engine.observe(window.integrated, window.gps, **observation)
    return engine
