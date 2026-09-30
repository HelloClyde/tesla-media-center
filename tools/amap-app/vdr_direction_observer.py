"""779d40 default GPS-direction observer (configuration bit 1 clear).

Direction is the native east-zero angle in degrees; no H5 datum/unit inference.
The alternate 782ae0 estimator must be supplied explicitly when enabled.
"""
import copy
import math
from dataclasses import dataclass
from vdr_state_transition import ObserverActivation, signed32
from vdr_window_gps import WindowGps, native_distance


@dataclass
class DirectionGps(WindowGps):
    direction: float = -1.
    position_sigma: float = 0.
    direct_direction: bool = False
    zero_speed_valid: bool = False


class DirectionObserver:
    replay_enabled = False

    def __init__(self, alternate=None):
        self.activation = ObserverActivation(mask=63)
        self.alternate = alternate
        self.reset()

    def reset(self):
        self.last_valid = -1000
        self.previous = None

    @property
    def enabled(self):
        return self.activation.enabled

    def transition(self, timestamp, state):
        self.activation.transition(timestamp, state, lambda _: None, lambda _: self.reset())

    def publish(self, payload):
        gps = payload.gps
        valid = gps is not None and gps.valid()
        if valid:
            self.last_valid = payload.integrated.timestamp
            payload.missing_fix, payload.missing_duration = False, 0
        else:
            elapsed = signed32(payload.integrated.timestamp - self.last_valid)
            if elapsed > 5000.:
                payload.missing_fix, payload.missing_duration = True, elapsed
            return
        if gps.zero_speed_valid and gps.speed == 0:
            payload.direction = gps.direction
            return
        if self.alternate is not None:
            if self.alternate(gps):
                payload.direction = gps.direction
            return
        previous = self.previous
        self.previous = copy.deepcopy(gps)
        if gps.direct_direction:
            payload.direction = gps.direction
            return
        if gps.position_sigma > 20 or gps.speed < 3 or gps.direction < 0:
            return
        if gps.speed >= 5:
            payload.direction = gps.direction
            return
        if previous is None or not previous.valid():
            return
        distance = native_distance(previous, gps)
        heading = math.degrees(math.atan2(gps.latitude - previous.latitude,
                    (gps.longitude - previous.longitude) * math.cos(math.radians(previous.latitude)))) % 360
        difference = abs((heading - gps.direction + 180) % 360 - 180)
        if (signed32(gps.timestamp - previous.timestamp) <= 1500 and
                gps.position_sigma <= 20 and previous.position_sigma <= 20 and
                distance >= 5 and difference <= 10):
            payload.direction = gps.direction
