"""Extract raw boundary triples from a native-decoded LNDS tile FlatBuffer.

Offline research only. Root slot 3 contains byte vectors holding nested
FlatBuffers (123d96c -> 106f448). Nested slot 8 contains boundaries
(105b8bc), boundary slot 1 contains segments (105b8fc), segment slot 1
contains geometry (1057460 -> 1058424). Preserve Z without assigning units.
"""
import argparse
import json
import struct
from pathlib import Path

from lane_boundary_points import LIMIT, boundary_points


def extract_boundaries(data):
    if not isinstance(data, bytes) or not 8 <= len(data) <= LIMIT:
        raise ValueError('invalid tile buffer')
    budget = [200000]

    def read(fmt, offset, end):
        size = struct.calcsize('<' + fmt)
        if offset < 0 or offset + size > end:
            raise ValueError('read outside FlatBuffer')
        return struct.unpack_from('<' + fmt, data, offset)[0]

    def pointer(table, slot, start, end):
        if not start <= table < end:
            raise ValueError('table outside FlatBuffer')
        vtable = table - read('i', table, end)
        if vtable < start:
            raise ValueError('vtable outside FlatBuffer')
        size = read('H', vtable, end)
        obj_size = read('H', vtable + 2, end)
        if size < 4 or size % 2 or vtable + size > end or obj_size < 4 or table + obj_size > end:
            raise ValueError('invalid table size')
        if 4 + slot * 2 >= size:
            return None
        offset = read('H', vtable + 4 + slot * 2, end)
        if not offset:
            return None
        if not 4 <= offset <= obj_size - 4:
            raise ValueError('invalid field offset')
        field = table + offset
        relative = read('I', field, end)
        target = field + relative
        if relative < 4 or target + 4 > end:
            raise ValueError('invalid relative pointer')
        return target

    def vector(table, slot, start, end):
        value = pointer(table, slot, start, end)
        if value is None:
            return []
        count = read('I', value, end)
        budget[0] -= count
        if budget[0] < 0 or count > (end - value - 4) // 4:
            raise ValueError('invalid vector size')
        result = []
        for i in range(count):
            field = value + 4 + i * 4
            rel = read('I', field, end)
            if rel < 4 or field + rel + 4 > end:
                raise ValueError('invalid vector element')
            result.append(field + rel)
        return result

    root = read('I', 0, len(data))
    lines, points = [], 0
    objects = vector(root, 3, 0, len(data))
    for blob in objects:
        length = read('I', blob, len(data))
        start, end = blob + 4, blob + 4 + length
        if length < 8 or end > len(data):
            raise ValueError('invalid nested FlatBuffer')
        nested = start + read('I', start, end)
        for boundary in vector(nested, 8, start, end):
            for segment in vector(boundary, 1, start, end):
                geometry = pointer(segment, 1, start, end)
                if geometry is None:
                    continue
                # Restrict the existing point reader to this nested buffer.
                line = boundary_points(data[start:end], geometry - start)
                points += len(line)
                if points > 1000000:
                    raise ValueError('too many boundary points')
                if line:
                    lines.append(line)
    return {'objects': len(objects), 'segments': len(lines),
            'points': points, 'coordinateSystem': 'unverified',
            'heightUnits': 'unverified', 'lines': lines}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = extract_boundaries(Path(args.input).read_bytes())
    Path(args.output).write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'lines'}))
