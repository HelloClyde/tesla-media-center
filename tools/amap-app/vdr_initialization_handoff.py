"""Join native history selection, pose creation and ordinary full replay.

Manager quality callbacks remain required dependencies. This handoff is not
the entire root state machine or the browser input adapter.
"""
from dataclasses import dataclass
from vdr_initialization_history import prepare_initialization
from vdr_initialization_replay import initialize_and_replay


@dataclass
class InitializationResult:
    engine: object
    state: int
    initial_timestamp: int


def initialize_from_windows(records, history, current, *, can_replay,
                            reset_manager, before_predict):
    prepared = prepare_initialization(records, can_replay,
        current_quality=current.quality, preferred=current.preferred,
        fallback=current.fallback)
    if prepared is None:
        return None
    pose, state = prepared
    # Manager slot28 precedes covariance reset and chronological replay.
    reset_manager()
    engine = initialize_and_replay(pose, history, before_predict=before_predict)
    return InitializationResult(engine, state, pose.timestamp)
