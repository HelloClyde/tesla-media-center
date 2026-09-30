"""Native +767e30 sample conversion, preserving ARM64 float32 arithmetic.

The calibration function is shared by accelerometer and gyroscope inputs.
This module is deliberately not a browser-input adapter.
"""
import struct


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def calibrate_sample(primary, alternate, cached_bias=None):
    """Return (values, alternate_used, new_bias).

    All three alternate values > 900 is the native sentinel condition. Otherwise
    the first alternate-primary difference is retained as the bias, and the
    current alternate values are corrected with that retained bias.
    """
    if len(primary) != 3 or len(alternate) != 3:
        raise ValueError('Expected two three-component samples')
    primary = tuple(map(f32, primary))
    alternate = tuple(map(f32, alternate))
    if cached_bias is not None:
        if len(cached_bias) != 3:
            raise ValueError('Expected a three-component bias')
        cached_bias = tuple(map(f32, cached_bias))
    if all(value > 900.0 for value in alternate):
        return primary, False, cached_bias
    if cached_bias is None:
        cached_bias = tuple(f32(a - p) for a, p in zip(alternate, primary))
    result = tuple(f32(a - b) for a, b in zip(alternate, cached_bias))
    return result, True, cached_bias


def prepare_sensor_sample(kind, primary, alternate, cached_bias=None):
    """Translate +769cbc/+769da8 value handling after native event conversion.

    kind is the verified JNI source (setAcce/setGyro), not Android's numeric
    Sensor.TYPE_* enum. Accelerometer values use the native input scale;
    the handler multiplies by float32 9.8 (consistent with g to m/s², but the
    caller's unit contract has not been independently checked). Gyroscope units
    are not changed here.
    Returns None for an accelerometer sample rejected by the native zero gate.
    Bias is stored in the scaled units, separately for each kind.
    """
    if kind not in ('accelerometer', 'gyroscope'):
        raise ValueError('Unknown native sensor kind')
    if len(primary) != 3 or len(alternate) != 3:
        raise ValueError('Expected two three-component samples')
    primary = tuple(map(f32, primary))
    alternate = tuple(map(f32, alternate))
    if kind == 'accelerometer':
        if not any(abs(value) > 1e-6 for value in primary):
            return None
        scale = f32(9.8)
        primary = tuple(f32(value * scale) for value in primary)
        alternate = tuple(f32(value * scale) for value in alternate)
    return calibrate_sample(primary, alternate, cached_bias)
