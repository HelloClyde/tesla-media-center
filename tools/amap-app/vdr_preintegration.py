"""Translation of ordinary VDR IMU preintegration at libamaploc +7cf594.

This produces relative rotation/velocity/displacement and bias derivatives,
and propagates a local pose with externally supplied gravity and biases.
It does not produce a geodetic navigation fix: initial alignment, gravity
estimation, GPS fusion and road matching are not implemented here.
"""
from dataclasses import dataclass, field
import math
from vdr_sample_calibration import f32


def zero_matrix():
    return [[0.0] * 3 for _ in range(3)]


def identity():
    return [[float(r == c) for c in range(3)] for r in range(3)]


def add(a, b):
    return [[a[r][c] + b[r][c] for c in range(3)] for r in range(3)]


def scale(a, value):
    return [[x * value for x in row] for row in a]


def multiply(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def transpose(a):
    return [list(row) for row in zip(*a)]


def transform(a, v):
    return [sum(a[r][k] * v[k] for k in range(3)) for r in range(3)]


def skew(v):
    x, y, z = v
    return [[0., -z, y], [z, 0., -x], [-y, x, 0.]]


def rotation_and_right_jacobian(phi):
    """Native +763320/+7639ec formulas, including the 1e-8 branch."""
    angle = math.sqrt(sum(v * v for v in phi))
    if angle < 1e-8:
        cross = skew(phi)
        return add(identity(), cross), add(identity(), scale(cross, -.5))
    axis = [v / angle for v in phi]
    cross = skew(axis)
    outer = [[a * b for b in axis] for a in axis]
    sine, cosine = math.sin(angle), math.cos(angle)
    rotation = add(add(scale(identity(), cosine), scale(outer, 1. - cosine)), scale(cross, sine))
    sinc = sine / angle
    jacobian = add(add(scale(identity(), sinc), scale(outer, 1. - sinc)),
                   scale(cross, -(1. - cosine) / angle))
    return rotation, jacobian


@dataclass
class Preintegration:
    rotation_gyro_derivative: list = field(default_factory=zero_matrix)  # +000
    velocity_gyro_derivative: list = field(default_factory=zero_matrix)  # +048
    velocity_accel_derivative: list = field(default_factory=zero_matrix)  # +090
    position_gyro_derivative: list = field(default_factory=zero_matrix)  # +0d8
    position_accel_derivative: list = field(default_factory=zero_matrix)  # +120
    rotation: list = field(default_factory=identity)  # +168
    velocity: list = field(default_factory=lambda: [0.] * 3)  # +1b0
    position: list = field(default_factory=lambda: [0.] * 3)  # +1c8
    gyro_bias: list = field(default_factory=lambda: [0.] * 3)  # +1e0
    accel_bias: list = field(default_factory=lambda: [0.] * 3)  # +1f8
    mean_gyro: list = field(default_factory=lambda: [0.] * 3)  # +210
    mean_accel: list = field(default_factory=lambda: [0.] * 3)  # +228
    timestamp: int = 0  # +260
    initial_timestamp: int = 0  # +264
    count: int = 0  # +268
    latest_gyro: list = field(default_factory=lambda: [0.] * 3)  # +250, float32

    def advance(self, timestamp, gyro, accel):
        """Consume paired native samples; timestamp uses internal milliseconds.

        First sample initializes time only. Native does not reject negative or
        repeated deltas here; freshness checks belong to upstream components.
        """
        gyro, accel = [list(map(f32, values)) for values in (gyro, accel)]
        self.latest_gyro = gyro[:]
        timestamp = signed32(timestamp)
        if self.initial_timestamp <= 0:
            self.initial_timestamp = self.timestamp = timestamp
            return False
        dt = signed32(timestamp - self.timestamp) * .001
        phi = [(v - b) * dt for v, b in zip(gyro, self.gyro_bias)]
        dv = [(v - b) * dt for v, b in zip(accel, self.accel_bias)]
        delta_rotation, right_jacobian = rotation_and_right_jacobian(phi)
        cross_term = multiply(multiply(self.rotation, skew(dv)), self.rotation_gyro_derivative)
        self.position_accel_derivative = add(self.position_accel_derivative,
            add(scale(self.velocity_accel_derivative, dt), scale(self.rotation, -.5 * dt * dt)))
        self.position_gyro_derivative = add(self.position_gyro_derivative,
            add(scale(self.velocity_gyro_derivative, dt), scale(cross_term, -.5 * dt)))
        self.velocity_accel_derivative = add(self.velocity_accel_derivative, scale(self.rotation, -dt))
        self.velocity_gyro_derivative = add(self.velocity_gyro_derivative, scale(cross_term, -1.))
        self.rotation_gyro_derivative = add(multiply(transpose(delta_rotation), self.rotation_gyro_derivative),
                                            scale(right_jacobian, -dt))
        rotated_dv = transform(self.rotation, dv)
        self.position = [p + v * dt + .5 * a * dt for p, v, a in zip(self.position, self.velocity, rotated_dv)]
        self.velocity = [v + a for v, a in zip(self.velocity, rotated_dv)]
        self.rotation = multiply(self.rotation, delta_rotation)
        self.timestamp = timestamp
        self.count += 1
        self.mean_gyro = [old + (v - old) / self.count for old, v in zip(self.mean_gyro, gyro)]
        self.mean_accel = [old + (v - old) / self.count for old, v in zip(self.mean_accel, accel)]
        return True


def signed32(value):
    return (value + 2**31) % 2**32 - 2**31


@dataclass
class PoseState:
    """Local-frame state used by +78b9b8; position is not longitude/latitude."""
    rotation: list = field(default_factory=identity)
    velocity: list = field(default_factory=lambda: [0.] * 3)
    position: list = field(default_factory=lambda: [0.] * 3)
    gyro_bias: list = field(default_factory=lambda: [0.] * 3)
    accel_bias: list = field(default_factory=lambda: [0.] * 3)


def advance_pose(pose, integrated, gravity):
    """Translate +78b9b8 bias correction and local-frame state propagation.

    Gravity must be supplied in the same local frame as the pose; deriving that
    frame and initializing gravity from live navigation is a separate stage.
    """
    gyro_difference = [a - b for a, b in zip(pose.gyro_bias, integrated.gyro_bias)]
    accel_difference = [a - b for a, b in zip(pose.accel_bias, integrated.accel_bias)]

    def corrected(vector, gyro_derivative, accel_derivative):
        a = transform(gyro_derivative, gyro_difference)
        b = transform(accel_derivative, accel_difference)
        return [z + (x + y) for x, y, z in zip(vector, a, b)]

    dp = corrected(integrated.position, integrated.position_gyro_derivative, integrated.position_accel_derivative)
    dv = corrected(integrated.velocity, integrated.velocity_gyro_derivative, integrated.velocity_accel_derivative)
    correction_rotation = rotation_and_right_jacobian(transform(integrated.rotation_gyro_derivative, gyro_difference))[0]
    corrected_rotation = multiply(integrated.rotation, correction_rotation)
    dt = signed32(integrated.timestamp - integrated.initial_timestamp) * .001
    world_dp, world_dv = transform(pose.rotation, dp), transform(pose.rotation, dv)
    return PoseState(
        rotation=multiply(pose.rotation, corrected_rotation),
        velocity=[v + a + g * dt for v, a, g in zip(pose.velocity, world_dv, gravity)],
        position=[p + d + v * dt + (.5 * g) * (dt * dt)
                  for p, d, v, g in zip(pose.position, world_dp, pose.velocity, gravity)],
        gyro_bias=pose.gyro_bias[:], accel_bias=pose.accel_bias[:])
