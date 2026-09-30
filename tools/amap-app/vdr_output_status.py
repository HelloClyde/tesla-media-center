"""Output status update +77b114; flags retain native, unnamed semantics.

Estimator readiness is +5a0, not 'neural model loaded' or a confidence threshold.
Do not reinterpret this status as proof of accurate real-world navigation.
"""
from dataclasses import dataclass
from vdr_state_transition import signed32


@dataclass
class OutputStatus:
    active: bool = False      # root+58
    motion: int = -1          # root+5c
    quality_positive: bool = False  # root+60
    missing_fix: bool = False # root+64
    flag65: bool = False
    flag66: bool = False

    def update(self, state, timestamp, estimator_ready, *, unstable_delay=0,
               reference_timestamp=0, window=None):
        events = []
        active = bool(state in (8, 16, 32) and estimator_ready)
        flag65 = active and state != 32
        flag66 = active and (state == 16 or (
            state == 8 and unstable_delay > 0
            and signed32(timestamp - reference_timestamp) > unstable_delay))
        motion, quality, missing = self.motion, self.quality_positive, self.missing_fix
        if window is not None:
            quality = window.quality > 0
            motion, missing = window.motion, bool(window.missing_fix)
            if quality != self.quality_positive:
                events.append(3 if quality else 2)
        if motion != self.motion and motion in (0, 1):
            events.append(8 if motion == 0 else 9)
        if missing != self.missing_fix:
            events.append(10 if missing else 11)
        if flag65 != self.flag65:
            events.append(4 if flag65 else 5)
        if flag66 != self.flag66:
            events.append(6 if flag66 else 7)
        self.active, self.motion, self.quality_positive = active, motion, quality
        self.missing_fix, self.flag65, self.flag66 = missing, flag65, flag66
        return events
