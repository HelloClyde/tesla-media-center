"""Read 694814's packed tunnel payload, preserving unresolved field semantics.

Projection requires explicit original local-frame parameters; no map datum or
axis ordering is inferred from browser longitude/latitude.
"""
import struct
from tunnel_local_coordinates import local_coordinates
from tunnel_polygon_matching import convex_hull


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def project(records, origin0_radians, origin1_radians, scale0, scale1):
    """694cec..694e34: project samples, then construct their native hull."""
    result = []
    for record in records:
        samples = [{**sample, 'local': local_coordinates(*sample['coordinates'],
                    origin0_radians, origin1_radians, scale0, scale1)}
                   for sample in record['samples']]
        result.append({**record, 'samples': samples,
                       'polygon': convex_hull([sample['local'] for sample in samples])})
    return result


def decode(data):
    if not isinstance(data, bytes) or len(data) < 4:
        raise ValueError('Missing tunnel payload count')
    count = struct.unpack_from('<I', data)[0]
    if count > (len(data) - 4) // 8:
        raise ValueError('Truncated tunnel scalar table')
    scalars = struct.unpack_from(f'<{count}d', data, 4)
    position = 4 + count * 8
    records = []
    for index in range(count):
        if len(data) - position < 53:
            raise ValueError('Truncated tunnel header')
        endpoints = struct.unpack_from('<4d', data, position)
        samples = struct.unpack_from('<H', data, position + 32)[0]
        attribute = data[position + 34]
        reserved = data[position + 35:position + 37]
        baselines = struct.unpack_from('<4f', data, position + 37)
        position += 53
        if samples > (len(data) - position) // 28:
            raise ValueError('Truncated tunnel sample array')
        readings = []
        for _ in range(samples):
            values = struct.unpack_from('<Hdd5h', data, position)
            readings.append({'id': values[0], 'coordinates': values[1:3],
                             'packed_values': values[3:],
                             'scalar': float32(baselines[0] + values[3] / 100),
                             'value': float32(values[4] / 100),
                             'vector': tuple(float32(baselines[i+1] + values[i+5] / 50)
                                             for i in range(3))})
            position += 28
        records.append({'scalar': scalars[index], 'endpoints': endpoints,
                        'attribute': attribute, 'reserved': reserved,
                        'baselines': baselines, 'samples': readings})
    if position != len(data):
        raise ValueError('Unparsed tunnel payload tail')
    return records
