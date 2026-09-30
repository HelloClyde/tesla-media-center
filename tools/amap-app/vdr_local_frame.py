"""Ordinary VDR local-frame conversion (+78b238/+78b278/+78b2e0).

Coordinates keep the source fix's datum; these functions do not convert
WGS84/GCJ-02 or establish the source fix's datum on their own.
"""
from dataclasses import dataclass
import math

METRES_PER_DEGREE = 111319.49079327358
INITIAL_GRAVITY = (0.0, 0.0, -9.80665)  # ELF initializer +7b30f0


@dataclass(frozen=True)
class LocalFrame:
    longitude: float
    latitude: float
    altitude: float

    @property
    def east_scale(self):
        # Retain the native multiply-then-divide order from +762750.
        return math.cos((self.latitude * math.pi) / 180.0) * METRES_PER_DEGREE

    def project(self, longitude, latitude, altitude):
        """Return local east/north/up relative to this origin."""
        return ((longitude - self.longitude) * self.east_scale,
                (latitude - self.latitude) * METRES_PER_DEGREE,
                altitude - self.altitude)

    def unproject(self, east, north, up):
        return (east / self.east_scale + self.longitude,
                north / METRES_PER_DEGREE + self.latitude,
                up + self.altitude)
