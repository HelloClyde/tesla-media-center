"""Section-20 point labels: native parser 1ac14bc / 1ac16a0 / 1ac1a90."""
from bmd_geometry import Reader, geographic_point, names
from bmd_styles import section, style_bindings


def points(raw):
    reader = Reader(raw)
    count = reader.variable()
    if count > 4096:
        raise ValueError('too many point styles')
    styles = [reader.integer(2) for _ in range(count)]
    count = reader.variable()
    if count > 10000:
        raise ValueError('too many point groups')
    result = []
    for _ in range(count):
        code, flags, width = reader.integer(4), reader.integer(2), reader.integer(1)
        count_points = reader.variable()
        if width not in (11, 12, 13) or count_points + len(result) > 100000:
            raise ValueError('unsupported point group')
        for _ in range(count_points):
            style = reader.variable()
            if style >= len(styles):
                raise ValueError('invalid point style')
            reader.integer(8)
            flags = reader.integer(1)
            reader.integer(8)
            name = reader.variable() if flags & 1 else None
            reader.begin_bits()
            point = [reader.bits(width), reader.bits(width)]
            reader.end_bits()
            result.append({'point': point, 'nameIndex': name, 'style': styles[style], 'width': width})
    if reader.offset != len(raw):
        raise ValueError('unconsumed point bytes')
    return result


def geographic_labels(data, grid, places=False):
    raw = section(data, 20)
    if not raw:
        return []
    table = names(section(data, 10))
    features = points(raw)
    bindings = style_bindings(data, 21, len(features)) if places else {}
    result = []
    for feature_index, feature in enumerate(features):
        category, subtype = bindings.get(feature_index, (0, 0))
        # App administrative labels verified in type 0: provinces (22),
        # capital/provincial capitals/municipalities (30/31/32), cities (5/6).
        # Do not classify rivers, seas or other POIs as administrative names.
        if places and (category != 10002 or subtype not in (5, 6, 22, 30, 31, 32)):
            continue
        index = feature['nameIndex']
        if index is None:
            continue
        if index >= len(table):
            raise ValueError('invalid point name reference')
        label = table[index].get('zh-Hans', next(iter(table[index].values()), ''))
        if label:
            result.append({'point': geographic_point(feature['point'], grid, feature['width']), 'name': label,
                           'minZoom': feature['style'] & 31, 'maxZoom': (feature['style'] >> 5) & 31,
                           **({'kind': 'province' if subtype == 22 else 'city',
                               'priority': 0 if subtype == 30 else 1 if subtype == 22 else 2 if subtype in (31, 32) else 3} if places else {})})
    return result
