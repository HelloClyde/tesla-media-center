"""Pinned Amap polygon-distance primitives; not a complete navigation engine.

Addresses in libamaploc.so: inside 6918f4, cross 6919b4, distance
691afc, segment projection 691bf4, candidate selection 695f40/695e64.
Inputs must already be in the native local coordinate frame. The integer
cross-product conversion is deliberate, including its near-edge behavior.
"""
import math
import sys


def _fma(a, b, c):
    return math.fma(a, b, c) if hasattr(math, 'fma') else a * b + c


def _cross(a, b, p):
    value = _fma(b[0] - a[0], p[1] - a[1], -(b[1] - a[1]) * (p[0] - a[0]))
    # ARM64 FCVTZS to signed W register truncates and saturates.
    if math.isnan(value):
        return 0
    return int(max(-2147483648, min(2147483647, value)))


def _inside(point, vertices):
    previous = 0
    for i, a in enumerate(vertices):
        cross = _cross(a, vertices[(i + 1) % len(vertices)], point)
        if i and previous * cross < 0:
            return False
        if abs(cross) > 1e-7:
            previous = cross
    return True


def convex_hull(points):
    """691690: preserve <=3 inputs; otherwise sort by axis1 then axis0.

    Uses the native integer-truncated cross product, including near-collinear
    behavior. Duplicate points are not removed before building the hull.
    """
    points = [tuple(point) for point in points]
    if not all(len(point) == 2 and all(math.isfinite(v) for v in point) for point in points):
        raise ValueError('Hull points must be finite pairs')
    if len(points) <= 3:
        return points
    points.sort(key=lambda point: (point[1], point[0]))
    hull = []
    for point in points:
        while len(hull) >= 2 and _cross(hull[-2], hull[-1], point) < 1:
            hull.pop()
        hull.append(point)
    threshold = len(hull) + 1
    for point in reversed(points[:-1]):
        while len(hull) >= threshold and _cross(hull[-2], hull[-1], point) < 1:
            hull.pop()
        hull.append(point)
    return hull[:-1]


def project_segment(a, b, point):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_squared = _fma(dx, dx, dy * dy)
    if length_squared < 1e-6:
        return a
    t = _fma(point[0] - a[0], dx, (point[1] - a[1]) * dy) / length_squared
    if t < 0:
        return a
    if t > 1:
        return b
    return (_fma(dx, t, a[0]), _fma(dy, t, a[1]))


def polygon_distance(point, vertices):
    if not all(math.isfinite(v) for pair in (point, *vertices) for v in pair):
        raise ValueError('Local coordinates must be finite')
    if len(vertices) < 3:
        return sys.float_info.max
    if _inside(point, vertices):
        return 0.0
    distance = sys.float_info.max
    for i, a in enumerate(vertices):
        projected = project_segment(a, vertices[(i + 1) % len(vertices)], point)
        distance = min(distance, math.hypot(point[0] - projected[0], point[1] - projected[1]))
    return distance


def select_polygon(point, candidates, threshold):
    """Return (index, distance, accepted); retain candidate even if rejected.

    Mirrors native output-before-threshold behavior and first-candidate ties.
    Threshold units depend on the still-unresolved frame initialization.
    """
    best, distance = None, sys.float_info.max
    for index, vertices in enumerate(candidates):
        current = polygon_distance(point, vertices)
        if current < distance:
            best, distance = index, current
    return best, distance, best is not None and distance <= threshold
