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


def extract_boundaries(data, *, include_raw_metadata=False, include_geometry_codes=False,
                       include_raw_fields=False):
    if not isinstance(data, bytes) or not 8 <= len(data) <= LIMIT:
        raise ValueError('invalid tile buffer')
    budget = [200000]

    def read(fmt, offset, end):
        size = struct.calcsize('<' + fmt)
        if offset < 0 or offset + size > end:
            raise ValueError('read outside FlatBuffer')
        return struct.unpack_from('<' + fmt, data, offset)[0]

    def field(table, slot, start, end, width=1):
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
        if not 4 <= offset or offset + width > obj_size:
            raise ValueError('invalid field offset')
        return table + offset

    def pointer(table, slot, start, end):
        location = field(table, slot, start, end, width=4)
        if location is None:
            return None
        relative = read('I', location, end)
        target = location + relative
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

    def byte_vector(table, slot, start, end):
        value = pointer(table, slot, start, end)
        if value is None:
            return []
        count = read('I', value, end)
        budget[0] -= count
        if budget[0] < 0 or count > end - value - 4:
            raise ValueError('invalid byte vector size')
        return list(data[value + 4:value + 4 + count])

    def raw_fields(table, start, end, slots=13):
        """Keep field bytes for offline schema research, without assigning semantics."""
        vtable = table - read('i', table, end)
        if vtable < start:
            raise ValueError('vtable outside FlatBuffer')
        size, obj_size = read('H', vtable, end), read('H', vtable + 2, end)
        if size < 4 or size % 2 or vtable + size > end or obj_size < 4 or table + obj_size > end:
            raise ValueError('invalid table size')
        offsets = {}
        for slot in range(slots):
            if 4 + slot * 2 >= size:
                continue
            offset = read('H', vtable + 4 + slot * 2, end)
            if offset:
                if not 4 <= offset < obj_size:
                    raise ValueError('invalid field offset')
                offsets[slot] = offset
        result = {}
        for slot, offset in offsets.items():
            next_offset = min((value for value in offsets.values() if value > offset),
                              default=obj_size)
            width = min(4, next_offset - offset)
            if width < 1:
                raise ValueError('overlapping field offsets')
            result[str(slot)] = data[table + offset:table + offset + width].hex()
        return result

    root = read('I', 0, len(data))
    lines, points, metadata_records = [], 0, 0
    line_metadata = [] if include_raw_metadata or include_raw_fields else None
    boundary_codes, metadata_types = {}, {}
    objects = vector(root, 3, 0, len(data))
    for blob in objects:
        length = read('I', blob, len(data))
        start, end = blob + 4, blob + 4 + length
        if length < 8 or end > len(data):
            raise ValueError('invalid nested FlatBuffer')
        nested = start + read('I', start, end)
        for boundary in vector(nested, 8, start, end):
            code_field = field(boundary, 0, start, end)
            code = read('B', code_field, end) if code_field is not None else None
            if code_field is not None:
                boundary_codes[code] = boundary_codes.get(code, 0) + 1
            for segment in vector(boundary, 1, start, end):
                # Segment slot 0 contains a vector of metadata tables in real
                # LNDS output. Preserve its count for offline style research;
                # no style enum or colour semantics have been confirmed yet.
                metadata = vector(segment, 0, start, end)
                metadata_records += len(metadata)
                if metadata_records > 200000:
                    raise ValueError('too many boundary metadata records')
                segment_metadata = [] if include_raw_metadata or include_raw_fields else None
                for item in metadata:
                    kind_field = field(item, 9, start, end, width=4)
                    kind = read('I', kind_field, end) if kind_field is not None else None
                    if kind_field is not None:
                        metadata_types[kind] = metadata_types.get(kind, 0) + 1
                    if segment_metadata is not None:
                        slot4_field = field(item, 4, start, end, width=4)
                        segment_metadata.append({
                            'kindRaw': kind,
                            'slot4Raw': read('I', slot4_field, end) if slot4_field is not None else None,
                            'slot12Present': field(item, 12, start, end) is not None,
                            **({'fieldsHexRaw': raw_fields(item, start, end),
                                'slot8ByteVectorRaw': byte_vector(item, 8, start, end)}
                               if include_raw_fields else {}),
                        })
                geometry = pointer(segment, 1, start, end)
                if geometry is None:
                    continue
                # This optional geometry-side byte vector is separate from
                # the metadata record's slot 8 byte vector. The native 3/6
                # check at 12d24fc-12d2560 reads the latter, not this one.
                geometry_meta = pointer(geometry, 1, start, end) if include_geometry_codes else None
                geometry_codes = (byte_vector(geometry_meta, 0, start, end)
                                  if geometry_meta is not None else [])
                # Restrict the existing point reader to this nested buffer.
                line = boundary_points(data[start:end], geometry - start)
                points += len(line)
                if points > 1000000:
                    raise ValueError('too many boundary points')
                if line:
                    lines.append(line)
                    if line_metadata is not None:
                        entry = {'boundaryCodeRaw': code, 'records': segment_metadata}
                        if include_geometry_codes:
                            entry['geometryCodesRaw'] = geometry_codes
                        line_metadata.append(entry)
    result = {'objects': len(objects), 'segments': len(lines),
            'points': points, 'coordinateSystem': 'unverified',
            'heightUnits': 'unverified', 'boundaryCodesRaw': boundary_codes,
            'metadataRecords': metadata_records, 'metadataTypesRaw': metadata_types,
            'lines': lines}
    if line_metadata is not None:
        result['lineMetadataRaw'] = line_metadata
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--output', required=True)
    parser.add_argument('--include-raw-metadata', action='store_true',
                        help='include raw per-line metadata for offline analysis')
    parser.add_argument('--include-geometry-codes', action='store_true',
                        help='offline only: inspect optional native geometry byte codes')
    parser.add_argument('--include-raw-fields', action='store_true',
                        help='offline only: preserve metadata field bytes without interpreting them')
    args = parser.parse_args()
    result = extract_boundaries(Path(args.input).read_bytes(),
                                include_raw_metadata=args.include_raw_metadata or args.include_geometry_codes,
                                include_geometry_codes=args.include_geometry_codes,
                                include_raw_fields=args.include_raw_fields)
    Path(args.output).write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('lines', 'lineMetadataRaw')}))
