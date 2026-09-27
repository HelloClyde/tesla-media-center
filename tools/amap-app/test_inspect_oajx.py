import struct
import unittest
from inspect_oajx import inspect


def sample():
    data = bytearray(79)
    data[:8] = b"ion\n002\0"
    struct.pack_into("<4I", data, 24, 48, 1, 68, 3)
    struct.pack_into("<5I", data, 48, 123, 68, 3, 71, 8)
    data[68:71] = b"abc"
    data[71:] = b"spx\n003\0"
    return data


class ContainerTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(inspect(sample())["count"], 1)

    def test_truncated(self):
        for length in (0, 7, 47, 67, 70, 78):
            with self.subTest(length=length), self.assertRaises(ValueError):
                inspect(sample()[:length])

    def test_invalid_offsets_and_sizes(self):
        for position, value in ((24, 40), (28, 0xffffffff), (32, 0),
                                (36, 0xffffffff), (52, 0), (56, 4),
                                (60, 72), (64, 0xffffffff)):
            data = sample()
            struct.pack_into("<I", data, position, value)
            with self.subTest(position=position), self.assertRaises(ValueError):
                inspect(data)

    def test_unknown_child_and_trailing_bytes(self):
        data = sample()
        data[71] = 0
        for invalid in (data, sample() + b"extra"):
            with self.assertRaises(ValueError):
                inspect(invalid)


if __name__ == "__main__":
    unittest.main()
