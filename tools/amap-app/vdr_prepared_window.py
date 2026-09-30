"""Construct root observer windows using verified 77376c/7737dc defaults."""
import copy
import numpy as np
from vdr_motion_observer import MotionWindow
from vdr_window_dispatch import DispatchWindow
from vdr_window_observation import FilterGps


def empty_gps():
    return FilterGps(-1000, 181., 91., kind=-1)


def prepare_window(window):
    gps = copy.deepcopy(window.gps) if window.gps is not None else empty_gps()
    payload = MotionWindow(copy.deepcopy(window.integrated), gps=gps,
        quality=-1, motion=-1, detail=0, stable=-1, direction=-1.,
        preferred=np.full((3, 3), 10000.), fallback=np.full((3, 3), 10000.),
        gyro_bias=np.zeros(3), maximum_sample_gap=window.maximum_sample_gap)
    return DispatchWindow(gps, payload, copy.deepcopy(window.samples))
