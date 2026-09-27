"""Offline inspection of the App's IndexedModel protobuf descriptor.

Schema recovered from libamapr.so 17.00.0.2005 descriptor 0x1b335b8,
used by 0xc7398c -> 0xc73b30 -> 0x1ada34c. No live nonempty index has
been validated yet. Field numbers are retained where semantics are unknown.
This tool does not fetch URLs or convert coordinates into map positions.
"""
import argparse
import json
import math
import struct
from pathlib import Path

from route_v51 import varint

# (encoding, required/repeated/optional). Integers retain unsigned wire values;
# their signedness/coordinate units are not inferred from plausible numbers.
SCHEMAS = {
    'root': {1: ('int', 'required'), 2: ('int', 'required'), 3: ('section', 'repeated')},
    'section': {1: ('int', 'required'), 2: ('int', 'required'),
                3: ('triple', 'optional'), 4: ('record', 'repeated'),
                5: ('strings', 'repeated'), 6: ('group', 'repeated'),
                7: ('model', 'repeated'), 8: ('int', 'optional')},
    'triple': {n: ('int', 'required') for n in (1, 2, 3)},
    'record': {**{n: ('int', 'required') for n in range(1, 6)},
               6: ('string', 'required'), 7: ('bytes', 'optional')},
    'strings': {n: ('string', 'required') for n in (1, 2, 3)},
    'group': {1: ('int', 'required'), 2: ('instances', 'repeated'), 3: ('tile_bounds', 'repeated')},
    'instances': {1: ('string', 'optional'), 2: ('instance', 'repeated')},
    'instance': {1: ('int', 'required'), 2: ('bounds', 'optional'), 3: ('tile_bounds', 'optional')},
    'bounds': {**{n: ('int', 'required') for n in (1, 2, 3, 4)},
               5: ('float', 'optional'), 6: ('float', 'optional')},
    'tile_bounds': {**{n: ('int', 'required') for n in (1, 2, 3)},
                    4: ('float', 'optional'), 5: ('float', 'optional')},
    'model': {1: ('int', 'required'), 2: ('reference', 'repeated'),
              3: ('float', 'optional'), 4: ('float', 'optional'),
              5: ('membership', 'repeated'), 6: ('float', 'optional'),
              7: ('pair', 'required'), 8: ('int', 'optional'),
              9: ('int', 'optional'), 10: ('float', 'optional'), 11: ('int', 'optional')},
    'reference': {1: ('string', 'required'), 2: ('int', 'optional')},
    'membership': {1: ('string', 'required'), 2: ('packed_int', 'repeated')},
    'pair': {1: ('float', 'required'), 2: ('float', 'required'), 3: ('float', 'optional')},
}


def decode_index(data):
    if not 0 < len(data) <= 16 * 1024 * 1024:
        raise ValueError('invalid index size')
    budget = [100000]

    def spend():
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError('index field limit')

    def decode(raw, schema, depth=0):
        if depth > 12:
            raise ValueError('index nesting limit')
        spec, result, pos = SCHEMAS[schema], {}, 0
        while pos < len(raw):
            spend()
            tag, pos = varint(raw, pos)
            number, wire = tag >> 3, tag & 7
            if not 0 < number < 1 << 29 or wire not in (0, 1, 2, 5):
                raise ValueError('invalid index tag')
            if wire == 0:
                value, pos = varint(raw, pos)
            else:
                if wire == 2:
                    size, pos = varint(raw, pos)
                else:
                    size = 4 if wire == 5 else 8
                if pos + size > len(raw):
                    raise ValueError('truncated index field')
                value, pos = raw[pos:pos + size], pos + size
            if number not in spec:
                continue
            kind, mode = spec[number]
            if mode != 'repeated' and number in result:
                raise ValueError('duplicate index field')
            expected = 0 if kind == 'int' else 5 if kind == 'float' else 2
            if kind == 'packed_int' and wire in (0, 2):
                values = []
                if wire == 0:
                    values.append(str(value))
                else:
                    offset = 0
                    while offset < len(value):
                        spend()
                        integer, offset = varint(value, offset)
                        values.append(str(integer))
                result.setdefault(number, []).extend(values)
                continue
            if wire != expected:
                raise ValueError('index wire type mismatch')
            if kind == 'int':
                value = str(value)  # Avoid loss of 64-bit IDs in JSON consumers.
            elif kind == 'float':
                value = struct.unpack('<f', value)[0]
                if not math.isfinite(value):
                    raise ValueError('nonfinite index number')
            elif kind == 'string':
                if len(value) > 8192:
                    raise ValueError('index string limit')
                value = value.decode('utf-8', errors='strict')
                if '\0' in value:
                    raise ValueError('embedded NUL in index string')
            elif kind == 'bytes':
                value = {'bytes': len(value)}
            else:
                value = decode(value, kind, depth + 1)
            if mode == 'repeated':
                result.setdefault(number, []).append(value)
            else:
                result[number] = value
        if any(mode == 'required' and n not in result for n, (_, mode) in spec.items()):
            raise ValueError('missing required index field')
        return result

    return decode(data, 'root')


def index_summary(data):
    decoded = decode_index(data)
    sections = []
    for section in decoded.get(3, []):
        models = {}
        for model in section.get(7, []):
            identity = model[1]
            if identity in models:
                raise ValueError('duplicate model definition')
            models[identity] = {'id': identity, 'references': model.get(2, []), 'rawFields': model}
        instances = []
        for group in section.get(6, []):
            for entry in group.get(2, []):
                for instance in entry.get(2, []):
                    identity = instance[1]
                    instances.append({'modelId': identity, 'resolved': identity in models,
                                      'group': group[1], 'label': entry.get(1), 'rawFields': instance})
        sections.append({'models': list(models.values()), 'instances': instances,
                         'unresolvedInstances': sum(not i['resolved'] for i in instances)})
    return {'verifiedLiveIndex': False, 'georeferenced': False, 'sections': sections, 'rawFields': decoded}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    if args.source.stat().st_size > 16 * 1024 * 1024:
        parser.error('index exceeds size limit')
    print(json.dumps(index_summary(args.source.read_bytes()), ensure_ascii=True, indent=2))
