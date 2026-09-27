"""Offline port of IndexModel bounds math, not a datum conversion.

libamapr.so 17.00.0.2005: 0x1446a34 (bit unpack), 0x1446ab4 (bounds),
0x1446b80 (angular scaling). No GCJ/WGS datum assumption is made.
"""


def signed32(value):
    value &= 0xffffffff
    return value - (1 << 32) if value & (1 << 31) else value


def index_bounds(identity, width, height):
    if type(identity) is not int or not 0 <= identity < (1 << 63):
        raise ValueError('invalid packed index coordinate')
    if any(type(v) is not int or not 0 <= v <= 0x7fffffff for v in (width, height)):
        raise ValueError('invalid index extent')
    x = sum(((identity >> (2 * bit)) & 1) << bit for bit in range(32))
    y = sum(((identity >> (2 * bit + 1)) & 1) << bit for bit in range(31))
    # Preserve the native unsigned comparison, including its boundary behavior.
    if ((y + 0xbffffffe) & 0xffffffff) < 0x7ffffffe:
        y |= 0x80000000
    x, y = signed32(x), signed32(y)

    def lon(value):
        value = signed32(value)
        return value * (1 / 2147483647 if value >= 0 else 1 / 2147483648) * 180

    def lat(value):
        value = signed32(value)
        return value * (1 / 1073741823 if value >= 0 else 1 / 1073741824) * 90

    half_w, half_h = width // 2, height // 2
    low_y, high_y = signed32(y - half_h), signed32(y + half_h)
    south, north = lat(high_y), lat(low_y)
    if low_y > high_y:
        south, north = north, south
    # Matches native slots exactly: west, upper-y, east, lower-y. Do not sort
    # or wrap these into a geographic bounding box without validating the datum.
    return [lon(x - half_w), south, lon(x + half_w), north]
