import struct
import unittest
from route_v51 import decode, fields, unpack


def vi(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out) + bytes([value])


def msg(**items):
    out = b""
    for key, value in items.items():
        tag = int(key[1:])
        for v in value if isinstance(value, list) else [value]:
            out += vi(tag * 8 + (2 if isinstance(v, bytes) else 0))
            out += vi(len(v)) + v if isinstance(v, bytes) else vi(v)
    return out


def packed(values):
    previous, result = 0, b""
    for value in values:
        delta = round(value * 3600000) - previous
        previous += delta
        result += vi((delta << 1) ^ (delta >> 63))
    return result


def fixture(xs=(116.4, 116.401), ys=(39.9, 39.9)):
    segment = msg(f1=2, f4=msg(f1=packed(xs), f2=packed(ys)))
    protobuf = msg(f1=msg(f1=51, f3=0), f2=msg(f1=0, f5=b"", f7=msg(f1=8500, f10=segment)))
    size = 64 + len(protobuf)
    body = struct.pack('<IHI', 31, 1, size).ljust(32, b'\0')
    body += struct.pack('<HHII', 0, 1, len(protobuf), len(protobuf)).ljust(32, b'\0') + protobuf
    return struct.pack('<HQ', 200, size) + body


class RouteV51Test(unittest.TestCase):
    def test_decodes_absolute_first_and_zigzag_deltas(self):
        route = decode(fixture())[0]
        self.assertEqual(route['path'], [[116.4, 39.9], [116.401, 39.9]])
        self.assertAlmostEqual(route['distance'], 85, delta=1)

    def test_negative_delta(self):
        self.assertEqual(decode(fixture(xs=(116.401, 116.4)))[0]['path'][-1][0], 116.4)

    def test_rejects_truncation(self):
        raw = fixture()
        for size in (0, 8, 31, 73, len(raw) - 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                decode(raw[:size])

    def test_rejects_mismatched_axes_and_wrong_destination(self):
        with self.assertRaises(ValueError):
            decode(fixture(ys=(39.9,)))
        with self.assertRaises(ValueError):
            decode(fixture(), destination=[120, 30])

    def test_rejects_invalid_protobuf_and_compression(self):
        for data in (b'\0', b'\x0a\x7f', b'\x08' + b'\xff' * 11):
            with self.assertRaises(ValueError):
                fields(data)
        raw = bytearray(fixture()); raw[42] = 99
        with self.assertRaises(ValueError):
            unpack(raw)

    def test_compressed_record_roundtrip(self):
        import zstandard
        data = unpack(fixture()); compressed = zstandard.ZstdCompressor().compress(data)
        size = 64 + len(compressed)
        raw = struct.pack('<HQ', 200, size) + struct.pack('<IHI', 31, 1, size).ljust(32, b'\0')
        raw += struct.pack('<HHII', 2, 1, len(compressed), len(data)).ljust(32, b'\0') + compressed
        self.assertEqual(decode(raw), decode(fixture()))
