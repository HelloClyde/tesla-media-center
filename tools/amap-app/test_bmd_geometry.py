import struct
import unittest
from bmd_geometry import lines, names, geographic_point


def v(value):
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    return bytes(output) + bytes([value])


def packed(*fields):
    text = ''.join(format(value & ((1 << width) - 1), f'0{width}b') for value, width in fields)
    text += '0' * (-len(text) % 8)
    return int(text, 2).to_bytes(len(text) // 8, 'big')


def fixture(suffix=0, flags=5):
    # Two points separated by a negative x and positive y delta; optional mark.
    group = struct.pack('<IHB', 123, 4, 13) + v(1)
    record = v(0) + bytes([flags]) + v(2) + bytes([0, 0]) + struct.pack('<Q', 42)
    delta = [(-3, 5), (7, 5)] + ([(1, 1)] if flags & 4 else [])
    geometry = v(2) + packed((100, 13), (200, 13), (5, 5)) + packed(*delta) + v(suffix)
    return v(1) + struct.pack('<H', 654) + v(1) + group + record + geometry


class GeometryTests(unittest.TestCase):
    def test_name_annotations_are_bounded_and_aligned(self):
        language, label = b'zh-Hans', '北京市'.encode()
        raw = v(1) + packed((3, 5), (len(language), 3), *((c, 8) for c in language))
        raw += v(1) + bytes([1]) + packed((4, 5)) + v(0) + packed((len(label), 4)) + label + b'\xc0'
        raw += v(3) + packed((2, 5), (0, 2), (1, 2), (2, 2))
        raw += v(2) + packed((3, 5), (5, 3), (7, 3))
        self.assertEqual(names(raw), [{'zh-Hans': '北京市'}])
        for end in range(len(raw)):
            with self.assertRaises(ValueError):
                names(raw[:end])
        with self.assertRaises(ValueError):
            names(raw + b'\0')

    def test_names_use_bit_lengths_and_utf8_byte_lengths(self):
        language = 'zh-Hans'.encode()
        label = '东长安街'.encode()
        raw = v(1) + packed((3, 5), (len(language), 3), *((c, 8) for c in language))
        raw += v(2) + bytes([1]) + packed((4, 5)) + v(0) + packed((len(label), 4)) + label + b'\0'
        raw += bytes([0]) + packed((0, 5))
        self.assertEqual(names(raw), [{'zh-Hans': '东长安街'}, {}])
        for end in range(len(raw)):
            with self.assertRaises(ValueError):
                names(raw[:end])
        with self.assertRaises(ValueError):
            names(raw + b'\0')

    def test_geographic_neighbor_seams_and_northward_axis(self):
        self.assertEqual(geographic_point([4096, 123], (14, 13489, 4559)),
                         geographic_point([0, 123], (14, 13490, 4559)))
        self.assertEqual(geographic_point([321, 0], (14, 13489, 4559)),
                         geographic_point([321, 2048], (14, 13489, 4560)))
        self.assertGreater(geographic_point([0, 2048], (14, 13489, 4559))[1],
                           geographic_point([0, 0], (14, 13489, 4559))[1])
        with self.assertRaises(ValueError):
            geographic_point([0, 0], (15, 13489, 4559))

    def test_signed_deltas_alignment_and_name_index(self):
        result = lines(fixture())[0]
        self.assertEqual(result['points'], [[100, 200], [97, 207]])
        self.assertEqual(result['pointMarks'], [0, 1])
        self.assertEqual(result['nameIndex'], 2)
        self.assertEqual(result['style'], 654)

    def test_without_optional_mark(self):
        result = lines(fixture(flags=1))[0]
        self.assertEqual(result['points'], [[100, 200], [97, 207]])
        self.assertEqual(result['pointMarks'], [0, 0])

    def test_truncation_at_every_boundary(self):
        raw = fixture()
        for end in range(len(raw)):
            with self.assertRaises(ValueError, msg=f'prefix {end}'):
                lines(raw[:end])

    def test_reject_unknown_suffix_and_trailing_data(self):
        for raw in [fixture(suffix=1), fixture() + b'\0', v(1000000)]:
            with self.assertRaises(ValueError):
                lines(raw)


if __name__ == '__main__':
    unittest.main()
