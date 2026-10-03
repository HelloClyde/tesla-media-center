"""Native-field extraction from a small valid 5.1 route response."""

import struct

from test_route_v51 import msg, packed
from v51_dynamic_route import extract


def _response() -> bytes:
    first = msg(f1=0, f2=1500, f7=msg(f1=6, f2=3, f8=110101),
                f8=msg(f1=0, f2=2))
    second = msg(f1=2, f2=17600, f8=msg(f1=1, f2=2))
    segment = msg(f3=[first, second],
                  f4=msg(f1=packed((116.4, 116.4002, 116.401)),
                         f2=packed((39.9, 39.9, 39.9))))
    route = msg(f1=19100, f6=struct.pack("<I", 42),
                f9=struct.pack("<Q", 0x4712E5A9802009D3), f10=segment)
    protobuf = msg(f1=msg(f1=51, f2=300, f3=0, f5=b"a" * 32),
                   f2=msg(f1=0, f7=route))
    size = 64 + len(protobuf)
    body = struct.pack("<IHI", 31, 1, size).ljust(32, b"\0")
    body += struct.pack("<HHII", 0, 1, len(protobuf), len(protobuf)).ljust(32, b"\0")
    return struct.pack("<HQ", 200, size) + body + protobuf


def test_native_route_and_link_lengths_use_whole_metres():
    result = extract(_response())
    assert result["length_candidate"] == 191
    assert result["route_links_length_candidate"] == [15, 176]
    assert sum(result["route_links_length_candidate"]) == result["length_candidate"]
    assert result["links_adcode_candidate"] == {"110101": "1,2"}
