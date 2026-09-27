"""Read an already-decoded native boundary point table (offline only).

The input is NOT a downloaded LNDS block. The native boundary accessor
104b5e4/104b5ec reads FlatBuffers slot 0 (vtable offset 4); 104b624 reads a
vector of 24-byte structures, returning three doubles without conversion.
Coordinate meaning/units are intentionally not assigned here.
"""
import math
import struct

LIMIT = 16 * 1024 * 1024
MAX_POINTS = 100000


def boundary_points(buffer, table_offset):
    if not isinstance(buffer, bytes) or len(buffer) > LIMIT:
        raise ValueError('invalid boundary buffer')
    if type(table_offset) is not int:
        raise ValueError('invalid table offset')

    def read(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset > len(buffer) - size:
            raise ValueError('boundary read outside buffer')
        return struct.unpack_from(fmt, buffer, offset)

    vtable = table_offset - read('<i', table_offset)[0]
    vtable_size, object_size = read('<HH', vtable)
    if vtable_size < 4 or vtable_size % 2 or object_size < 4:
        raise ValueError('invalid boundary table size')
    if vtable > len(buffer) - vtable_size or table_offset > len(buffer) - object_size:
        raise ValueError('boundary table outside buffer')
    if vtable_size == 4:
        return []
    field_offset = read('<H', vtable + 4)[0]
    if not field_offset:
        return []
    if field_offset < 4 or field_offset > object_size - 4:
        raise ValueError('invalid boundary vector field')
    field = table_offset + field_offset
    relative = read('<I', field)[0]
    if relative < 4:
        raise ValueError('invalid boundary vector offset')
    vector = field + relative
    count = read('<I', vector)[0]
    if count > MAX_POINTS or count > (len(buffer) - vector - 4) // 24:
        raise ValueError('invalid boundary point count')
    result = []
    for index in range(count):
        point = read('<3d', vector + 4 + index * 24)
        if not all(math.isfinite(value) for value in point):
            raise ValueError('non-finite boundary point')
        result.append(point)
    return result
