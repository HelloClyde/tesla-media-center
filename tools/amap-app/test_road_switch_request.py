import struct
import unittest
from xml.etree import ElementTree as ET

from road_switch_request import avoid_link_pair, encode_start_avoid_link
from road_switch_route import build_body, request_route, MAX_RESPONSE
from test_route_v51 import fixture, road_link_fixture
from tmc_route_helper import switch_road
import base64
from types import SimpleNamespace
from unittest.mock import patch


class RoadSwitchRequestTest(unittest.TestCase):
    def test_short_link_midpoints_and_long_link_interior_vertices(self):
        self.assertEqual(avoid_link_pair([(101, -101), (111, -111)]), ((106, -106), (109, -109)))
        points = [(100 + index, 200 + index) for index in range(6)]
        self.assertEqual(avoid_link_pair(points), (points[1], points[-3]))
        self.assertIsNone(avoid_link_pair([]))
        self.assertIsNone(avoid_link_pair([(1, 2)]))

    def test_xml_has_attributes_not_child_flags_and_float32_coordinates(self):
        pair = ((432000000, 108000000), (432001111, 108001111))
        root = ET.fromstring(encode_start_avoid_link([pair], 0, 2))
        self.assertEqual(root.attrib, {'hwflag': '0', 'switchaction': '2'})
        self.assertEqual([child.tag for child in root], ['linkPoint'])
        expected = struct.unpack('<f', struct.pack('<f', pair[1][0] / 3600000))[0]
        self.assertEqual(root.findtext('linkPoint/x2'), f'{expected:.6f}')
        self.assertEqual(ET.fromstring(encode_start_avoid_link([pair], 255, 128)).attrib,
                         {'hwflag': '-1', 'switchaction': '-128'})

    def test_rejects_bad_dimensions_coordinates_flags_and_oversized_payload(self):
        for points in ([[1]], [[True, 1]], [[1 << 31, 1]]):
            with self.assertRaises(ValueError): avoid_link_pair(points)
        pair = ((1, 2), (3, 4))
        for pairs in ([], [pair] * 17, [[(1, 2)]], [[(1, 2), (3, True)]]):
            with self.assertRaises(ValueError): encode_start_avoid_link(pairs, 0, 2)
        for flags in ((True, 1), (-1, 1), (0, 256)):
            with self.assertRaises(ValueError): encode_start_avoid_link([pair], *flags)

    def test_fresh_request_has_old_link_constraint_and_no_captured_session_values(self):
        root = ET.fromstring(build_body([120, 30], [120.2, 30.2], [[120, 30], [120.001, 30]], now=1700000000, heading=270))
        self.assertEqual(root.get('Uuid'), '1700000000000')
        self.assertIsNone(root.get('NaviID'))
        self.assertEqual(root.findtext('startpoint/x'), '120.000000')
        self.assertEqual(root.find('jump').get('sa'), '270.000000')
        self.assertEqual(root.find('startAvoidLink').attrib, {'hwflag': '0', 'switchaction': '0'})
        self.assertIsNone(root.find('PrevPath'))
        with self.assertRaises(ValueError): build_body([float('nan'), 30], [120, 30], [[120, 30], [121, 30]])

    def test_native_transfer_is_bounded_and_preserves_start_no_road(self):
        points = [[116.4, 39.9], [116.401, 39.9]]
        material = {'getAosChannel': 'test', 'getAosKey': 'test-only'}
        with patch('road_switch_route.encode_binary', return_value=b'encoded'), patch('road_switch_route.encode', side_effect=lambda value, assets: value):
            for raw, expected in ((fixture(route_metadata=1)[10:], True), (fixture(header_status=10)[10:], False)):
                response = SimpleNamespace(status_code=200, raw=SimpleNamespace(read=lambda *args, **kwargs: raw))
                with patch('requests.post') as post:
                    post.return_value.__enter__.return_value = response
                    result = request_route(points[0], points[-1], points, material, None, accuracy=32, speed=9)
                    self.assertEqual(result is not None, expected)
                    self.assertFalse(post.call_args.kwargs['allow_redirects'])
                    self.assertIn('sloc_precision=32', post.call_args.kwargs['params']['in'])
            response.raw.read = lambda *args, **kwargs: b'x' * (MAX_RESPONSE+1)
            with patch('requests.post') as post:
                post.return_value.__enter__.return_value = response
                with self.assertRaises(ValueError): request_route(points[0], points[-1], points, material, None)

    def test_current_link_must_belong_to_session_and_be_near_vehicle_before_transmission(self):
        payload = {'rawRoute': base64.b64encode(road_link_fixture()).decode(), 'routeIndex': 0,
                   'linkId': '9007199254740993', 'linkStart': 0, 'point': [116.4001, 39.9]}
        with patch('native_signer.load_material', return_value={}), patch('road_switch_route.request_route', return_value=fixture(route_metadata=1)[10:]) as request:
            result = switch_road(payload)
            self.assertEqual(result['state'], 'ready')
            self.assertEqual(request.call_args.args[2], [[116.4, 39.9], [116.4003, 39.9]])
            request.reset_mock()
            for change in ({'linkId': '1'}, {'linkStart': 1}, {'point': [120, 30]}, {'routeIndex': True}):
                with self.assertRaises(ValueError): switch_road({**payload, **change})
            request.assert_not_called()
            request.return_value = None
            self.assertEqual(switch_road(payload)['state'], 'absent')
