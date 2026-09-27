import unittest
from lane_response import decode_lane_response
from test_bmd_tile import field


class LaneResponseTests(unittest.TestCase):
    def test_nested_transport_preserves_binary(self):
        tile=field(1,123)+field(2,1)+field(3,b'\x00\xffopaque')+field(4,42)+field(6,7)
        raw=field(1,200)+field(5,field(1,b'block')+field(2,field(1,tile)))
        result=decode_lane_response(raw)
        self.assertEqual(result['blocks'][0]['records'],[{'tileId':123,'state':1,
            'payload':b'\x00\xffopaque','version':42,'field6':7}])
        self.assertFalse(result['verifiedLaneGeometry'])

    def test_empty_and_error_are_not_geometry_success(self):
        self.assertEqual(decode_lane_response(field(1,200))['blocks'],[])
        result=decode_lane_response(field(1,403)+field(2,b'denied'))
        self.assertEqual(result['status'],403)
        self.assertEqual(result['field2'],'denied')

    def test_rejects_wrong_types_duplicates_overflow_and_missing_status(self):
        for raw in [b'',field(1,b'200'),field(1,200)*2,field(1,1<<32),
                    field(1,200)+field(5,field(2,b'\x0a\xff'))]:
            with self.subTest(raw=raw),self.assertRaises(ValueError):decode_lane_response(raw)

    def test_truncated_nested_payload(self):
        inner=field(1,field(1,1)+field(3,b'data'))
        for size in range(1,len(inner)):
            raw=field(1,200)+field(5,field(2,inner[:size]))
            with self.subTest(size=size),self.assertRaises(ValueError):decode_lane_response(raw)

    def test_unknown_fields_and_absent_optional_values(self):
        raw=field(1,200)+field(90,b'future')+field(5,field(2,field(1,field(1,0))))
        record=decode_lane_response(raw)['blocks'][0]['records'][0]
        self.assertEqual(record['tileId'],0)
        self.assertIsNone(record['state'])
        self.assertIsNone(record['payload'])


if __name__=='__main__':unittest.main()
