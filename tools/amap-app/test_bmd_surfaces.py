import struct
import unittest
from bmd_surfaces import surfaces
from test_bmd_geometry import packed, v


def fixture(width=12):
    head = v(1) + struct.pack('<H', 655) + v(1) + struct.pack('<IHB', 123, 0, width) + v(1)
    ring = v(3) + packed((100, width), (200, width), (1, 1), (0, 1), (5, 5))
    ring += packed((-3, 5), (7, 5), (0, 1), (2, 5), (-4, 5), (1, 1))
    return head + v(0) + v(1) + ring


class SurfaceTests(unittest.TestCase):
    def test_geometry_marks_and_precision(self):
        for width in (12, 13):
            feature = surfaces(fixture(width))[0]
            self.assertEqual(feature['coordinateBits'], width)
            self.assertEqual(feature['rings'][0]['points'], [[100, 200], [97, 207], [99, 203]])
            self.assertEqual(feature['rings'][0]['pointMarks'], [1, 0, 1])

    def test_truncation_and_trailing_bytes(self):
        raw = fixture()
        for end in range(len(raw)):
            with self.assertRaises(ValueError):
                surfaces(raw[:end])
        with self.assertRaises(ValueError):
            surfaces(raw + b'\0')

    def test_count_bound(self):
        with self.assertRaises(ValueError):
            surfaces(v(1000000))


if __name__ == '__main__':
    unittest.main()
