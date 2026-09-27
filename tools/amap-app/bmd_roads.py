"""Road point-level markers, NOT measured elevations or lane counts.

Native 17.00.0.2005: attribute 40 at 1aba224 (uvarint, signed byte),
1ac44e8 -> RoadFeature+0x78, 1ac628c -> point+0x10, absent=-1000.
154f130/154f1bc closes spans when the marker changes; -1/0 are not
elevated spans. Preserve markers separately from longitude/latitude.
"""
from bmd_geometry import Reader
from bmd_styles import attribute_block


def road_levels(data, point_counts):
    raw = attribute_block(data, 31, 40)
    if not raw:
        return {}
    reader = Reader(raw)
    mode, count = reader.integer(1), reader.variable()
    if mode not in (1, 2) or count > 500000:
        raise ValueError('unsupported road level attributes')
    result, total = {}, 0
    for _ in range(count):
        size = reader.variable() if mode == 2 else 1
        if not 1 <= size <= len(point_counts) or total + size > 500000:
            raise ValueError('too many road level references')
        indexes = [reader.variable() for _ in range(size)]
        point, value = reader.variable(), reader.integer(1)
        value = value - 256 if value >= 128 else value
        for index in indexes:
            if index >= len(point_counts) or point >= point_counts[index]:
                raise ValueError('invalid road level reference')
            markers = result.setdefault(index, {})
            if point in markers:
                raise ValueError('duplicate road level point')
            markers[point] = value
        total += size
    if reader.offset != len(raw):
        raise ValueError('unconsumed road level bytes')
    return {index: [[point, value] for point, value in sorted(markers.items())]
            for index, markers in result.items()}
