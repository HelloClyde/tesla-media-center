"""Bounded section attribute-1 binding and packaged App polygon paints."""
from bmd_geometry import Reader
from bmd_tile import directory, LIMIT
from route_v51 import fields, one
import zipfile
import zstandard
import math
import struct


def solid_color(paint, key):
    value = one(fields(one(paint, key)), 1)
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('invalid material color')
    return {'color': f'#{value & 0xffffff:06x}', 'opacity': (value >> 24) / 255}


def detail_paints(raw, mode_id):
    """Packaged default-theme rules, excluding conditional/unsupported branches.

    Road widths remain style units, NOT measured lane widths. The web renderer
    chooses its cartographic scale. For buildings only uniform solid palettes
    are accepted: heterogeneous face assignments/textures need a native port.
    """
    mode = next((m for m in map(fields, fields(raw).get(1, [])) if one(m, 1) == mode_id), None)
    if mode is None:
        return {}
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
            for identity in groups.get(one(binding, 3), {}).get(5, []):
                try:
                    rule = fields(one(fields(one(rules[identity], 3)), 1))
                    condition = fields(one(rule, 2))
                    if one(condition, 2) != 0 or set(condition) != {1, 2}:
                        continue
                    limits = fields(one(condition, 1))
                    low, high = one(limits, 1), one(limits, 2)
                    if not 0 <= low <= high <= 24:
                        continue
                    material = materials[one(fields(one(rule, 4 if mode_id == 1 else 11)), 1)]
                    kind = 5 if mode_id == 1 else 8
                    if one(material, 2) != kind:
                        continue
                    paint = fields(one(fields(one(material, 3)), kind))
                    if mode_id == 1:
                        outer, inner = solid_color(paint, 10), solid_color(paint, 11)
                        widths = [struct.unpack('<d', one(paint, k))[0] for k in (19, 20)]
                        if not all(math.isfinite(w) and 0 < w <= 2000 for w in widths) or widths[0] < widths[1]:
                            continue
                        stop = dict(outer=outer, inner=inner, outerWidth=widths[0], innerWidth=widths[1])
                    else:
                        colors = [solid_color(paint, k) for k in range(2, 7)]
                        if any(c != colors[0] for c in colors):
                            continue
                        stop = dict(surface=colors[0])
                    stops.append(dict(minZoom=low, maxZoom=high, **stop))
                except (KeyError, TypeError, ValueError, struct.error):
                    continue
        if stops:
            result[(one(style, 1), one(style, 2))] = stops
    return result


def section(data, kind):
    header = directory(data)
    entry = next((e for e in header['sections'] if e['kind'] == kind), None)
    if not entry:
        return b''
    start = header['bodyOffset'] + entry['offset']
    return data[start:start + entry['size']]


def attribute_block(data, kind, attribute):
    """Return one bounded attribute block; offsets are directory-relative."""
    raw = section(data, kind)
    if not raw:
        return b''
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
    offset = dict(entries).get(attribute)
    if offset is None:
        return b''
    end = min((o for _, o in entries if o > offset), default=len(raw) - base)
    return raw[base + offset:base + end]


def style_bindings(data, kind, feature_count):
    """Attribute 1 stores subtype u32, category u32 (1ab9be4/1aba10c).

    Attribute blocks have offsets relative to the end of their directory.
    Modes 1 and 2 are individual and shared-value feature lists respectively.
    """
    raw = attribute_block(data, kind, 1)
    if not raw:
        return {}
    reader = Reader(raw)
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


def load_paints(apk, mode_id=2):
    result = {}
    with zipfile.ZipFile(apk) as archive:
        for theme, prefix in [('day', 'style_X_MainStd_Std_D_s_'), ('night', 'style_X_MainStd_Std_N_s_')]:
            name = next(n for n in archive.namelist() if n.startswith('assets/map_assets/' + prefix))
            if archive.getinfo(name).file_size > LIMIT:
                raise ValueError('style size limit')
            raw = zstandard.ZstdDecompressor().decompress(archive.read(name), max_output_size=LIMIT)
            result[theme] = polygon_paints(raw) if mode_id == 2 else detail_paints(raw, mode_id)
    return result
