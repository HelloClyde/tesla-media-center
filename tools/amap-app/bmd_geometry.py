"""Experimental bounded BMD section 30 decoder, in local tile coordinates.

Native evidence: 0x1ac4138 groups, 0x1ac402c feature metadata,
0x1ac5e1c first point and signed bit-packed deltas, 0x1ac6038 suffix.
No native styles, name binding, or geographic projection are implied.
"""
from bmd_tile import LIMIT, directory
from route_v51 import varint


class Reader:
    def __init__(self, data):
        if len(data) > LIMIT:
            raise ValueError('section too large')
        self.data, self.offset, self.bit = data, 0, 0

    def integer(self, size):
        if self.offset + size > len(self.data):
            raise ValueError('truncated integer')
        value = int.from_bytes(self.data[self.offset:self.offset + size], 'little')
        self.offset += size
        return value

    def variable(self):
        value, self.offset = varint(self.data, self.offset)
        return value

    def begin_bits(self):
        self.bit = self.offset * 8

    def bits(self, width, signed=False):
        if not 0 <= width <= 31 or self.bit + width > len(self.data) * 8:
            raise ValueError('invalid bit field')
        value = 0
        for _ in range(width):
            value = (value << 1) | ((self.data[self.bit // 8] >> (7 - self.bit % 8)) & 1)
            self.bit += 1
        if signed and width and value & (1 << (width - 1)):
            value -= 1 << width
        return value

    def end_bits(self):
        self.offset = (self.bit + 7) // 8


def lines(section):
    reader = Reader(section)
    style_count = reader.variable()
    if style_count > 4096:
        raise ValueError('too many styles')
    styles = [reader.integer(2) for _ in range(style_count)]
    groups = reader.variable()
    if groups > 10000:
        raise ValueError('too many groups')
    features, total_points = [], 0
    for group in range(groups):
        group_code = reader.integer(4)
        group_flags = reader.integer(2)
        width = reader.integer(1)
        count = reader.variable()
        if not 1 <= width <= 24 or len(features) + count > 100000:
            raise ValueError('unsupported group')
        for _ in range(count):
            style = reader.variable()
            if style >= len(styles):
                raise ValueError('invalid style index')
            flags = reader.integer(1)
            name = reader.variable() if flags & 1 else None
            if flags & 2:
                reader.variable()
                reader.variable()
            alternate_name = None
            if flags & 32:
                alternate_name = name if flags & 16 else reader.variable()
            info = reader.integer(1)
            reader.integer(1)
            identity = reader.integer(8)
            point_count = reader.variable()
            total_points += point_count
            if point_count < 1 or point_count > 100000 or total_points > 500000:
                raise ValueError('unsupported point count')
            reader.begin_bits()
            x, y = reader.bits(width), reader.bits(width)
            delta_width = reader.bits(5) if point_count > 1 else 0
            reader.end_bits()
            points, marks = [[x, y]], [0]
            reader.begin_bits()
            for _ in range(point_count - 1):
                x += reader.bits(delta_width, signed=True)
                y += reader.bits(delta_width, signed=True)
                marks.append(reader.bits(1) if flags & 4 else 0)
                points.append([x, y])
            reader.end_bits()
            # Nonzero suffixes need the alternate native geometry branch.
            # Never silently skip them and risk shifting the next record.
            if reader.variable() != 0:
                raise ValueError('unsupported geometry suffix')
            features.append(dict(group=group, groupCode=group_code, groupFlags=group_flags,
                                 coordinateBits=width, style=styles[style], flags=flags, info=info, id=identity,
                                 nameIndex=name, alternateNameIndex=alternate_name,
                                 points=points, pointMarks=marks))
    if reader.offset != len(section):
        raise ValueError('unconsumed geometry bytes')
    return features


def decode(data):
    header = directory(data)
    entry = next((entry for entry in header['sections'] if entry['kind'] == 30), None)
    if entry is None:
        raise ValueError('no line section')
    start = header['bodyOffset'] + entry['offset']
    return lines(data[start:start + entry['size']])


def names(section):
    """Name table from 0x1abdf40 / 0x1abe0c8, including optional index arrays."""
    reader = Reader(section)
    count = reader.variable()
    if not 1 <= count <= 64:
        raise ValueError('invalid language count')
    reader.begin_bits()
    width = reader.bits(5)
    languages = []
    for _ in range(count):
        length = reader.bits(width)
        if not 1 <= length <= 64:
            raise ValueError('invalid language length')
        languages.append(bytes(reader.bits(8) for _ in range(length)).decode('utf-8'))
    reader.end_bits()
    count = reader.variable()
    if count > 100000:
        raise ValueError('too many names')
    result = []
    for _ in range(count):
        variants = reader.integer(1)
        if not 0 <= variants <= len(languages):
            raise ValueError('invalid name variants')
        reader.begin_bits()
        width = reader.bits(5)
        reader.end_bits()
        entry = {}
        for _ in range(variants):
            language = reader.variable()
            if language >= len(languages) or languages[language] in entry:
                raise ValueError('invalid name language')
            reader.begin_bits()
            length = reader.bits(width)
            reader.end_bits()
            if length > 4096:
                raise ValueError('name too long')
            text = bytes(reader.integer(1) for _ in range(length)).decode('utf-8')
            reader.begin_bits()
            alternate, phonetic = reader.bits(1), reader.bits(1)
            reader.end_bits()
            # 1abe37c: each optional name annotation is a count followed by
            # a 5-bit width and packed indices, all aligned as one bit stream.
            # They annotate pronunciation/layout, not the displayed UTF-8 name.
            for present in (alternate, phonetic):
                if present:
                    count = reader.variable()
                    if count > 4096:
                        raise ValueError('name annotation too long')
                    reader.begin_bits()
                    index_width = reader.bits(5)
                    for _ in range(count):
                        reader.bits(index_width)
                    reader.end_bits()
            entry[languages[language]] = text
        result.append(entry)
    if reader.offset != len(section):
        raise ValueError('unconsumed name bytes')
    return result


def geographic_point(point, grid, width=13):
    """Native geographic grid expansion (1adc464), with bounded known levels."""
    level, x, y = grid
    if level not in (3, 6, 8, 10, 12, 14) or any(type(v) is not int for v in grid) or not 0 <= x < 1 << level or not 0 <= y < 1 << level:
        raise ValueError('unsupported map grid')
    if width not in (11, 12, 13):
        raise ValueError('unsupported coordinate precision')
    px, py = point
    extent = 1 << (width - 1)
    if not 0 <= px <= extent or not 0 <= py <= extent / 2:
        raise ValueError('point outside validated tile extent')
    unit = 360 / (1 << (level + width - 1))
    return [(x * extent + px) * unit - 180,
            90 - (y + 1) * 180 / (1 << level) + py * unit]


def geographic_features(data, grid, paints=None):
    header = directory(data)
    entry = next((entry for entry in header['sections'] if entry['kind'] == 10), None)
    if not any(e['kind'] == 30 for e in header['sections']):
        return {'type': 'FeatureCollection', 'features': []}
    table = []
    if entry:
        start = header['bodyOffset'] + entry['offset']
        table = names(data[start:start + entry['size']])
    result = []
    decoded = decode(data)
    from bmd_roads import road_levels
    levels = road_levels(data, [len(f['points']) for f in decoded])
    from bmd_styles import style_bindings
    bindings = style_bindings(data, 31, len(decoded)) if paints is not None else {}
    for feature_number, feature in enumerate(decoded):
        index = feature['nameIndex']
        if index is not None and index >= len(table):
            raise ValueError('invalid road name index')
        label = '' if index is None else table[index].get('zh-Hans', next(iter(table[index].values()), ''))
        binding = bindings.get(feature_number)
        result.append({'type': 'Feature', 'properties': {'name': label, 'style': feature['style'],
                       **({'levelMarkers': levels[feature_number]} if feature_number in levels else {}),
                       **({'paintKey': f'{binding[0]}/{binding[1]}'} if binding else {})},
                       'geometry': {'type': 'LineString', 'coordinates': [geographic_point(p, grid, feature['coordinateBits']) for p in feature['points']]}})
    return {'type': 'FeatureCollection', 'features': result}


def preview(features):
    """Local-coordinate inspection SVG, never a geographically verified map."""
    from html import escape
    points = [point for feature in features for point in feature['points']]
    if not points:
        raise ValueError('empty geometry')
    left, top = min(p[0] for p in points), min(p[1] for p in points)
    width = max(p[0] for p in points) - left
    height = max(p[1] for p in points) - top
    if width <= 0 or height <= 0:
        raise ValueError('degenerate geometry')
    result = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="660" viewBox="{left-40} {top-200} {width+80} {height+240}">',
              '<rect x="-100000" y="-100000" width="200000" height="200000" fill="#101d26"/>',
              f'<text x="{left}" y="{top-75}" font-family="sans-serif" font-size="55" fill="#d8e8ef">App BMD · local geometry preview · {len(features)} lines</text>']
    for feature in features:
        if len(feature['points']) < 2:
            continue
        xy = ' '.join(f'{x},{y}' for x, y in feature['points'])
        title = escape(f"style {feature['style']}; name index {feature['nameIndex']}")
        result.append(f'<polyline points="{xy}" fill="none" stroke="#8bc9cf" stroke-width="3" stroke-linejoin="round"><title>{title}</title></polyline>')
    return '\n'.join(result + ['</svg>'])


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_tile', type=Path)
    parser.add_argument('--svg', required=True, type=Path)
    args = parser.parse_args()
    if args.decoded_tile.stat().st_size > LIMIT:
        parser.error('tile too large')
    result = decode(args.decoded_tile.read_bytes())
    args.svg.write_text(preview(result), encoding='utf-8')
    print(f"{len(result)} lines, {sum(len(f['points']) for f in result)} points; geographic alignment not yet verified")
