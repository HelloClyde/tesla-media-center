"""Pinned MgcGridFinger outer container. Geometry payloads remain opaque.

Field layout compared with native695a88; numeric record fields retain wire
numbers until their semantics are independently established.
"""
def fields(data):
    position = 0
    def integer():
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(data):
                raise ValueError('Truncated varint')
            byte = data[position]; position += 1
            if shift == 63 and byte > 1:
                raise ValueError('Varint overflow')
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('Varint overflow')
    while position < len(data):
        key = integer(); tag, wire = key >> 3, key & 7
        if not 0 < tag < 2**29:
            raise ValueError('Invalid field number')
        if wire == 0:
            yield tag, wire, integer()
            continue
        if wire not in (1, 2, 5):
            raise ValueError('Unsupported wire type')
        length = integer() if wire == 2 else (8 if wire == 1 else 4)
        if length > len(data) - position:
            raise ValueError('Truncated field')
        value = data[position:position+length]; position += length
        yield tag, wire, value


def record(data, tunnel=False):
    types = {1: 0, 2: 0, 3: 2, 4: 2, 5: 0}
    if tunnel:
        types[6] = 0
    result = {}
    for tag, wire, value in fields(data):
        if tag not in types:
            continue
        if wire != types[tag]:
            raise ValueError('Record wire type mismatch')
        if wire == 0:
            value &= 0xffffffff
            if value >= 0x80000000:
                value -= 0x100000000
        result[tag] = value
    if set(result) != set(types):
        raise ValueError('Missing required record fields')
    return result


def decode(data):
    if not isinstance(data, bytes) or len(data) > 16 * 1024 * 1024:
        raise ValueError('Expected bounded fingerprint bytes')
    outer = {}
    for tag, wire, value in fields(data):
        if tag not in range(1, 7):
            continue
        if wire != (0 if tag == 1 else 2):
            raise ValueError('Container wire type mismatch')
        outer[tag] = value
    if set(outer) != set(range(1, 7)) or outer[1] != 7001:
        raise ValueError('Incomplete or unsupported fingerprint container')
    groups = {1: [], 2: [], 3: [], 4: []}
    for tag, wire, value in fields(outer[4]):
        if tag not in groups:
            continue
        if wire != 2:
            raise ValueError('Collection wire type mismatch')
        groups[tag].append(value if tag == 1 else record(value, tunnel=tag == 3))
    return {'version': outer[1], 'identifier': outer[3],
            'strings': {tag: outer[tag] for tag in (2, 3, 5, 6)},
            'metadata': groups[1], 'floors': groups[2],
            'tunnels': groups[3], 'hulls': groups[4]}
