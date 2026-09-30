"""77bfc4 recovery-state control flow, with explicit restoration dependencies.

Callbacks must install native partial-mask state/covariance before transition.
This module does not approximate the 7bde68 recovery estimator.
"""
from vdr_running_states import TransitionRequest
from vdr_state_transition import signed32


def recover(manager, window, *, allow_fallback_recovery, tolerate_missing,
            recovery_timeout, restore_aligned, restore_fallback, transition):
    timestamp = window.integrated.timestamp
    if manager.reason == 16:
        if window.quality >= 1 and restore_aligned(window):
            transition(TransitionRequest(16))
        # Native checks these after restoration, against the updated state time.
        missing_expired = window.missing_fix and (
            not tolerate_missing or window.missing_duration > 10000)
        deadline = signed32(manager.state_since + recovery_timeout)
        if missing_expired or timestamp > deadline:
            transition(TransitionRequest(2, 0, 4))
    if allow_fallback_recovery and manager.reason == 8:
        # ARM b.lt also rejects unordered FCMP results (NaN).
        if window.quality >= 6 and window.direction >= 0:
            restore_fallback(window)
            transition(TransitionRequest(8))
        if window.missing_fix or timestamp > signed32(manager.state_since + 10000):
            transition(TransitionRequest(2, 0, 5))
