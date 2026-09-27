import struct
import unittest

from inspect_route_prefix import inspect


def sample():
    payload = bytearray(87)
    payload[3] = 5
    payload[9:13] = b"\x03\x0aGj"
    payload[52] = 2
    for name in ("东华门路", "金宝街"):
        payload.extend(bytes((1, 2, len(name))) + name.encode("utf-16-le") + bytes(5))
    text = "东华门路金宝街"
    payload.extend(struct.pack("<H", len(text)) + text.encode("utf-16-le"))
    payload[:3] = len(payload).to_bytes(3, "little")
    return struct.pack("<HQ", 200, len(payload)) + payload


class PrefixTest(unittest.TestCase):
    def test_multiple_groups(self):
        result = inspect(sample())
        self.assertEqual([g[0]["text"] for g in result["groups"]], ["东华门路", "金宝街"])
        self.assertFalse(result["native_route_decoded"])

    def test_unknown_profile(self):
        data = bytearray(sample())
        data[13] = 6
        with self.assertRaises(ValueError):
            inspect(data)

    def test_invalid_record_length(self):
        data = bytearray(sample())
        data[99] = 255
        with self.assertRaises(ValueError):
            inspect(data)

    def test_truncated_envelope(self):
        with self.assertRaises(ValueError):
            inspect(sample()[:-1])


if __name__ == "__main__":
    unittest.main()
