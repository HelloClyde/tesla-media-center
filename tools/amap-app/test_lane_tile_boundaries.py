"""Small synthetic nested LNDS FlatBuffer for the boundary/metadata path."""

import struct

import pytest

from lane_tile_boundaries import extract_boundaries


def tile(geometry_codes=None, metadata_codes=None):
    def container():
        data = bytearray(b'\0' * 4)

        def align(size=4):
            data.extend(b'\0' * (-len(data) % size))

        def table(slots, size):
            vtable = len(data)
            data.extend(struct.pack('<HH', 4 + 2 * (max(slots, default=-1) + 1), size))
            for slot in range(max(slots, default=-1) + 1):
                data.extend(struct.pack('<H', slots.get(slot, 0)))
            align()
            result = len(data)
            data.extend(struct.pack('<i', result - vtable))
            data.extend(b'\0' * (size - 4))
            return result

        def vector(count):
            align()
            result = len(data)
            data.extend(struct.pack('<I', count) + b'\0' * (count * 4))
            return result

        def link(field, target):
            struct.pack_into('<I', data, field, target - field)

        return data, align, table, vector, link

    nested, align, table, vector, link = container()
    root = table({8: 4}, 8)
    boundaries = vector(1); link(root + 4, boundaries)
    boundary = table({0: 4, 1: 8}, 12)
    nested[boundary + 4] = 1
    link(boundaries + 4, boundary)
    segments = vector(1); link(boundary + 8, segments)
    segment = table({0: 4, 1: 8}, 12); link(segments + 4, segment)
    attrs = vector(1); link(segment + 4, attrs)
    metadata = table({9: 4, **({8: 8} if metadata_codes is not None else {})},
                     12 if metadata_codes is not None else 8)
    link(attrs + 4, metadata)
    struct.pack_into('<I', nested, metadata + 4, 1)
    if metadata_codes is not None:
        align()
        codes = len(nested)
        nested.extend(struct.pack('<I', len(metadata_codes)) + bytes(metadata_codes))
        link(metadata + 8, codes)
    geometry = table({0: 4, **({1: 8} if geometry_codes is not None else {})},
                     12 if geometry_codes is not None else 8)
    link(segment + 8, geometry)
    if geometry_codes is not None:
        code_table = table({0: 4}, 8)
        link(geometry + 8, code_table)
        align()
        code_vector = len(nested)
        nested.extend(struct.pack('<I', len(geometry_codes)) + bytes(geometry_codes))
        link(code_table + 4, code_vector)
    while len(nested) % 8 != 4:
        nested.append(0)
    points = len(nested)
    nested.extend(struct.pack('<I6d', 2, 116.4, 39.9, 0.0, 116.401, 39.9, 0.0))
    link(geometry + 4, points)
    struct.pack_into('<I', nested, 0, root)

    outer, align, table, vector, link = container()
    root = table({3: 4}, 8)
    objects = vector(1); link(root + 4, objects)
    align()
    blob = len(outer)
    outer.extend(struct.pack('<I', len(nested)) + nested)
    link(objects + 4, blob)
    struct.pack_into('<I', outer, 0, root)
    return bytes(outer)


def test_nested_boundaries_keep_raw_metadata_count_without_assigning_style():
    result = extract_boundaries(tile())
    assert result['objects'] == 1
    assert result['segments'] == 1
    assert result['points'] == 2
    assert result['boundaryCodesRaw'] == {1: 1}
    assert result['metadataRecords'] == 1
    assert result['metadataTypesRaw'] == {1: 1}
    assert result['lines'] == [[(116.4, 39.9, 0.0), (116.401, 39.9, 0.0)]]
    assert 'lineMetadataRaw' not in result

    detailed = extract_boundaries(tile(), include_raw_metadata=True)
    assert detailed['lineMetadataRaw'] == [{
        'boundaryCodeRaw': 1,
        'records': [{'kindRaw': 1, 'slot4Raw': None, 'slot12Present': False}],
    }]
    assert len(detailed['lineMetadataRaw']) == len(detailed['lines'])


def test_geometry_byte_codes_are_preserved_without_assigning_line_style():
    detailed = extract_boundaries(tile([3, 6, 0]), include_raw_metadata=True,
                                  include_geometry_codes=True)
    assert detailed['lineMetadataRaw'][0]['geometryCodesRaw'] == [3, 6, 0]


def test_offline_raw_fields_preserve_bytes_without_changing_production_output():
    plain = extract_boundaries(tile())
    detailed = extract_boundaries(tile(), include_raw_fields=True)
    assert {key: value for key, value in detailed.items() if key != 'lineMetadataRaw'} == plain
    assert detailed['lineMetadataRaw'][0]['records'][0]['fieldsHexRaw'] == {'9': '01000000'}
    assert detailed['lineMetadataRaw'][0]['records'][0]['slot8ByteVectorRaw'] == []


def test_metadata_slot8_is_a_byte_vector_not_a_scalar_style():
    detailed = extract_boundaries(tile(metadata_codes=[0xEF, 0xF1]), include_raw_fields=True)
    record = detailed['lineMetadataRaw'][0]['records'][0]
    assert record['slot8ByteVectorRaw'] == [0xEF, 0xF1]
    assert '8' in record['fieldsHexRaw']


def test_truncated_metadata_vector_is_rejected():
    raw = tile()
    with pytest.raises(ValueError):
        extract_boundaries(raw[:-30])
