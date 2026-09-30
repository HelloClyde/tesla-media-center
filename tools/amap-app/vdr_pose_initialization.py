"""State-building path +77b86c through +77b98c, excluding its logging tail.

direction_degrees is the native solution's direction field, not assumed to
be the H5 compass heading. Conversion of that source field is upstream.
"""
from dataclasses import dataclass
import math
from vdr_local_frame import LocalFrame
from vdr_preintegration import PoseState, multiply, transform, transpose


@dataclass
class InitializedPose:
    timestamp: int
    pose: PoseState
    frame: LocalFrame
    calibration: list
    auxiliary: tuple = (1.5, 0., 0.)
    flags: int = 0x7f


def initialize_pose(timestamp, direction_degrees, speed, origin,
                    preferred, fallback, gyro_bias):
    calibration = preferred if preferred[0][0] < 100. else fallback
    angle = direction_degrees * (math.pi / 180.)
    c, s = math.cos(angle), math.sin(angle)
    yaw = [[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]
    pose = PoseState(rotation=multiply(yaw, transpose(calibration)),
                     velocity=transform(yaw, [speed, 0., 0.]),
                     gyro_bias=list(gyro_bias))
    return InitializedPose(timestamp, pose, LocalFrame(*origin),
                           [row[:] for row in calibration])
