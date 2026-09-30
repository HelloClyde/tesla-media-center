"""Paired-IMU window scheduling from +7dbebc (ordinary configuration).

Produces primary/look-ahead preintegrations and synchronously publishes them
before refreshing bias histories; no GPS-only IMU is synthesized.
"""
import copy
from dataclasses import dataclass, field
from vdr_preintegration import Preintegration, signed32
from vdr_preintegration_composition import compose
from vdr_window_gps import WindowGpsGate
from vdr_window_dispatch import SamplePair
from vdr_sample_calibration import f32
from vdr_weighted_history import WeightedHistory


def empty_integration(timestamp=-1, gyro_bias=(0., 0., 0.), accel_bias=(0., 0., 0.)):
    return Preintegration(timestamp=timestamp, initial_timestamp=timestamp,
                          gyro_bias=list(gyro_bias), accel_bias=list(accel_bias))


@dataclass
class InputWindow:
    integrated: Preintegration = field(default_factory=empty_integration)
    gps: object = None
    samples: list = field(default_factory=list)
    maximum_sample_gap: int = 0


class WindowProducer:
    def __init__(self, *, interval=500, lookahead=240, maximum_gap=200,
                 on_publish=None):
        self.interval, self.lookahead, self.maximum_gap = interval, lookahead, maximum_gap
        self.gps_gate = WindowGpsGate()
        self.current = InputWindow()
        self.retained = InputWindow()
        self.last_timestamp = -1
        self.deadline = -1000
        self.gyro_bias = [0., 0., 0.]
        self.accel_bias = [0., 0., 0.]
        self.gyro_history = WeightedHistory(.9)
        self.accel_history = WeightedHistory(.9)
        self.last_bias_refresh = -1000
        self.bias_refresh_interval = 30000
        self.on_publish = on_publish

    def feedback_bias(self, timestamp, gyro, accel):
        """7dbe34: accumulate filter feedback; timestamp belongs to the caller."""
        self.gyro_history.add(gyro)
        self.accel_history.add(accel)

    def _restart_current(self, timestamp, refresh=False):
        if (timestamp >= 1 and refresh and
                signed32(timestamp-self.last_bias_refresh) > self.bias_refresh_interval):
            self.last_bias_refresh = timestamp
            self.gyro_bias = self.gyro_history.mean() or [0., 0., 0.]
            self.accel_bias = self.accel_history.mean() or [0., 0., 0.]
        self.current = InputWindow(empty_integration(timestamp, self.gyro_bias, self.accel_bias))

    def push(self, timestamp, gyro, accel, gps=None, *, relaxed_gap=False):
        """Return publications and an optional (current, previous) gap event."""
        timestamp = signed32(timestamp)
        gps_accepted = gps is not None and self.gps_gate.accept(gps)
        elapsed = 0 if self.last_timestamp < 0 else signed32(timestamp-self.last_timestamp)
        publications, gap = [], None
        def publish(primary, lookahead):
            pair = copy.deepcopy(primary), copy.deepcopy(lookahead)
            publications.append(pair)
            # Native listeners run before the GPS branch refreshes the biases.
            if self.on_publish is not None:
                self.on_publish(*pair)

        if elapsed > (1000 if relaxed_gap else self.maximum_gap):
            if self.retained.integrated.count >= 1:
                publish(self.retained, InputWindow())
                self.retained = InputWindow()
            self._restart_current(-1)
            gap = timestamp, self.last_timestamp
            self.deadline = signed32(timestamp+self.interval)
        self.current.maximum_sample_gap = max(self.current.maximum_sample_gap,
            signed32(timestamp-self.current.integrated.timestamp))
        self.current.integrated.advance(timestamp, gyro, accel)
        self.current.samples.append(SamplePair(timestamp, tuple(map(f32, gyro)), tuple(map(f32, accel))))
        if gps_accepted:
            self.current.gps = copy.deepcopy(gps)
            if self.retained.integrated.count >= 1:
                self.current.integrated = compose(self.retained.integrated, self.current.integrated)
                self.current.samples = self.retained.samples + self.current.samples
                # Extended-window composition constructs fresh auxiliary fields.
                self.current.maximum_sample_gap = 0
                self.retained = InputWindow()
            publish(self.current, InputWindow())
            self._restart_current(timestamp, refresh=True)
            self.deadline = signed32(timestamp+self.interval)
        elif timestamp >= signed32(self.deadline+self.lookahead):
            if self.retained.integrated.count >= 1:
                publish(self.retained, self.current)
                self.retained = InputWindow()
                self.deadline = signed32(self.deadline+self.interval)
        elif timestamp >= self.deadline and self.retained.integrated.count <= 0:
            self.retained = copy.deepcopy(self.current)
            self._restart_current(timestamp)
        self.last_timestamp = timestamp
        return publications, gap
