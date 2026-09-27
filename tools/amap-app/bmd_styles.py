"""Bounded section attribute-1 binding and packaged App polygon paints."""
from bmd_geometry import Reader
from bmd_tile import directory, LIMIT
from route_v51 import fields, one
import zipfile
import zstandard


def section(data, kind):
    header = directory(data)
    entry = next((e for e in header['sections'] if e['kind'] == kind), None)
    if not entry:
        return b''
    start = header['bodyOffset'] + entry['offset']
    return data[start:start + entry['size']]


def style_bindings(data, kind, feature_count):
    """Attribute 1 stores subtype u32, category u32 (1ab9be4/1aba10c).

    Attribute blocks have offsets relative to the end of their directory.
    Modes 1 and 2 are individual and shared-value feature lists respectively.
    """
    raw = section(data, kind)
    if not raw:
        return {}
    reader = Reader(raw)
    count = reader.variable()
    if not 1 <= count <= 32:
        raise ValueError('invalid attribute directory')
    entries = [(reader.variable(), reader.variable()) for _ in range(count)]
    base = reader.offset
    if len({k for k, _ in entries}) != count or len({o for _, o in entries}) != count:
        raise ValueError('duplicate attributes')
    if any(o >= len(raw) - base for _, o in entries):
        raise ValueError('attribute outside section')
    offset = dict(entries).get(1)
    if offset is None:
        return {}
    end = min((o for _, o in entries if o > offset), default=len(raw) - base)
    reader = Reader(raw[base + offset:base + end])
    mode, count = reader.integer(1), reader.variable()
    if mode not in (1, 2) or count > feature_count:
        raise ValueError('unsupported style bindings')
    result = {}
    for _ in range(count):
        size = reader.variable() if mode == 2 else 1
        if size > feature_count or len(result) + size > feature_count:
            raise ValueError('too many style references')
        indexes = [reader.variable() for _ in range(size)]
        subtype, category = reader.integer(4), reader.integer(4)
        for index in indexes:
            if index >= feature_count or index in result:
                raise ValueError('invalid style reference')
            result[index] = (category, subtype)
    if reader.offset != len(reader.data):
        raise ValueError('unconsumed style bindings')
    return result


def polygon_paints(raw):
    """Resolve mode-2 polygon style -> group -> zoom rule -> solid material.

    Unknown material/condition branches are omitted, never assigned a guessed
    land-use category or color. Numeric categories stay internal to the DTO.
    """
    root = fields(raw)
    modes = [fields(v) for v in root.get(1, [])]
    mode = next((v for v in modes if one(v, 1) == 2), None)
    if mode is None:
        raise ValueError('missing polygon styles')
    data = fields(one(mode, 3))
    groups = {one(q, 1): q for q in map(fields, data.get(2, []))}
    rules = {one(q, 1): q for q in map(fields, data.get(5, []))}
    materials = {one(q, 1): q for q in map(fields, data.get(4, []))}
    result = {}
    for style in map(fields, data.get(1, [])):
        stops = []
        for binding in map(fields, style.get(3, [])):
            if one(binding, 1) != 0 or one(binding, 2) != 0:
                continue
            group = groups.get(one(binding, 3), {})
            for identity in group.get(5, []):
                try:
                    rule = fields(one(fields(one(rules[identity], 3)), 1))
                    condition = fields(one(rule, 2))
                    if one(condition, 2) != 0 or set(condition) != {1, 2}:
                        continue
                    limits = fields(one(condition, 1))
                    low, high = one(limits, 1), one(limits, 2)
                    material = materials[one(fields(one(rule, 5)), 1)]
                    if one(material, 2) != 6:
                        continue
                    paint = fields(one(fields(one(material, 3)), 6))
                    color = one(fields(one(paint, 18)), 1)
                    alpha = one(paint, 2, 100) / 100 * ((color >> 24) & 255) / 255
                    if not (0 <= low <= high <= 24 and 0 <= color <= 0xffffffff and 0 <= alpha <= 1):
                        raise ValueError('invalid paint')
                    stops.append({'minZoom': low, 'maxZoom': high, 'color': f'#{color & 0xffffff:06x}', 'opacity': alpha})
                except (KeyError, TypeError, ValueError):
                    continue
        if stops:
            result[(one(style, 1), one(style, 2))] = stops
    return result


def load_paints(apk):
    result = {}
    with zipfile.ZipFile(apk) as archive:
        for theme, prefix in [('day', 'style_X_MainStd_Std_D_s_'), ('night', 'style_X_MainStd_Std_N_s_')]:
            name = next(n for n in archive.namelist() if n.startswith('assets/map_assets/' + prefix))
            if archive.getinfo(name).file_size > LIMIT:
                raise ValueError('style size limit')
            raw = zstandard.ZstdDecompressor().decompress(archive.read(name), max_output_size=LIMIT)
            result[theme] = polygon_paints(raw)
    return result
