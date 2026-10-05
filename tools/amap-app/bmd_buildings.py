"""Bounded level-15 type-5 building decoder, BMD chapters 50/51.

libamapr: ReadShape 15a5f3c, ReadFeature 15a63ec, ParseBuilding 15a66a8.
This path does not use the unrelated legacy type-3 multi-data format.
"""
import math
from bmd_geometry import Reader
from bmd_tile import directory


class BuildingReader(Reader):
    def v32(self, signed=False):
        # Native 1448b58 stops after FIVE bytes, including negative i32 values
        # whose fifth byte still has bit 7 set. The generic u64 reader cannot
        # be substituted here (it consumes the following field).
        value = 0
        for i in range(5):
            byte = self.integer(1)
            value |= (byte & 127) << (7 * i)
            if byte < 128 or i == 4:
                value &= 0xffffffff
                return value - (1 << 32) if signed and value & (1 << 31) else value

    def count(self, maximum):
        value = self.v32()
        if value > maximum:
            raise ValueError('building count limit')
        return value


def building_section(data):
    r = BuildingReader(data)
    width = r.integer(1)
    if not 11 <= width <= 20:
        raise ValueError('unsupported building precision')
    shapes, point_total = [], 0
    for _ in range(r.count(10000)):
        if r.v32() != 1:  # The native shape parser also requires one contour.
            raise ValueError('unsupported building contour')
        count = r.count(10000)
        point_total += count
        if count < 3 or point_total > 200000:
            raise ValueError('building point limit')
        r.begin_bits()
        x, y = r.bits(width), r.bits(width)
        marks, flag = [r.bits(1)], r.bits(1)
        delta = r.bits(5)
        r.end_bits()
        points = [[x, y]]
        r.begin_bits()
        for _ in range(count - 1):
            x += r.bits(delta, signed=True)
            y += r.bits(delta, signed=True)
            marks.append(r.bits(1))
            points.append([x, y])
        r.end_bits()
        # Native retains ceil(pointCount/8) edge flags even if unused by style.
        edges = r.integer((count + 7) // 8)
        shapes.append(dict(points=points, marks=marks, flag=flag, edges=edges))
    features, part_total = [], 0
    for _ in range(r.count(4096)):
        style = r.integer(4)
        for _ in range(r.count(10000)):
            if len(features) >= 20000:
                raise ValueError('building feature limit')
            identity = str(r.integer(8))
            shape, height = r.v32(), r.v32()
            count = r.integer(2)
            part_total += count
            if part_total > 50000:
                raise ValueError('building part limit')
            lengths = [r.count(65536) for _ in range(count)]
            parts, unsupported = [], 0
            for length in lengths:
                end = r.offset + length
                if length < 1 or end > len(data):
                    raise ValueError('invalid building part length')
                kind = r.integer(1)
                if kind == 1:
                    part = dict(shape=r.v32(), scaleX=r.v32(), scaleY=r.v32(),
                                dx=r.v32(signed=True), dy=r.v32(signed=True),
                                angle=r.integer(2), base=r.v32(), height=r.v32(), flags=r.integer(1))
                    if part['shape'] >= len(shapes):
                        raise ValueError('invalid building shape reference')
                    parts.append(part)
                else:
                    unsupported += 1
                if r.offset > end:
                    raise ValueError('building part overflow')
                r.offset = end
            if not count:
                parts.append(dict(shape=shape, scaleX=10000, scaleY=10000, dx=0, dy=0,
                                  angle=0, base=0, height=height, flags=2))
            if any(part['shape'] >= len(shapes) for part in parts):
                raise ValueError('invalid building shape reference')
            features.append(dict(id=identity, style=style, height=height,
                                 parts=parts, unsupported=unsupported))
    if r.offset != len(data):
        raise ValueError('unconsumed building bytes')
    return width, shapes, features


def building_point(point, grid, width):
    level, x, y = grid
    if level != 15 or any(type(v) is not int for v in grid) or not (0 <= x < 1 << level and 0 <= y < 1 << level):
        raise ValueError('unsupported building grid')
    extent = 1 << (width - 1)
    px, py = point
    # Parts can cross a tile edge; do not clamp them and deform the building.
    if not (-extent <= px <= 2 * extent and -extent <= py <= 2 * extent):
        raise ValueError('building point outside tile neighbourhood')
    unit = 360 / (1 << (level + width - 1))
    return [round((x * extent + px) * unit - 180, 8),
            round(90 - (y + 1) * 180 / (1 << level) + py * unit, 8)]


def rounded_wall_candidate(shape):
    points = shape['points']
    if shape['edges'] != 0 or len(points) < 8:
        return False
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    radii = [math.hypot(point[0] - cx, point[1] - cy) for point in points]
    average = sum(radii) / len(radii)
    return average > 0 and max(abs(radius - average) for radius in radii) < average * 0.3


def geographic_buildings(data, grid, paints=None):
    header = directory(data)
    entry = next((e for e in header['sections'] if e['kind'] == 50), None)
    if not entry:
        raise ValueError('missing building chapter')
    start = header['bodyOffset'] + entry['offset']
    width, shapes, features = building_section(data[start:start + entry['size']])
    from bmd_styles import style_bindings
    bindings = style_bindings(data, 51, len(features)) if paints is not None else {}
    buildings, skipped = [], 0
    for feature_number, feature in enumerate(features):
        parts, seen = [], set()
        skipped += feature['unsupported']
        for p in feature['parts']:
            # Translation is verified against native 15a6a30..15a6ab8.
            # Nonidentity shape scales/rotations need separate validation.
            if p['scaleX'] != 10000 or p['scaleY'] != 10000 or p['angle'] != 0:
                skipped += 1
                continue
            if not (0 < p['height'] <= 1000 and 0 <= p['base'] <= 1000):
                skipped += 1
                continue
            ring = [building_point([x + p['dx'], y + p['dy']], grid, width)
                    for x, y in shapes[p['shape']]['points']]
            key = (tuple(tuple(p) for p in ring), p['base'], p['height'])
            if key in seen:
                continue
            seen.add(key)
            parts.append(dict(ring=ring, base=p['base'], height=p['height'], flags=p['flags'],
                              smoothWalls=rounded_wall_candidate(shapes[p['shape']])))
        if parts:
            binding = bindings.get(feature_number)
            styles = {theme: lookup.get(binding, []) for theme, lookup in (paints or {}).items()}
            # This is the feature-level height from the APK's type-5 building
            # record. Its upper roof parts can extend above it; keep both.
            overall_height = feature['height']
            buildings.append(dict(id=feature['id'], parts=parts,
                                  **({'overallHeight': overall_height} if 0 < overall_height <= 2000 else {}),
                                  **({'paints': styles} if binding else {})))
    return buildings, skipped
