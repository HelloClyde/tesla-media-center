"""History selection +77ba80 and pose-building handoff to +77b86c.

The caller supplies native quality/availability decisions. This is not an
alternative to the missing upstream quality observer or initialization replay.
"""
from dataclasses import dataclass
import copy
from typing import Callable
from vdr_pose_initialization import initialize_pose


@dataclass
class InitializationRecord:
    timestamp: int
    direction: float
    eligible: bool
    speed: float
    origin: tuple
    preferred: object
    fallback: object
    gyro_bias: object


def record_from_window(window):
    """77b58c: snapshot the published window; eligibility is quality != 0.

The caller supplies native unavailable-matrix and empty-GPS representations.
Do not infer missing matrices or sensor bias from GPS.
"""
    gps = window.gps
    return InitializationRecord(
        timestamp=window.integrated.timestamp, direction=window.direction,
        eligible=window.quality != 0, speed=gps.speed,
        origin=(gps.longitude, gps.latitude, gps.altitude),
        preferred=copy.deepcopy(window.preferred), fallback=copy.deepcopy(window.fallback),
        gyro_bias=copy.deepcopy(window.gyro_bias))


def select_initialization_record(records, can_replay: Callable[[int], bool]):
    """Newest-to-oldest scan, retaining the oldest qualifying contiguous fix.

    An ineligible record ends the scan; negative/NaN direction merely skips
    that record. Replay availability is checked only for nonnegative headings.
    """
    selected = None
    for record in reversed(records):
        if not record.eligible:
            break
        if record.direction >= 0 and can_replay(record.timestamp):
            selected = record
    return selected


def prepare_initialization(records, can_replay, *, current_quality,
                           preferred, fallback):
    """Return (initialized pose, requested state) after the known init gates.

    This does not install the pose in a live filter: the manager must restore
    covariance and replay intervening windows before exposing a current fix.
    """
    if current_quality == 0 or not (preferred[0][0] < 100 or fallback[0][0] < 100):
        return None
    record = select_initialization_record(records, can_replay)
    if record is None:
        return None
    # 77b8bc/77b8c0 select the ring's latest slot for calibration and bias;
    # x21 remains the historical record supplying time/direction/GPS.
    latest = records[-1]
    initialized = initialize_pose(record.timestamp, record.direction, record.speed,
                                  record.origin, latest.preferred, latest.fallback,
                                  latest.gyro_bias)
    if initialized.timestamp < 1:
        return None
    if not (initialized.frame.east_scale > 0 or initialized.flags):
        return None
    return initialized, 16 if preferred[0][0] < 100 else 8
