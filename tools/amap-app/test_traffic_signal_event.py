import json
import unittest

from traffic_signal_event import parse_native_signal_event


class TrafficSignalEventTest(unittest.TestCase):
    def test_native_envelope_maps_verified_statuses(self):
        event = {"dataType": 1, "data": json.dumps([{"statusInfos": [
            {"showType": 2, "status": 2, "mainAction": 1, "remainTime": 12},
            {"showType": 2, "status": 5, "mainAction": 2, "remainTime": 9},
            {"showType": 2, "status": 8, "mainAction": 8, "remainTime": 2},
        ]}])}
        self.assertEqual(parse_native_signal_event(event), [{"states": [
            {"phase": "red", "action": 1, "seconds": 12},
            {"phase": "green", "action": 2, "seconds": 9},
            {"phase": "yellow", "action": 8, "seconds": 2},
        ]}])

    def test_other_events_and_hidden_or_invalid_states_do_not_show(self):
        self.assertEqual(parse_native_signal_event({"dataType": 6, "data": ""}), [])
        self.assertEqual(parse_native_signal_event({"eventType": 26401, "commonInfos": []}), [])
        self.assertEqual(parse_native_signal_event({"statusInfos": [
            {"showType": 1, "status": 2, "mainAction": 1, "remainTime": 10},
            {"showType": 2, "status": 0, "mainAction": 1, "remainTime": 10},
            {"showType": 2, "status": 2, "mainAction": 1, "remainTime": -1},
        ]}), [])

    def test_native_countdown_event_matches_live_activity_shape(self):
        event = {"eventType": 26403, "commonInfos": [{"remainDis": 42,
            "statusInfos": [{"showType": 2, "status": 3, "mainAction": 1,
                             "remainTime": 11}]}]}
        self.assertEqual(parse_native_signal_event({"trafficLightInfo": event}),
                         [{"distanceMeters": 42, "states": [
                             {"phase": "red", "action": 1, "seconds": 11}]}])
        event["commonInfos"][0]["remainDis"] = 100000
        self.assertEqual(parse_native_signal_event(event), [])

    def test_rejects_malformed_payload(self):
        with self.assertRaises(ValueError):
            parse_native_signal_event({"dataType": 1, "data": "not json"})
        with self.assertRaises(ValueError):
            parse_native_signal_event({"statusInfos": "red"})


if __name__ == "__main__":
    unittest.main()
