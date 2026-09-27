import struct
import unittest

from lane_boundary_points import boundary_points


def table(points):
    # A synthetic FlatBuffers table, never used as evidence of live geometry.
    return (struct.pack('<HHHH', 6, 8, 4, 0) + struct.pack('<iII', 8, 4, len(points))
            + b''.join(struct.pack('<3d', *point) for point in points))


class BoundaryPointsTests(unittest.TestCase):
    def test_raw_triples(self):
        points = [(1.25, -3.5, 0.0), (1e7, 2e7, -10.0)]
        self.assertEqual(boundary_points(table(points), 8), points)

    def test_missing_vector(self):
        self.assertEqual(boundary_points(table([]), 8), [])
        raw = bytearray(table([]))
        struct.pack_into('<H', raw, 4, 0)
        self.assertEqual(boundary_points(bytes(raw), 8), [])

    def test_truncation(self):
        raw = table([(1.0, 2.0, 3.0)])
        for length in range(len(raw)):
            with self.assertRaises(ValueError):
                boundary_points(raw[:length], 8)

    def test_invalid_offsets(self):
        original = table([(1.0, 2.0, 3.0)])
        for fmt, offset, value in [('<i', 8, 1000), ('<H', 0, 7),
                                   ('<H', 4, 7), ('<I', 12, 0),
                                   ('<I', 12, 10000), ('<I', 16, 100001)]:
            raw = bytearray(original)
            struct.pack_into(fmt, raw, offset, value)
            with self.assertRaises(ValueError):
                boundary_points(bytes(raw), 8)
        for offset in [-1, True, len(original)]:
            with self.assertRaises(ValueError):
                boundary_points(original, offset)

    def test_non_finite(self):
        for value in [float('nan'), float('inf'), float('-inf')]:
            with self.assertRaises(ValueError):
                boundary_points(table([(1, 2, value)]), 8)


if __name__ == '__main__':
    unittest.main()
