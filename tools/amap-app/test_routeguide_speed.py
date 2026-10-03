import struct
import unittest

import zstandard

from routeguide_speed import decode_speed_signs


def varint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def point_record(kind, speed, longitude, latitude):
    coordinate = field(1, round(longitude * 7200000)) + field(2, round(latitude * 7200000))
    return field(1, kind) + field(2, speed) + field(4, coordinate)


def response(records, status=0):
    link = b''.join(field(7, record) for record in records)
    route = field(1, (123).to_bytes(4, 'little')) + field(2, field(1, link))
    root = field(1, field(1, 51) + field(3, status)) + field(2, field(1, route))
    packed = zstandard.ZstdCompressor().compress(root)
    descriptor = struct.pack('<HHII', 2, 2, len(packed), len(root)).ljust(32, b'\0')
    size = 32 + len(descriptor) + len(packed)
    return struct.pack('<IHI', 31, 1, size).ljust(32, b'\0') + descriptor + packed


class RouteguideSpeedTest(unittest.TestCase):
    def test_only_coordinate_backed_type_ten_signs_are_projected(self):
        route = {'path': [[120, 30], [120.01, 30]], 'breaks': [], 'distance': 963}
        answer = response([
            point_record(10, 80, 120.005, 30),
            point_record(10, 80, 120.00501, 30),  # duplicate sign at same location
            point_record(9, 60, 120.007, 30),
            point_record(10, 60, 120.008, 30),
            point_record(10, 120, 121, 31),  # unrelated location
            point_record(10, 255, 120.009, 30),
        ])
        signs = decode_speed_signs(answer, [route], [123])[0]
        self.assertEqual([item['limit'] for item in signs], [80, 60])
        self.assertAlmostEqual(signs[0]['at'], 481.5, delta=2)
        self.assertLess(signs[0]['at'], signs[1]['at'])

    def test_fails_closed_on_error_status_and_truncation(self):
        route = {'path': [[120, 30], [120.01, 30]], 'breaks': [], 'distance': 963}
        with self.assertRaises(ValueError):
            decode_speed_signs(response([], status=1), [route])
        with self.assertRaises(ValueError):
            decode_speed_signs(response([])[:-1], [route])
        with self.assertRaises(ValueError):
            decode_speed_signs(response([]), [route], [124])


if __name__ == '__main__':
    unittest.main()
