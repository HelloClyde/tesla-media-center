import unittest
import struct
import zlib
import zstandard
from bmd_tile import catalog, tile_id, tile_grid, unpack, directory, geographic_grid


def vint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out) + bytes([value])


def field(key, value):
    if isinstance(value, bytes):
        return vint(key * 8 + 2) + vint(len(value)) + value
    return vint(key * 8) + vint(value)


def response(data, size, compressed=0, codec=0):
    block = b''.join(field(k, v) for k, v in [(1, data), (2, size), (3, compressed), (4, codec)])
    return field(1, tile_id(14, 13489, 6208)) + field(2, 1) + field(5, block)


class BmdTests(unittest.TestCase):
    def test_geographic_grid_and_edges(self):
        self.assertEqual(geographic_grid(116.397, 39.908, 14), (14, 13489, 4559))
        self.assertEqual(geographic_grid(180, -90, 14), (14, 16383, 16383))
        self.assertEqual(geographic_grid(-180, 90, 14), (14, 0, 0))
        for args in [(float('nan'), 0, 14), (0, 91, 14), (0, 0, -1), (True, 0, 14)]:
            with self.assertRaises(ValueError):
                geographic_grid(*args)

    def make_bmd(self, entries, body=b'abcdef'):
        data = struct.pack('<BIH', 0, 8000, len(entries))
        for kind, offset, size in entries:
            data += struct.pack('<H', kind) + vint(offset) + vint(size) + vint(5000)
        data += body
        return struct.pack('<I', zlib.crc32(data)) + data

    def test_directory_not_sorted_by_offset(self):
        raw = self.make_bmd([(30, 3, 3), (10, 0, 3)])
        result = directory(raw)
        self.assertEqual(result['format'], 8000)
        self.assertEqual(raw[result['bodyOffset']:], b'abcdef')
        self.assertEqual([s['kind'] for s in result['sections']], [30, 10])

    def test_directory_integrity_and_bounds(self):
        valid = self.make_bmd([(10, 0, 6)])
        invalid = [valid[:-1], valid[:-1] + b'x',
                   self.make_bmd([(10, 0, 7)]),
                   self.make_bmd([(10, 0, 4), (30, 3, 3)]),
                   self.make_bmd([(10, 0, 3), (10, 3, 3)])]
        for raw in invalid:
            with self.assertRaises(ValueError):
                directory(raw)

    def test_native_id_layout_and_signed_wrap(self):
        self.assertEqual(tile_id(14, 13489, 6208), 3940753826919601)
        self.assertEqual(tile_grid(14 << 48 | 6208 << 24 | 0xffffff), (14, 16383, 6208))

    def test_catalog_default_zero_and_duplicate(self):
        self.assertEqual(catalog(field(1, field(2, 123))), {0: 123})
        with self.assertRaises(ValueError):
            catalog(field(1, field(2, 123)) * 2)

    def decode(self, raw):
        return unpack(raw, tile_id(14, 13489, 6208), 1)

    def test_raw_and_zstd(self):
        data = b'fixture-map-block' * 100
        self.assertEqual(self.decode(response(data, len(data))), data)
        self.assertEqual(self.decode(response(zstandard.ZstdCompressor().compress(data), len(data), 1, 1)), data)

    def test_decompression_size_and_unknown_codec(self):
        packed = zstandard.ZstdCompressor().compress(b'x' * 10000)
        for raw in [response(packed, 1, 1, 1), response(b'x', 1, 1, 99), response(b'x', 2), response(b'x', 1 << 30)]:
            with self.assertRaises(ValueError):
                self.decode(raw)

    def test_identity_and_truncation(self):
        raw = response(b'x', 1)
        with self.assertRaises(ValueError):
            unpack(raw, 1, 1)
        with self.assertRaises(ValueError):
            self.decode(raw[:-1])


if __name__ == '__main__':
    unittest.main()
