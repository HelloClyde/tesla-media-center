"""Window GPS admission +7dbd14, with native validity and distance helpers."""
import copy
import math
from dataclasses import dataclass
from vdr_preintegration import signed32


@dataclass
class WindowGps:
    timestamp: int
    longitude: float
    latitude: float
    altitude: float = 0.
    speed: float = 0.
    kind: int = 0

    def valid(self):
        # This is the native sentinel check, not public API input validation.
        return (self.kind != -1 and self.timestamp >= 1 and
                not (abs(self.longitude-181.) < 2.220446049250313e-16 and
                     abs(self.latitude-91.) < 2.220446049250313e-16 and
                     abs(self.altitude) < 2.220446049250313e-16))


def native_distance(first, second):
    lon1, lat1 = first.longitude*math.pi/180., first.latitude*math.pi/180.
    lon2, lat2 = second.longitude*math.pi/180., second.latitude*math.pi/180.
    value = math.sin((lat2-lat1)*.5)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)*.5)**2
    return math.asin(math.sqrt(value))*12756274.


class WindowGpsGate:
    def __init__(self, minimum_interval=500):
        self.minimum_interval = minimum_interval
        self.previous = None

    def accept(self, incoming):
        if not incoming.valid():
            return False
        if self.previous is not None and self.previous.valid():
            if signed32(incoming.timestamp-self.previous.timestamp) < self.minimum_interval:
                return False
            if native_distance(self.previous, incoming) < .01 and incoming.speed > 1.:
                return False
        self.previous = copy.deepcopy(incoming)
        return True
