import struct
import unittest

from inspect_route_blocks import read_blocks, simple_geometry, UnsupportedGeometry


def geometry_block():
    data = bytearray(struct.pack("<HHBB", 0, 0, 0, 5))
    data.extend(b"\x0d\0\0")  # Synthetic empty opaque metadata.
    data.extend(struct.pack("<H", 1) + bytes(7) + bytes((2,)))
    for mode, dx, dy, length in [(0, -200, 300, 180), (1, -1, 37, 17)]:
        data.extend(struct.pack("<IHHHHBH", 1, length, 0, 0, 7, 10, 12))
        data.extend(struct.pack("<H", (mode << 14) | 1))
        data.extend(struct.pack("<hh" if mode == 0 else "<bb", dx, dy))
    struct.pack_into("<H", data, 0, len(data))
    return data


class BlocksTest(unittest.TestCase):
    def test_optional_link_fields_have_independent_boundaries(self):
        # Synthetic extension, two 4-byte fields, descriptor payload and two
        # 7-byte turn records. The coordinate must not absorb opaque metadata.
        data = bytearray(struct.pack("<HHBB", 0, 0, 0, 5))
        data.extend(b"\x0d\0\0" + struct.pack("<H", 1) + bytes(7) + b"\x01")
        data.extend(struct.pack("<IH", 42, 7))
        data.extend(b"\xf3\x05" + bytes(8) + b"\x1f\xc1" + bytes(9) + b"\0")
        data.extend(b"\x02" + bytes(14))
        data.extend(struct.pack("<HBHHhh", 263, 10, 12, 1, -7, 8))
        struct.pack_into("<H", data, 0, len(data))
        result = simple_geometry(data, [100, 200])
        self.assertEqual(result["points_raw"], [[100, 200], [93, 208]])
        self.assertEqual(result["links"][0]["unknown_extension"], 5)
        self.assertEqual(result["length_value_sum_candidate"], 7)

    def test_unknown_descriptor_rejected(self):
        data = geometry_block()
        # Header 9 + group count 2 + attributes 8 + id/length 6 + flags/meta 2.
        data[27] = 2
        with self.assertRaises(UnsupportedGeometry):
            simple_geometry(data, [1000, 2000])

    def test_unverified_coordinate_mode_rejected(self):
        data = geometry_block()
        struct.pack_into("<H", data, 34, 0x8001)
        with self.assertRaises(UnsupportedGeometry):
            simple_geometry(data, [1000, 2000])

    def test_signed_coordinate_modes(self):
        result = simple_geometry(geometry_block(), [1000, 2000])
        self.assertEqual(result["points_raw"], [[1000, 2000], [800, 2300], [799, 2337]])
        self.assertEqual(result["length_value_sum_candidate"], 197)

    def test_partial_geometry_rejected(self):
        with self.assertRaises(UnsupportedGeometry):
            simple_geometry(geometry_block()[:-1], [1000, 2000])

    def test_unknown_flags(self):
        data = geometry_block()
        data[5] = 0x85
        with self.assertRaises(UnsupportedGeometry):
            simple_geometry(data, [1000, 2000])

    def test_multi_group_framing(self):
        first = struct.pack("<HHBB", 6, 0, 0, 1)
        second = struct.pack("<HHBB", 6, 0, 1, 1)
        records = [{"references": [{"node_index_candidate": 0}]}] * 2
        result = read_blocks(first + second, 0, records)
        self.assertEqual([(b["group"], b["index"]) for b in result], [(0, 0), (1, 0)])

    def test_invalid_size(self):
        records = [{"references": [{"node_index_candidate": 0}]}]
        for size in (0, 5, 7):
            with self.subTest(size=size), self.assertRaises(ValueError):
                read_blocks(struct.pack("<HHBB", size, 0, 0, 1), 0, records)

    def test_wrong_index(self):
        with self.assertRaises(ValueError):
            read_blocks(struct.pack("<HHBB", 6, 1, 0, 1), 0,
                        [{"references": [{"node_index_candidate": 0}]}])

    def test_unframed_tail_rejected(self):
        with self.assertRaises(ValueError):
            read_blocks(struct.pack("<HHBB", 6, 0, 0, 1) + b"X", 0,
                        [{"references": [{"node_index_candidate": 0}]}])


if __name__ == "__main__":
    unittest.main()
