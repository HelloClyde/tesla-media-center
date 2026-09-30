"""Root state routing from 77b628 with real initialization and recovery.

Configuration and root notification side effects are explicit. This controller
consumes prepared native windows; it does not synthesize browser sensor data.
"""
from dataclasses import dataclass
import math
import numpy as np
from vdr_initialization_history import select_initialization_record
from vdr_initialization_handoff import initialize_from_windows
from vdr_initialization_replay import initialize_and_replay
from vdr_pose_initialization import initialize_pose
from vdr_running_states import (TransitionRequest, waiting_transition,
                                aligned_transition, fallback_transition)
from vdr_recovery_state import recover
from vdr_recovery_candidate import AlignedRecovery, restore_fallback


def maximum_attitude_difference(preferred, current):
    """77bd80..77bde4: max absolute Euler angle of preferred * current.T."""
    rotation = np.asarray(preferred) @ np.asarray(current).T
    return max(abs(math.degrees(angle)) for angle in (
        math.atan2(rotation[2, 1], rotation[2, 2]),
        math.atan2(-rotation[2, 0], math.hypot(rotation[2, 1], rotation[2, 2])),
        math.atan2(rotation[1, 0], rotation[0, 0])))


@dataclass(frozen=True)
class StateConfiguration:
    fast_start: bool
    retain_on_quality_loss: bool
    allow_fallback_recovery: bool
    tolerate_missing: bool
    recovery_timeout: int
    attitude_threshold: float
    preserve_recovery_covariance: bool
    gyro_bias_variance: float
    accel_bias_variance: float


class StateController:
    def __init__(self, manager, records, history, quality, configuration, *,
                 can_replay, transition,
                 notify_reinitialized, reset_manager):
        self.manager, self.records, self.history = manager, records, history
        self.quality, self.configuration = quality, configuration
        self.can_replay, self.transition = can_replay, transition
        self.notify_reinitialized = notify_reinitialized
        self.reset_manager = reset_manager
        self.aligned_recovery = AlignedRecovery()

    def __call__(self, filter_manager, window):
        config = self.configuration
        timestamp = window.integrated.timestamp

        def change(request):
            if request is not None:
                self.transition(request.state, timestamp, request.reason, request.forced)

        def selected():
            return select_initialization_record(self.records, self.can_replay)

        def reset():
            self.quality.reset()
            self.reset_manager()

        def reinitialize(record):
            latest = self.records[-1]
            pose = initialize_pose(record.timestamp, record.direction, record.speed,
                record.origin, latest.preferred, latest.fallback, latest.gyro_bias)
            reset()
            filter_manager.install(initialize_and_replay(pose, self.history,
                before_predict=self.quality.before_predict))

        state = self.manager.state
        if state == 2:
            change(waiting_transition(window.quality, fast_start=config.fast_start))
        elif state == 4:
            if window.quality == 0:
                change(TransitionRequest(2, forced=2))
                return
            result = initialize_from_windows(self.records, self.history, window,
                can_replay=self.can_replay, reset_manager=reset,
                before_predict=self.quality.before_predict)
            if result is not None:
                filter_manager.install(result.engine)
                change(TransitionRequest(result.state))
            else:
                # 77bcac: report history/preferred/fallback availability bits.
                # An attempted but invalid pose leaves state/reason untouched.
                record = selected()
                preferred = window.preferred[0][0] < 100.
                fallback = window.fallback[0][0] < 100.
                if record is None or not (preferred or fallback):
                    reason = int(record is not None) | int(preferred) << 1 | int(fallback) << 2
                    change(TransitionRequest(4, reason))
        elif state == 8:
            change(fallback_transition(window.quality, window.preferred,
                retain_on_quality_loss=config.retain_on_quality_loss,
                select_history=selected,
                maximum_attitude_difference=lambda matrix:
                    maximum_attitude_difference(matrix, filter_manager.state.calibration),
                threshold=config.attitude_threshold, reinitialize=reinitialize,
                notify_reinitialized=lambda: self.notify_reinitialized(timestamp, 1)))
        elif state == 16:
            change(aligned_transition(window.quality))
        elif state == 32:
            engine = filter_manager.engine
            covariance = engine.correction.covariance
            options = dict(preserve_covariance=config.preserve_recovery_covariance,
                gyro_bias_variance=config.gyro_bias_variance,
                accel_bias_variance=config.accel_bias_variance)
            recover(self.manager, window,
                allow_fallback_recovery=config.allow_fallback_recovery,
                tolerate_missing=config.tolerate_missing,
                recovery_timeout=config.recovery_timeout,
                restore_aligned=lambda w: self.aligned_recovery.restore(
                    engine, w, covariance, **options),
                restore_fallback=lambda w: restore_fallback(engine, w, covariance, **options),
                transition=change)
