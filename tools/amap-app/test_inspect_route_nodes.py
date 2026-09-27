import struct
import unittest

from inspect_route_nodes import inspect, inspect_reference_run


def sample(name_offset=0, span_start=0, coordinate=26817975):
    payload = bytearray(87)
    payload[3] = 5
    payload[9:13] = b"\x03\x0aGj"
    payload[52] = 1
    name = "测试路".encode("utf-16-le")
    payload.extend(bytes((1, 2, 3)) + name + struct.pack("<HBH", span_start, 1, 0))
    payload.extend(struct.pack("<H", 3) + name)
    payload.extend(struct.pack("<H", 1))
    payload.extend(struct.pack("<I", 450) + bytes(6) + bytes((3,)))
    payload.extend(struct.pack("<HII", name_offset, coordinate, 9194964))
    payload[:3] = len(payload).to_bytes(3, "little")
    return struct.pack("<HQ", 200, len(payload)) + payload


class NodesTest(unittest.TestCase):
    def test_named_node_and_group(self):
        result = inspect(sample())
        self.assertEqual(result["nodes"][0]["name"], "测试路")
        self.assertEqual(result["nodes"][0]["length_value_candidate"], 450)
        self.assertEqual(result["summary_groups"][0]["span_total_candidate"], 1)
        self.assertEqual(result["unparsed_native_bytes"], 0)
        self.assertFalse(result["complete_polyline"])

    def test_outside_name_dictionary(self):
        with self.assertRaises(ValueError):
            inspect(sample(name_offset=1))

    def test_invalid_summary_span(self):
        with self.assertRaises(ValueError):
            inspect(sample(span_start=1))

    def test_invalid_coordinate(self):
        with self.assertRaises(ValueError):
            inspect(sample(coordinate=0xFFFFFFFF))

    def test_reused_reference(self):
        payload = bytes((2, 0, 0, 1, 0, 0)) * 2
        result = inspect_reference_run(payload, 0, 2, 2)
        self.assertEqual([r["node_index_candidate"] for r in result], [1, 1])

    def test_invalid_reference(self):
        with self.assertRaises(ValueError):
            inspect_reference_run(bytes((2, 0, 0, 1, 0, 0)), 0, 1, 1)

    def test_truncated_reference(self):
        with self.assertRaises(ValueError):
            inspect_reference_run(bytes(5), 0, 1, 1)


if __name__ == "__main__":
    unittest.main()
