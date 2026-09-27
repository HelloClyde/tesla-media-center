"""Synthetic fixtures only: these tests do not establish live API compatibility."""

import struct
import unittest

from inspect_envelope import inspect


def sample(text="12,34"):
    encoded = text.encode("utf-16-le")
    return struct.pack("<HQ", 200, 4) + b"FAKE" + struct.pack("<HQ", 100, len(encoded)) + encoded


class EnvelopeTests(unittest.TestCase):
    def test_synthetic_taxi_extension(self):
        result = inspect(sample())
        self.assertEqual(result["taxi_cost_values"], [12, 34])
        self.assertEqual(result["extension_offset_in_payload"], 4)
        self.assertFalse(result["native_route_decoded"])

    def test_truncated_headers(self):
        for size in range(10):
            with self.subTest(size=size), self.assertRaises(ValueError):
                inspect(sample()[:size])
        for tail in [b"d", b"d\x00", b"d\x00" + bytes(7)]:
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                inspect(struct.pack("<HQ", 200, 0) + tail)

    def test_invalid_markers_offsets_and_lengths(self):
        for data in [struct.pack("<HQ", 201, 0),
                     struct.pack("<HQ", 200, 1),
                     struct.pack("<HQ", 200, 2**32),
                     struct.pack("<HQHQ", 200, 0, 100, 1) + b"x",
                     struct.pack("<HQHQ", 200, 0, 100, 100)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                inspect(data)

    def test_malformed_text(self):
        for text in ["1,", "x", "2147483648", "-2147483649", "1, 2"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                inspect(sample(text))
        with self.assertRaises(ValueError):
            inspect(struct.pack("<HQHQ", 200, 0, 100, 2) + b"\x00\xd8")

    def test_unknown_and_missing_extensions(self):
        self.assertEqual(inspect(struct.pack("<HQ", 200, 0))["extension_state"], "absent-unverified")
        self.assertEqual(inspect(struct.pack("<HQH", 200, 0, 101))["extension_state"], "unknown")

    def test_empty_and_extra_bytes(self):
        self.assertEqual(inspect(sample(""))["taxi_cost_values"], [])
        self.assertEqual(inspect(sample() + b"extra")["unparsed_trailing_bytes"], 5)


if __name__ == "__main__":
    unittest.main()
