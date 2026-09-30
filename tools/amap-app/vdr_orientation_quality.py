"""Native 76c9e0 attitude feedback and 779ba4 quality publication.

Consumes native-frame gyro/acceleration, not browser geolocation substitutes.
"""
import math
import numpy as np
from vdr_initial_attitude import align_vectors
from vdr_posture_quality import PostureQuality
from vdr_state_transition import ObserverActivation


class OrientationFilter:
    def __init__(self, rate=25., gain_p=.5, gain_i=.01):
        self.rate, self.two_kp, self.two_ki = rate, 2 * gain_p, 2 * gain_i
        self.reset()

    def reset(self):
        self.initialized = False
        self.q = np.array([1., 0., 0., 0.])
        self.integral = np.zeros(3)

    def advance(self, gyro, accel):
        gyro = np.asarray(gyro, dtype=np.float32).astype(float)
        accel = np.asarray(accel, dtype=np.float32).astype(float)
        if not self.initialized:
            r = np.asarray(align_vectors(accel, [0., 0., 1.]))
            roll = math.atan2(r[2, 1], r[2, 2])
            pitch = math.atan2(-r[2, 0], math.hypot(r[2, 1], r[2, 2]))
            cr, sr = math.cos(roll / 2), math.sin(roll / 2)
            cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
            self.q = np.array([cr * cp, sr * cp, cr * sp, -sr * sp])
            self.q /= np.linalg.norm(self.q)
            self.initialized = True
        w, x, y, z = self.q
        if any(abs(a) > 1e-15 for a in accel):
            error = np.cross(accel / np.linalg.norm(accel),
                             [x * z - w * y, w * x + y * z, w * w - .5 + z * z])
            if self.two_ki > 0:
                self.integral += error * self.two_ki / self.rate
            else:
                self.integral[:] = 0
            gyro += self.two_kp * error + self.integral
        gx, gy, gz = gyro * (.5 / self.rate)
        self.q = np.array([w - x * gx - y * gy - z * gz,
                           x + w * gx + y * gz - z * gy,
                           y + w * gy - x * gz + z * gx,
                           z + w * gz + x * gy - y * gx])
        self.q /= np.linalg.norm(self.q)
        w, x, y, z = self.q
        return (x * z - y * w, y * z + x * w, .5 - x * x - y * y)


class OrientationQualityObserver:
    replay_enabled = True

    def __init__(self):
        self.activation = ObserverActivation(mask=62)
        self.reset()

    def reset(self):
        self.orientation = OrientationFilter()
        self.detector = PostureQuality()
        self.counter = 1

    @property
    def enabled(self):
        return self.activation.enabled

    def transition(self, timestamp, state):
        self.activation.transition(timestamp, state, lambda _: None, lambda _: self.reset())

    def sample(self, timestamp, gps, gyro, accel):
        posture = self.orientation.advance(gyro, accel)
        if self.detector.advance(timestamp, gyro, posture) == 0:
            self.counter = 0

    def publish(self, payload):
        payload.quality = self.counter
        if self.counter <= 99:
            self.counter += 1
