"""Compare 5.1 link-ID interpretations across route alternatives.

This is an offline research tool. Matching geometry is only a comparison key;
the ZigZag interpretation agrees across saved routes, but native event
identity is still unconfirmed.
"""

import argparse
import json
from pathlib import Path

from route_v51 import delta_values, fields, one, unpack


MASK64 = (1 << 64) - 1


def route_links(route_blob: bytes) -> list[dict]:
    route = fields(route_blob)
    base_bytes = one(route, 9, b"")
    if len(base_bytes) != 8:
        raise ValueError("route lacks eight-byte field-9 base")
    base = int.from_bytes(base_bytes, "little")
    cumulative = base
    zigzag = base
    result = []
    for segment_blob in route.get(10, []):
        segment = fields(segment_blob)
        coordinates = fields(one(segment, 4, b""))
        points = tuple(zip(delta_values(one(coordinates, 1, b"")),
                           delta_values(one(coordinates, 2, b""))))
        for link_blob in segment.get(3, []):
            link = fields(link_blob)
            span = fields(one(link, 8, b""))
            start, count = one(span, 1, -1), one(span, 2, 0)
            if start < 0 or count < 2 or start + count > len(points):
                raise ValueError("invalid link geometry span")
            value = one(link, 1, None)
            if type(value) is not int or not 0 <= value <= MASK64:
                raise ValueError("invalid link field 1")
            if result:
                cumulative = (cumulative + value) & MASK64
            zigzag = (zigzag + ((value >> 1) ^ -(value & 1))) & MASK64
            result.append({
                "geometry": points[start:start + count],
                "field1": value,
                "cumulative_candidate": cumulative,
                "independent_candidate": (base + value) & MASK64,
                "zigzag_candidate": zigzag,
            })
    return result


def compare(raw: bytes, left_index: int = 0, right_index: int = 1) -> dict:
    message = fields(one(fields(unpack(raw)), 2, b""))
    routes = message.get(7, [])
    if min(left_index, right_index) < 0 or max(left_index, right_index) >= len(routes):
        raise ValueError("route alternative index out of range")
    left, right = route_links(routes[left_index]), route_links(routes[right_index])
    left_by_geometry = {link["geometry"]: link for link in left}
    matched = [(left_by_geometry[link["geometry"]], link) for link in right
               if link["geometry"] in left_by_geometry]
    return {
        "left_links": len(left),
        "right_links": len(right),
        "shared_geometry": len(matched),
        "matching_field1": sum(a["field1"] == b["field1"] for a, b in matched),
        "matching_cumulative_candidate": sum(
            a["cumulative_candidate"] == b["cumulative_candidate"] for a, b in matched
        ),
        "matching_independent_candidate": sum(
            a["independent_candidate"] == b["independent_candidate"] for a, b in matched
        ),
        "matching_zigzag_candidate": sum(
            a["zigzag_candidate"] == b["zigzag_candidate"] for a, b in matched
        ),
    }


def compare_captures(left_raw: bytes, right_raw: bytes) -> dict:
    """Compare every route alternative between two saved responses."""
    def all_links(raw: bytes) -> list[dict]:
        message = fields(one(fields(unpack(raw)), 2, b""))
        return [link for route in message.get(7, []) for link in route_links(route)]

    left, right = all_links(left_raw), all_links(right_raw)
    left_by_geometry = {link["geometry"]: link for link in left}
    matched = [(left_by_geometry[link["geometry"]], link) for link in right
               if link["geometry"] in left_by_geometry]
    return {
        "left_links": len(left),
        "right_links": len(right),
        "shared_geometry": len(matched),
        "matching_raw_cumulative": sum(
            a["cumulative_candidate"] == b["cumulative_candidate"] for a, b in matched
        ),
        "matching_zigzag": sum(
            a["zigzag_candidate"] == b["zigzag_candidate"] for a, b in matched
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    parser.add_argument("--other", type=Path, help="compare all routes with another saved response")
    parser.add_argument("--left", type=int, default=0)
    parser.add_argument("--right", type=int, default=1)
    args = parser.parse_args()
    left_raw = args.response.read_bytes()
    result = (compare_captures(left_raw, args.other.read_bytes()) if args.other
              else compare(left_raw, args.left, args.right))
    print(json.dumps(result, indent=2))
