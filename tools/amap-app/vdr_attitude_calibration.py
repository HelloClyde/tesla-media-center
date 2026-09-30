"""Batch attitude calibration from libamaploc +7bd500.

Window assembly (+7bd1a4) remains external. Inputs are calibrated device
IMU vectors and interpolated speed, before gravity-frame rotation.
"""
import math
from vdr_heading_alignment import HeadingAlignment
from vdr_initial_attitude import align_vectors, attitude_from_acceleration
from vdr_preintegration import multiply, transform, transpose
from vdr_weighted_history import WeightedHistory


class AttitudeCalibration:
    def __init__(self):
        # +7bd064 constructor: rate 5, acceptance weight 2, gravity decay .99.
        self.heading = HeadingAlignment(5., 2)
        self.gravity = WeightedHistory(.99)
        self.rotation = None

    def advance(self, acceleration, gyro, speed):
        if len(acceleration) != 375 or len(gyro) != 375 or len(speed) != 375:
            raise ValueError('Expected 375 paired samples per native calibration window')
        mean = [sum(a[k] for a in acceleration) / len(acceleration) for k in range(3)]
        self.gravity.add(mean)
        gravity = self.gravity.mean()
        if gravity is None:
            return self.rotation
        aligned = align_vectors(gravity, (0., 0., 1.))
        if not all(math.isfinite(v) for row in aligned for v in row):
            # Explicit adapter safeguard, not a claim that native +7bd500
            # implements this recovery for degenerate align_vectors inputs.
            return self.rotation
        acc = [transform(aligned, value) for value in acceleration]
        gyr = [transform(aligned, value) for value in gyro]
        candidate = self.heading.advance(acc, gyr, speed)
        if candidate is not None and candidate[0] >= 0:
            radians = -candidate[0] * (math.pi / 180.)
            c, s = math.cos(radians), math.sin(radians)
            yaw = [[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]
            # +7bed28 stores the transposed dynamic-matrix product.
            self.rotation = transpose(multiply(yaw, aligned))
        return self.rotation


class CalibrationWindow:
    """Queue/interpolation portion of +7bd1a4 after GPS validity checks.

    gps_speed=None means no accepted fix. Fix validity/accuracy filtering
    remains upstream. The independent five-second fallback uses all samples.
    """
    def __init__(self):
        self.previous_fix = None
        self.pending = []
        self.acceleration = []
        self.gyro = []
        self.speed = []
        self.calibration = AttitudeCalibration()
        self.batches = 0
        self.fallback_history = WeightedHistory(.99)
        self.fallback_started = -1
        self.fallback_ready = False
        self.fallback_rotation = None

    def advance(self, timestamp, gyro, acceleration, gps_speed=None):
        self.fallback_history.add(acceleration)
        if gps_speed is not None:
            if self.previous_fix is not None:
                previous_time, previous_speed = self.previous_fix
                delta = ((timestamp - previous_time + 2**31) % 2**32) - 2**31
                if 1 <= delta < 3000:
                    slope = (gps_speed - previous_speed) / (delta * .001)
                    for time, g, a in self.pending:
                        elapsed = ((time - previous_time + 2**31) % 2**32) - 2**31
                        self.gyro.append(g)
                        self.acceleration.append(a)
                        self.speed.append(previous_speed + elapsed * .001 * slope)
            self.pending.clear()
            self.previous_fix = timestamp, gps_speed
        self.pending.append((timestamp, tuple(gyro), tuple(acceleration)))
        if len(self.pending) > 100:
            self.pending.clear()
            self.previous_fix = None
        if len(self.speed) > 375:
            self.calibration.advance(self.acceleration[:375], self.gyro[:375], self.speed[:375])
            del self.acceleration[:375]
            del self.gyro[:375]
            del self.speed[:375]
            self.batches += 1
        if self.fallback_started == -1:
            self.fallback_started = timestamp
        elif not self.fallback_ready:
            elapsed = ((timestamp - self.fallback_started + 2**31) % 2**32) - 2**31
            if elapsed > 5000:
                mean = self.fallback_history.mean()
                if mean is not None:
                    self.fallback_rotation = attitude_from_acceleration(*mean)
                self.fallback_ready = True
        return self.calibration.rotation
