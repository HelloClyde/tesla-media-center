import unittest
from lane_request import encode_lane_request
from route_v51 import fields


class LaneRequestTests(unittest.TestCase):
    def test_descriptor_wire_layout(self):
        # Synthetic bytes, NOT a live lane-tile fixture.
        self.assertEqual(encode_lane_request([150], ['v1'], 'h1'),
                         bytes.fromhex('0a070896011202763112026831'))

    def test_ordered_pairs_and_uint32_boundary(self):
        result = fields(encode_lane_request([0xffffffff, 0], ['first', 'second'], 'hd'))
        self.assertEqual(result[2], [b'hd'])
        self.assertEqual([fields(v) for v in result[1]],
                         [{1:[0xffffffff],2:[b'first']},{1:[0],2:[b'second']}])

    def test_rejects_bmd_ids_mismatched_lists_and_duplicates(self):
        for ids, versions in [([14 << 48],['v']),([1,2],['v']),([],[]),
                              ([1,1],['v','v']),([True],['v']),([-1],['v']),
                              (list(range(65)),['v']*65)]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                encode_lane_request(ids, versions, 'h')

    def test_version_validation(self):
        for value in ['', 'a\0b', 'x'*1025, None, 12]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                encode_lane_request([1], [value], 'h')
            with self.subTest(value=value), self.assertRaises(ValueError):
                encode_lane_request([1], ['v'], value)


if __name__=='__main__': unittest.main()
