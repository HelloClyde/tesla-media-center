"""Bounded section-40 ring decoder (native 0x1ac2728/0x1ac2bb0).

Keeps precision and ring flags intact. Geographic expansion follows
154dd64 -> 14ae678 / 14ae788 -> 1adc464; paints bind via section 41.
"""
from bmd_geometry import Reader
from bmd_tile import directory


def surfaces(section):
    reader = Reader(section)
    count = reader.variable()
    if count > 4096:
        raise ValueError('too many surface styles')
    styles = [reader.integer(2) for _ in range(count)]
    groups = reader.variable()
    if groups > 10000:
        raise ValueError('too many surface groups')
    result, point_total, ring_total = [], 0, 0
    for group in range(groups):
        code, flags, width = reader.integer(4), reader.integer(2), reader.integer(1)
        count = reader.variable()
        if not 1 <= width <= 24 or count + len(result) > 100000:
            raise ValueError('unsupported surface group')
        for _ in range(count):
            style = reader.variable()
            if style >= len(styles):
                raise ValueError('invalid surface style')
            count_rings = reader.variable()
            ring_total += count_rings
            if count_rings > 10000 or ring_total > 100000:
                raise ValueError('too many rings')
            rings = []
            for _ in range(count_rings):
                count_points = reader.variable()
                point_total += count_points
                if not 1 <= count_points <= 100000 or point_total > 500000:
                    raise ValueError('invalid ring size')
                reader.begin_bits()
                x, y = reader.bits(width), reader.bits(width)
                mark, flag = reader.bits(1), reader.bits(1)
                delta_width = reader.bits(5) if count_points > 1 else 0
                reader.end_bits()
                points, marks = [[x, y]], [mark]
                reader.begin_bits()
                for _ in range(count_points - 1):
                    x += reader.bits(delta_width, signed=True)
                    y += reader.bits(delta_width, signed=True)
                    marks.append(reader.bits(1))
                    points.append([x, y])
                reader.end_bits()
                # Preserve the original sequence and flags. Closing rings or
                # assigning hole orientation belongs to the verified renderer.
                rings.append(dict(points=points, pointMarks=marks, ringFlag=flag))
            result.append(dict(group=group, groupCode=code, groupFlags=flags,
                               coordinateBits=width, style=styles[style], rings=rings))
    if reader.offset != len(section):
        raise ValueError('unconsumed surface bytes')
    return result


def decode(data):
    header = directory(data)
    entry = next((s for s in header['sections'] if s['kind'] == 40), None)
    if entry is None:
        raise ValueError('no surface section')
    start = header['bodyOffset'] + entry['offset']
    return surfaces(data[start:start + entry['size']])


def geographic_surfaces(data, grid, paints):
    from bmd_geometry import geographic_point
    from bmd_styles import style_bindings, section
    if not section(data, 40):
        return []
    features = decode(data)
    bindings = style_bindings(data, 41, len(features))
    result = []
    for index, feature in enumerate(features):
        width = feature['coordinateBits']
        if width not in (12, 13):
            raise ValueError('unsupported surface precision')
        key = bindings.get(index)
        colors = {theme: table[key] for theme, table in paints.items() if key in table}
        if not colors:
            continue
        # Native expansion scales by 2**(33-level-coordinateBits). Normalize
        # to the already seam-verified 13-bit road grid before projecting.
        factor = 2 ** (13 - width)
        rings = []
        for ring in feature['rings']:
            if len(ring['points']) < 3:
                continue
            rings.append([geographic_point([x * factor, y * factor], grid) for x, y in ring['points']])
        if rings:
            result.append({'rings': rings, 'paints': colors,
                           'minZoom': feature['style'] & 31,
                           'maxZoom': (feature['style'] >> 5) & 31})
    return result
