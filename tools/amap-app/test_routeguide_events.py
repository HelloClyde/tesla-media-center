import json
import struct
import unittest
from unittest.mock import patch

import msgpack
import zstandard

from routeguide_events import decode_ncp


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def event(payload, script):
    return msgpack.packb({'NCPEvent': script, '_ds': json.dumps(payload)}, use_bin_type=True)


def response(section_length=1000, camera_link_distance=500, identity=123):
    section = event({'speed': 80}, {'_rd': 0, '_ss': 0, '_es': 0,
                                    '_c': f'((distance>0) && (distance<={section_length}))'})
    camera = event({'coord2D': {'lon': 120.005, 'lat': 30}, 'segment': 0, 'link': 0,
                    'distToLink': camera_link_distance,
                    'subCamera': [{'subType': 7, 'speed': [60, 80, 255]}]}, {'_rd': 500})
    interval = event({'coord2D': {'lon': 120.005, 'lat': 30}, 'type': 25,
                      'distance': 500, 'speed': [80]}, {'_rd': 500})
    block = (struct.pack('<I', len(section)) + section + b'\0' * 4
             + struct.pack('<I', len(camera)) + camera + b'\0' * 4
             + struct.pack('<I', len(interval)) + interval + b'\x04ida')
    container = (b'ncp0' + b'\0' * 4 + struct.pack('<I', 1) + b'\x02wla'
                 + b'\0' * 4 + struct.pack('<I', len(block)) + b'\0' * 4 + block)
    container = container[:4] + struct.pack('<I', len(container) - 12) + container[8:]
    route = field(1, identity.to_bytes(4, 'little')) + field(4, container)
    root = field(1, field(1, 5100) + field(3, 0) + field(5, b'a' * 32)) + field(2, route)
    packed = zstandard.ZstdCompressor().compress(root)
    descriptor = struct.pack('<HHII', 2, 3, len(packed), len(root)).ljust(32, b'\0')
    size = 32 + len(descriptor) + len(packed)
    return struct.pack('<IHI', 31, 1, size).ljust(32, b'\0') + descriptor + packed


class RouteguideEventsTest(unittest.TestCase):
    def setUp(self):
        self.route = {'path': [[120, 30], [120.01, 30]], 'breaks': [],
                      'distance': 963, 'steps': [{'distance': 963}]}
        self.context = {'navigation_id_candidate': 'a' * 32}

    def decode(self, answer):
        with patch('routeguide_events.extract', return_value=self.context), \
             patch('routeguide_events._native_segments', return_value=[[[1000]]]):
            return decode_ncp(answer, b'route', [self.route], [123])[0]

    def test_native_section_and_two_camera_types_map_to_measured_geometry(self):
        result = self.decode(response())
        self.assertEqual(result['speedLimits'], [{'start': 0, 'end': 963, 'limit': 80}])
        self.assertEqual([x['type'] for x in result['speedCameras']], [7, 25])
        self.assertEqual(result['speedCameras'][0]['speed'], [60, 80, 255])
        self.assertAlmostEqual(result['speedCameras'][0]['at'], 481.5, delta=2)

    def test_rejects_mismatched_identity_and_unverified_event_distance(self):
        with self.assertRaises(ValueError):
            self.decode(response(identity=124))
        self.assertEqual(self.decode(response(section_length=1100, camera_link_distance=400)),
                         {'speedLimits': [], 'speedCameras': [{'at': 481.5, 'type': 25, 'speed': [80]}]})


if __name__ == '__main__':
    unittest.main()
