import unittest
from tmc_lane_helper import boundary_dto, boundary_dto_with_kinds


class LaneDtoTest(unittest.TestCase):
    def test_height_omission_and_direction_independent_deduplication(self):
        a, b = [116.123456789, 39.9, 99999], [116.124, 39.901, -80000]
        self.assertEqual(boundary_dto([[a, a, b], [b, a], [a]]),
                         [[(116.1234568, 39.9), (116.124, 39.901)]])

    def test_bad_coordinates_fail(self):
        for point in [[float('nan'), 40], [181, 40], [116, 90]]:
            with self.assertRaises(ValueError):
                boundary_dto([[point, [116, 40]]])

    def test_raw_kind_stays_aligned_after_reverse_deduplication(self):
        a, b, c = [116, 40], [116.0001, 40], [116.0002, 40]
        lines, kinds = boundary_dto_with_kinds([[a, b], [b, a], [b, c]], [1, 3, 1])
        self.assertEqual(lines, [[(116, 40), (116.0001, 40)],
                                 [(116.0001, 40), (116.0002, 40)]])
        self.assertEqual(kinds, [3, 1])
        with self.assertRaises(ValueError):
            boundary_dto_with_kinds([[a, b]], [])
