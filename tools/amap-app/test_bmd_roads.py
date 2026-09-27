import unittest
from bmd_roads import road_levels
from test_bmd_tile import BmdTests, vint


def tile(block):
    raw=bytes([1,40,0])+block
    return BmdTests().make_bmd([(31,0,len(raw))],raw)


class RoadLevelTests(unittest.TestCase):
    def test_markers_signed_and_repeated_feature(self):
        block=bytes([1,3,0,0,1,0,1,255,0,3,0])
        self.assertEqual(road_levels(tile(block),[4]),{0:[[0,1],[1,-1],[3,0]]})

    def test_shared_markers(self):
        self.assertEqual(road_levels(tile(bytes([2,1,2,0,1,2,1])),[3,4]),{0:[[2,1]],1:[[2,1]]})

    def test_absent_attribute(self):
        self.assertEqual(road_levels(BmdTests().make_bmd([(30,0,1)],b'\0'),[2]),{})

    def test_invalid_references_truncation_and_trailing_bytes(self):
        good=bytes([1,2,0,0,1,0,2,255])
        bad=[good[:i] for i in range(len(good))]
        bad += [good+b'\0',bytes([1,1,1,0,1]),bytes([1,1,0,3,1]),
                bytes([1,2,0,0,1,0,0,1]),bytes([2,1,2,0,0,0,1]),
                bytes([3,0]),bytes([1])+vint(500001)]
        for raw in bad:
            with self.subTest(raw=raw),self.assertRaises((ValueError,IndexError)):
                road_levels(tile(raw),[3])


if __name__=='__main__': unittest.main()
