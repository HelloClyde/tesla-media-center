import struct
import unittest
import zlib

from lane_render_blocks import decode_render_blocks
from test_lane_render import field


def body(data=b'opaque lane binary'):
    return struct.pack('<I', zlib.crc32(data)) + data


def block(identifier=1, data=None):
    return field(1, identifier) + field(3, body() if data is None else data)


def envelope(*blocks):
    return field(1, 123) + b''.join(field(2, b) for b in blocks)


class RenderBlocksTests(unittest.TestCase):
    def test_preserves_binary_and_unknown_metadata(self):
        result = decode_render_blocks(envelope(block() + field(2, 7)), 123)
        self.assertEqual(result['blocks'][0]['data'], body())
        self.assertEqual(result['blocks'][0]['field2'], 7)
        self.assertFalse(result['geometryDecoded'])

    def test_integrity(self):
        for data in (b'', b'123', body()[:-1], body()[:-1] + b'!'):
            with self.assertRaises(ValueError):
                decode_render_blocks(envelope(block(data=data)), 123)

    def test_duplicate_and_large_ids(self):
        for data in (envelope(block(), block()), envelope(block(65536))):
            with self.assertRaises(ValueError):
                decode_render_blocks(data, 123)

    def test_identity_and_wire_types(self):
        for data in (field(1, 124), field(1, b'123'),
                     envelope(field(1, b'1') + field(3, body())),
                     envelope(block() + field(3, body()))):
            with self.assertRaises(ValueError):
                decode_render_blocks(data, 123)

    def test_empty_and_limits(self):
        self.assertEqual(decode_render_blocks(envelope(), 123)['blocks'], [])
        with self.assertRaises(ValueError):
            decode_render_blocks(envelope(*(block(i) for i in range(65))), 123)


if __name__ == '__main__':
    unittest.main()
