"""Observation selection from +7d657c..+7d6748, after lifecycle preparation.

Coordinates, flags and motion classification retain native meanings. Callers
must reanchor first and supply stationary history/preintegration produced by
the native lifecycle; neither is inferred from browser speed being zero.
"""
from dataclasses import dataclass
import math
from vdr_heading_observation import heading_observation
from vdr_velocity_observation import velocity_observation
from vdr_position_observation import position_observation, horizontal_position_observation
from vdr_stationary_observation import stationary_observation
from vdr_vehicle_observation import vehicle_observation
from vdr_stationary_attitude_observation import stationary_attitude_observation
from vdr_stationary_bias_observation import stationary_bias_observation
from vdr_preintegration import signed32


@dataclass
class GpsObservation:
    valid: bool = False
    flag18: bool = False
    longitude: float = 0.
    latitude: float = 0.
    altitude: float = 0.
    speed: float = -1.
    direction: float = -1.
    position_sigma: float = 100.
    heading_sigma_degrees: float = -1.


def observation_blocks(state, gps, *, config=0, calibrate=True, direction=-1.,
                       motion=1, gyro=(0., 0., 0.), flag1=False, flag2=False,
                       force=False, stationary_reference=None, stationary_integrated=None,
                       motion_detail=0, extra_position=None):
    """Return ordered blocks and whether the ordinary GPS position was used.

extra_position is native type-8 (longitude, latitude, altitude, sigma).
Stationary arguments are snapshots after the history/IMU window update.
"""
    blocks = []
    if calibrate:
        variance = -1.
        if config & 0x40 and gps.valid and .001 < gps.heading_sigma_degrees < 180.:
            variance = (gps.heading_sigma_degrees * math.pi / 180.)**2
        heading = heading_observation(state, direction, variance, flag2 and not force)
        if heading is not None:
            blocks.append(heading)
        if config & 0x10 and gps.valid and not gps.flag18 and gps.direction >= 0 and 0 <= gps.speed < 100:
            blocks.append(velocity_observation(state, gps.speed, gps.direction))
        if motion == 0:
            blocks.append(stationary_observation(state))
            if flag1:
                if motion_detail >= 2 and stationary_integrated is not None:
                    elapsed = signed32(stationary_integrated.timestamp-stationary_integrated.initial_timestamp)
                    if elapsed >= 1900:
                        blocks.append(stationary_bias_observation(state, stationary_integrated))
            elif stationary_reference is not None:
                blocks.append(stationary_attitude_observation(state, stationary_reference))
        else:
            blocks.append(vehicle_observation(state, gyro, flag1 and not force, False))
    used_gps_position = False
    if gps.valid and not gps.flag18:
        sigma = gps.position_sigma
        if config & 0x20 or sigma <= 20.:
            if config & 0x20:
                sigma *= .3
            blocks.append(position_observation(state, gps.longitude, gps.latitude, gps.altitude, sigma))
            used_gps_position = True
    if extra_position is not None:
        blocks.append(horizontal_position_observation(state, *extra_position))
    return blocks, used_gps_position
