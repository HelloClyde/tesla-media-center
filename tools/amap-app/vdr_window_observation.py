"""Translate prepared window fields to the ordinary 7d64a0 call contract.

This is an internal adapter: GPS fields already use native units and flags.
Browser permission, coordinate datum and sensor axes are handled upstream.
"""
from dataclasses import dataclass
from vdr_direction_observer import DirectionGps
from vdr_observation_dispatch import GpsObservation
from vdr_observation_binding import ObservationBinding


@dataclass
class FilterGps(DirectionGps):
    flag18: bool = False
    heading_sigma_degrees: float = -1.


class WindowObservation:
    def __init__(self, *, config, flag1, flag2):
        self.config = config
        self.binding = ObservationBinding(flag1, flag2)

    def bind(self, source):
        self.binding.bind(source)

    def __call__(self, window):
        flag1, flag2 = self.binding.refresh()
        source = window.gps
        if source is None:
            gps = GpsObservation()
        else:
            gps = GpsObservation(valid=source.valid(), flag18=source.flag18,
                longitude=source.longitude, latitude=source.latitude,
                altitude=source.altitude, speed=source.speed,
                direction=source.direction, position_sigma=source.position_sigma,
                heading_sigma_degrees=source.heading_sigma_degrees)
        return gps, dict(calibration_state=window.quality, config=self.config,
            direction=window.direction, motion=window.motion, motion_detail=window.detail,
            gyro=tuple(window.integrated.latest_gyro), flag1=flag1, flag2=flag2)
