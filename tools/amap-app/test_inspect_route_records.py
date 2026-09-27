import unittest

from inspect_route_records import read_records


def record(labels=("推荐",), index=0):
    data = bytearray.fromhex("80010001000100000f00")
    data[9] = len(labels)
    for text in labels:
        encoded = text.encode("utf-16-le")
        data.extend(bytes((1, len(encoded) // 2)) + encoded + b"\0")
    data.extend(b"\x02\0\0" + b"\x01\0\0" + index.to_bytes(3, "little"))
    data.extend(bytes.fromhex("01000a0e00000400000000fd"))
    return data


class RecordsTest(unittest.TestCase):
    def test_variable_labels_and_shared_node(self):
        first = record(("大众常选", "时间短", "距离短"))
        second = record(("备选二", "测试🎵"))
        result, end = read_records(first + second, 0, 2, 1)
        self.assertEqual(end, len(first + second))
        self.assertEqual(result[1]["payload_offset"], len(first))
        self.assertEqual(result[1]["labels"][1]["text"], "测试🎵")
        self.assertEqual([r["references"][0]["node_index_candidate"] for r in result], [0, 0])

    def test_all_truncations_rejected(self):
        data = record()
        for size in range(len(data)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                read_records(data[:size], 0, 1, 1)

    def test_bad_reference(self):
        with self.assertRaises(ValueError):
            read_records(record(index=1), 0, 1, 1)

    def test_unknown_trailer(self):
        data = record()
        data[-1] = 0
        with self.assertRaises(ValueError):
            read_records(data, 0, 1, 1)

    def test_unknown_header(self):
        data = record()
        data[0] = 127
        with self.assertRaises(ValueError):
            read_records(data, 0, 1, 1)


if __name__ == "__main__":
    unittest.main()
