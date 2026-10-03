import unittest

from eta_pop_lights import parse_eta_pop_lights


class EtaPopLightsTest(unittest.TestCase):
    def test_decodes_nested_native_schema_without_inventing_phase(self):
        body = {"data": {"radar": {"popLights": [{
            "countDown": {"lon": 116.4, "lat": 39.9},
            "countDownDistance": 180,
            "state": {"lon": 116.401, "lat": 39.901},
            "stateDistance": 120,
            "location": {"lon": 116.402, "lat": 39.902},
            "nodeId": 1234567890123,
            "linkId": 9876543210123,
            "greenEndOffset": 15,
            "dirs": [{"dir": 2, "showType": 1, "phase": 3,
                      "lightType": 4, "controlLight": 1,
                      "lightStates": [{"type": 5, "stime": 1234567890123,
                                       "etime": 1234567900123,
                                       "signalTag": 2, "signalChange": 1}]}],
        }]}}}
        self.assertEqual(parse_eta_pop_lights(body), body["data"]["radar"]["popLights"])

    def test_missing_radar_has_no_lights(self):
        self.assertEqual(parse_eta_pop_lights({"data": {}}), [])

    def test_rejects_wrong_native_types_and_unbounded_lists(self):
        for light in ({"nodeId": True}, {"countDown": 10},
                      {"dirs": [{"lightStates": [{"stime": "12"}]}]},
                      {"dirs": [{}] * 17}):
            with self.subTest(light=light), self.assertRaises(ValueError):
                parse_eta_pop_lights({"data": {"radar": {"popLights": [light]}}})


if __name__ == "__main__":
    unittest.main()
