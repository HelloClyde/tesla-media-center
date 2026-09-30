"""Local-coordinate primitive used by the pinned APK tunnel matcher.

libamaploc.so+0x69f404, called from +0x6ae718. Input axis ordering and
scale initialization must still be traced before connecting this to H5 positions.
This function does not predict a position or identify a tunnel.
"""
import math
import struct

# Exact binary64 constant read from libamaploc.so+0x7bc78.
DEGREES_TO_RADIANS = 0.0174532925199433


def initialize_packed_frame(origin: bytes) -> tuple[float, float, float, float]:
    """Decode +6aa8f4's int32/int32/float32 input without changing datum."""
    if not isinstance(origin, bytes) or len(origin) != 12:
        raise ValueError('Packed frame origin must contain exactly 12 bytes')
    first, second, altitude = struct.unpack('<iif', origin)
    return initialize_frame(second / 10000000.0, first / 10000000.0, altitude)


def initialize_frame(axis0_degrees: float, axis1_degrees: float,
                     altitude: float) -> tuple[float, float, float, float]:
    """Port +6ada54; input datum/provider is not established by this function.

    Return origins in radians followed by the two curvature scales. The
    initializer uses a different rounded radian constant from the projector.
    """
    if not all(math.isfinite(v) for v in (axis0_degrees, axis1_degrees, altitude)):
        raise ValueError('Frame origin must be finite')
    angle = axis0_degrees * 0.017453292519943295
    sine = math.sin(angle)
    coefficient = -0.006694380004260925
    fma = getattr(math, 'fma', None)
    squared = sine * sine
    denominator = fma(squared, coefficient, 1.0) if fma else squared * coefficient + 1.0
    scale0 = 6335439.327202763 / math.sqrt(math.pow(denominator, 3.0)) + altitude
    scale1 = math.cos(angle) * (6378137.0 / math.sqrt(denominator) + altitude)
    return angle, axis1_degrees * 0.017453292519943295, scale0, scale1


def local_coordinates(axis0_degrees: float, axis1_degrees: float,
                      origin0_radians: float, origin1_radians: float,
                      scale0: float, scale1: float) -> tuple[float, float]:
    values = (axis0_degrees, axis1_degrees, origin0_radians, origin1_radians, scale0, scale1)
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Coordinates and frame parameters must be finite')
    # Native FNMSUB fuses multiply/subtract. On Python without math.fma,
    # the separated operations may differ by rounding; verified with tolerance.
    fma = getattr(math, 'fma', None)
    delta0 = fma(axis0_degrees, DEGREES_TO_RADIANS, -origin0_radians) if fma else axis0_degrees * DEGREES_TO_RADIANS - origin0_radians
    delta1 = fma(axis1_degrees, DEGREES_TO_RADIANS, -origin1_radians) if fma else axis1_degrees * DEGREES_TO_RADIANS - origin1_radians
    return delta0 * scale0, delta1 * scale1
