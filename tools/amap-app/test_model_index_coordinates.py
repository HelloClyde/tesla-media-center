import unittest

from model_index_coordinates import index_bounds


class IndexCoordinateTests(unittest.TestCase):
    def test_native_reference_vectors(self):
        # Outputs captured by executing 0x1446ab4 from the pinned native library
        # in Unicorn, independently of the Python port (103 cases compared).
        cases = [
            (0, 0, 0, [0.0, 0.0, 0.0, 0.0]),
            (1, 1, 1, [8.381903175442434e-08, 0.0, 8.381903175442434e-08, 0.0]),
            (9223372036854775807, 100, 200, [-4.274770617485046e-06,
                8.298084147552107e-06, 4.107132555966793e-06, -8.4657222032547e-06]),
            (9067994896918811722, 11087, 90120, [-0.017064129933714867,
                -31.106811175122857, -0.01613491214811802, -31.11436494626105]),
            (3670076030439752586, 7423, 84633, [104.45050982965645,
                -45.01630992628634, 104.45113193451014, -45.02340369857848]),
            (8157736277699334768, 91848, 35624, [-58.568739518523216,
                -82.71334670484066, -58.56104090809822, -82.71633267402649]),
        ]
        for identity, width, height, expected in cases:
            with self.subTest(identity=identity):
                for actual, reference in zip(index_bounds(identity, width, height), expected):
                    self.assertAlmostEqual(actual, reference, places=12)

    def test_invalid_inputs_rejected(self):
        for args in [(-1, 0, 0), (1 << 63, 0, 0), (True, 1, 1),
                     (0, -1, 0), (0, 1 << 31, 0), (0, 1.5, 2)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                index_bounds(*args)


if __name__ == '__main__':
    unittest.main()
