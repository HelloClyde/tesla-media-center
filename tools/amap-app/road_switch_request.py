"""Pinned APK startAvoidLink sampling and XML fragment.

Verified primitives from libamaphorus 0xc660c8 / 0xc671c0. This is not a
nearby-road generator or a complete navigation reroute request. The caller
must provide a confirmed current link, native hwflag and switchaction.
"""
from __future__ import annotations

import math
import struct
from collections.abc import Sequence

SCALE = 3600000


def _i32(value):
    if type(value) is not int or not -(1 << 31) <= value < 1 << 31:
        raise ValueError('invalid native coordinate word')
    return value


def _wrap_i32(value):
    return (value + (1 << 31)) % (1 << 32) - (1 << 31)


def avoid_link_pair(points: Sequence[Sequence[int]]) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Native integer coordinate pair selected for one old link.

    The route getter supplies integer points, not screen/Mercator pixels.
    Short links use 50%/80% of the first edge. Longer links use the second
    and third-from-last vertices. Preserve native signed-word arithmetic.
    """
    if not isinstance(points, (tuple, list)) or len(points) > 100000:
        raise ValueError('invalid native link geometry')
    if any(not isinstance(point, (tuple, list)) or len(point) != 2 for point in points):
        raise ValueError('invalid native point')
    points = [tuple(_i32(value) for value in point) for point in points]
    if len(points) < 2:
        return None
    if len(points) > 4:
        return points[1], points[-3]
    first, second = points[:2]
    return (tuple(math.trunc(_wrap_i32(a + b) / 2) for a, b in zip(first, second)),
            tuple(math.trunc(a / 5 + _wrap_i32(b << 2) / 5) for a, b in zip(first, second)))


def encode_start_avoid_link(pairs: Sequence[Sequence[Sequence[int]]], hwflag: int, switchaction: int) -> bytes:
    """Match native iksemel field order and float32 %f serialization.

    These flags belong to RerouteOption, not the AJX LocSwitch command enum.
    Their values are supplied by a verified navigation context, never guessed
    from altitude or a UI button's numeric action ID.
    """
    if any(type(value) is not int or not 0 <= value <= 255 for value in (hwflag, switchaction)):
        raise ValueError('invalid native switch byte')
    if not isinstance(pairs, (list, tuple)) or not 1 <= len(pairs) <= 16:
        raise ValueError('invalid avoid-link pair count')
    # The native function sign-extends the uint8 arguments before formatting.
    signed = lambda value: value if value < 128 else value - 256
    chunks = [f'<startAvoidLink hwflag="{signed(hwflag)}" switchaction="{signed(switchaction)}">']
    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2 or any(
                not isinstance(point, (tuple, list)) or len(point) != 2 for point in pair):
            raise ValueError('invalid avoid-link pair')
        chunks.append('<linkPoint>')
        for key, value in zip(('x1', 'y1', 'x2', 'y2'), [word for point in pair for word in point]):
            word = _i32(value)
            coordinate = struct.unpack('<f', struct.pack('<f', word / SCALE))[0]
            chunks.append(f'<{key}>{coordinate:.6f}</{key}>')
        chunks.append('</linkPoint>')
    return (''.join(chunks) + '</startAvoidLink>').encode('ascii')
