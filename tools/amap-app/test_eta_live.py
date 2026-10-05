import json
import struct
import time
import unittest
import zlib
from urllib.parse import parse_qs
from xml.etree import ElementTree as ET

from eta_live import build_eta_body, decode_eta_lights


class EtaLiveTest(unittest.TestCase):
    def setUp(self):
        self.context = {"navigation_id_candidate": "a" * 32,
                        "eta_data_vers": 2695, "wire_route_field6": 1234,
                        "route_links_candidate": ["91234", "-42"],
                        "route_links_start_point_candidate": [(120.1, 30.1), (120.18, 30.18)],
                        "route_links_points_candidate": [
                            [(120.1, 30.1), (120.18, 30.18)],
                            [(120.18, 30.18), (120.2, 30.2)],
                        ],
                        "route_links_length_candidate": [20, 4]}
        self.route = {"path": [[120.1, 30.1], [120.2, 30.2]]}

    def frame(self, data, *, status=0, path_id=1234, timestamp=None):
        now = int(time.time())
        payload = {"controlflag": 0, "status": status, "timestamp": timestamp or now * 1000,
                   "data": {"onlineNavi": {"commonPoints": [
                       {"pathId": path_id, "location": {"lon": 120.15, "lat": 30.15},
                        "lightInfo": {"dir": 8, "lightStates": [
                            {"type": 1, "stime": now - 5, "etime": now + 10},
                            {"type": 11, "stime": now + 10, "etime": now + 30}]}}]}}}
        if data is not None:
            payload = data
        unpacked = b"native-prefix" + json.dumps(payload).encode()
        compressed = zlib.compress(unpacked)
        header = struct.pack("<IHHBHBBII32s", 53 + len(compressed), 20, 2695,
                             0, 200, 0, 1, 0, len(unpacked), b"a" * 32)
        return header + compressed

    def test_generated_request_uses_current_location_and_route(self):
        wire = build_eta_body([self.route], [self.context], 0, [120.15, 30.15],
                              speed=5, heading=90, now=1700000000)
        self.assertEqual(wire[:1], b"0")
        self.assertIn(b"<![CDATA[", wire)
        root = ET.fromstring(wire[1:])
        self.assertEqual(root.attrib["NaviID"], "a" * 32)
        self.assertEqual(root.findtext("curloc/x"), "120.150000")
        self.assertEqual(root.find("path").attrib["id"], "1234")
        self.assertEqual(root.findtext("path/roadlinks"), "91234;-42")
        params = parse_qs(root.findtext("ETAInfo/TRRequestData"))
        self.assertEqual(json.loads(params["frontParam"][0])["prePoint"]["time"], 1700000000)

    def test_moving_vehicle_slices_remaining_links(self):
        wire = build_eta_body([self.route], [self.context], 0, [120.19, 30.19], now=1700000001)
        root = ET.fromstring(wire[1:])
        self.assertEqual(root.findtext("path/startpoint/x"), "120.190000")
        self.assertEqual(root.findtext("path/routestartpoint/x"), "120.100000")
        self.assertEqual(root.findtext("path/roadlinks"), "91192")
        self.assertEqual(root.find("path/linklens").attrib["startlen"], "2")

    def test_curved_link_matches_native_vertices_instead_of_endpoint_chord(self):
        self.context["route_links_candidate"] = ["91234"]
        self.context["route_links_start_point_candidate"] = [(120.0, 30.0)]
        self.context["route_links_points_candidate"] = [[
            (120.0, 30.0), (120.004, 30.0), (120.004, 30.004),
        ]]
        self.context["route_links_length_candidate"] = [900]
        self.route["path"] = [[120.0, 30.0], [120.004, 30.004]]

        wire = build_eta_body([self.route], [self.context], 0,
                              [120.004, 30.0], now=1700000001)
        root = ET.fromstring(wire[1:])
        self.assertEqual(root.findtext("path/roadlinks"), "91234")
        # The corner lies over 200 m from the endpoint chord, but exactly on
        # the route. The travelled portion uses the real polyline length.
        startlen = int(root.find("path/linklens").attrib["startlen"])
        self.assertGreater(startlen, 350)
        self.assertLess(startlen, 450)

    def test_inconsistent_link_geometry_is_rejected(self):
        self.context["route_links_points_candidate"][0][0] = (120.11, 30.1)
        with self.assertRaisesRegex(ValueError, "geometry"):
            build_eta_body([self.route], [self.context], 0, [120.15, 30.15])

    def test_route_progress_disambiguates_repeated_road_geometry(self):
        self.context["route_links_candidate"] = ["91234", "1"]
        self.context["route_links_start_point_candidate"] = [
            (120.0, 30.0), (120.004, 30.0)]
        self.context["route_links_points_candidate"] = [
            [(120.0, 30.0), (120.004, 30.0)],
            [(120.004, 30.0), (120.0, 30.0)],
        ]
        self.context["route_links_length_candidate"] = [385, 385]
        self.route = {"path": [[120.0, 30.0], [120.004, 30.0], [120.0, 30.0]],
                      "distance": 770}
        position = [120.002, 30.0]
        first = ET.fromstring(build_eta_body(
            [self.route], [self.context], 0, position, progress_hint=190)[1:])
        returning = ET.fromstring(build_eta_body(
            [self.route], [self.context], 0, position, progress_hint=580)[1:])
        self.assertEqual(first.findtext("path/roadlinks"), "91234;1")
        self.assertEqual(returning.findtext("path/roadlinks"), "91235")
        with self.assertRaisesRegex(ValueError, "progress"):
            build_eta_body([self.route], [self.context], 0, position, progress_hint=2000)

    def test_live_phases_require_matching_session_path_and_fresh_timestamp(self):
        raw = self.frame(None)
        result = decode_eta_lights(raw, "a" * 32, 1234)
        self.assertEqual(len(result["lights"]), 1)
        self.assertEqual([p["color"] for p in result["lights"][0]["phases"]], ["red", "green"])
        self.assertEqual(decode_eta_lights(raw, "a" * 32, 999)["lights"], [])
        with self.assertRaisesRegex(ValueError, "match"):
            decode_eta_lights(raw, "b" * 32, 1234)
        with self.assertRaisesRegex(ValueError, "stale"):
            decode_eta_lights(self.frame(None, timestamp=1000), "a" * 32, 1234)
        with self.assertRaisesRegex(ValueError, "rejected"):
            decode_eta_lights(self.frame(None, status=100004), "a" * 32, 1234)


if __name__ == "__main__":
    unittest.main()
