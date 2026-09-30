"""State handlers 77bf00/77bf70 and decision flow of 77bd0c.

State8's matrix difference and reinitialization are required callbacks: their
native side effects cannot be replaced by a state assignment alone.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionRequest:
    state: int
    reason: int = 0
    forced: int = 0


def waiting_transition(quality, *, fast_start=False):
    if quality > 5 if fast_start else quality >= 20:
        return TransitionRequest(4)
    return None


def aligned_transition(quality):
    return TransitionRequest(32, 16) if quality == 0 else None


def fallback_transition(quality, preferred, *, retain_on_quality_loss,
                        select_history, maximum_attitude_difference,
                        threshold, reinitialize, notify_reinitialized):
    if quality == 0:
        return (TransitionRequest(32, 8) if retain_on_quality_loss
                else TransitionRequest(2, 0, 3))
    record = select_history()
    available = preferred[0][0] < 100.
    reason = int(record is not None) | (int(available) << 1)
    if not available:
        return TransitionRequest(8, reason)
    if maximum_attitude_difference(preferred) <= threshold:
        return TransitionRequest(16)
    if record is None:
        return TransitionRequest(8, reason)
    # 78fd60 reset/7b483c full restore must finish before event and transition.
    reinitialize(record)
    notify_reinitialized()
    return TransitionRequest(16, 0, 1)
