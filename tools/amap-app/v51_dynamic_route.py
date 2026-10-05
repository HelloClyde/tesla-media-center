"""Extract research-only native navigation fields from an App 5.1 route.

The header ID and data version map to native path fields, but a server-side
navigation session and the full dynamic event schema remain unverified. Route
field 6 is a wire route value, not the locally allocated main_path_id. Link IDs
reproduce a stable cross-route invariant. Never expose this opaque result
through the public TMC route DTO as live signal information.
"""

from __future__ import annotations

import re
from pathlib import Path

from dynamic_route_links import decode_v51_link_deltas, encode_link_adcodes, encode_link_boundary_properties, encode_link_ids, encode_segment_link_ids
from route_v51 import delta_values, fields, one, unpack


_HEX32 = re.compile(r"[0-9a-fA-F]{32}\Z")


def _signed_word(value: int) -> int:
    return value if value < 1 << 31 else value - (1 << 32)


def extract(raw: bytes, route_index: int = 0) -> dict:
    if type(route_index) is not int or route_index < 0:
        raise ValueError("invalid route index")
    envelope = fields(unpack(raw))
    header = fields(one(envelope, 1, b""))
    message = fields(one(envelope, 2, b""))
    if one(header, 1) != 51 or one(header, 3) != 0 or one(message, 1) != 0:
        raise ValueError("unsuccessful 5.1 route")
    data_vers = one(header, 2, None)
    if type(data_vers) is not int or not 0 <= data_vers <= 65535:
        raise ValueError("invalid route data version")
    route_blobs = message.get(7, [])
    if not 0 <= route_index < len(route_blobs) <= 10:
        raise ValueError("route index outside result")
    route = fields(route_blobs[route_index])
    session_bytes = one(header, 5, b"")
    if not isinstance(session_bytes, bytes) or len(session_bytes) != 32:
        raise ValueError("invalid navigation ID")
    session = session_bytes.decode("ascii")
    if not _HEX32.fullmatch(session):
        raise ValueError("invalid navigation ID")
    path_bytes, base_bytes = one(route, 6, b""), one(route, 9, b"")
    if not isinstance(path_bytes, bytes) or len(path_bytes) != 4 or not isinstance(base_bytes, bytes) or len(base_bytes) != 8:
        raise ValueError("invalid route identifiers")
    raw_length = one(route, 1, None)
    if type(raw_length) is not int or not 0 < raw_length <= 100 * 10_000_000:
        raise ValueError("invalid route length")
    raw_deltas: list[int] = []
    lengths: list[int] = []
    road_classes: list[int] = []
    link_starts: list[tuple[float, float]] = []
    link_points: list[list[tuple[float, float]]] = []
    segment_link_counts: list[int] = []
    segment_boundary_properties: list[list[tuple[int, int]]] = []
    segment_adcodes: list[list[int]] = []
    for segment_blob in route.get(10, []):
        segment = fields(segment_blob)
        coordinates = fields(one(segment, 4, b""))
        xs = delta_values(one(coordinates, 1, b""))
        ys = delta_values(one(coordinates, 2, b""))
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError("invalid segment coordinates")
        if any(not -180 <= x <= 180 or not -90 <= y <= 90 for x, y in zip(xs, ys)):
            raise ValueError("coordinates outside world bounds")
        covered = 0
        segment_link_count = 0
        road_class = 11  # DriveLinkImpl getter fallback before a road record exists.
        road_property = -1  # +0xe8 virtual getter fallback before a road record exists.
        boundary_properties: list[tuple[int, int]] = []
        adcodes: list[int] = []
        adcode = 0
        for link_blob in segment.get(3, []):
            link = fields(link_blob)
            span = fields(one(link, 8, b""))
            start, count = one(span, 1, -1), one(span, 2, 0)
            delta, length = one(link, 1, None), one(link, 2, None)
            if type(start) is not int or type(count) is not int or start != covered or count < 2 or start + count > len(xs):
                raise ValueError("invalid link span")
            # The native wire field is wider than 16 bits: a real 666 m
            # highway link arrives as 66,600 centimetres.
            if type(delta) is not int or not 0 <= delta < 1 << 64 or type(length) is not int or not 0 < length <= 1_000_000:
                raise ValueError("invalid link value")
            if 7 in link:
                attributes = fields(one(link, 7))
                next_class = one(attributes, 1, 0)
                if type(next_class) is not int or not 0 <= next_class <= 0xFFFFFFFF:
                    raise ValueError("invalid road class")
                next_property = one(attributes, 2, 0)
                if type(next_property) is not int or not 0 <= next_property <= 0xFFFFFFFF:
                    raise ValueError("invalid road property")
                road_class = next_class
                road_property = _signed_word(next_property)
                # The native assembler creates a new segment road record for
                # this attribute. Links without one inherit the preceding
                # record's administrative code within the segment.
                next_adcode = one(attributes, 8, 0)
                if type(next_adcode) is not int or not 0 <= next_adcode <= 0xFFFFFFFF:
                    raise ValueError("invalid link adcode")
                adcode = next_adcode
            raw_deltas.append(delta)
            segment_link_count += 1
            # libassembly_kit.so 0xbb794-0xbb7a8 stores the 5.1 link
            # length divided by 100 in DriveLinkImpl+0x18. Horus reads
            # that slot for route_links_length, so these are whole metres.
            lengths.append(length // 100)
            road_classes.append(road_class)
            boundary_properties.append((_signed_word(road_class), road_property))
            adcodes.append(adcode)
            link_starts.append((xs[start], ys[start]))
            link_points.append(list(zip(xs[start:start + count], ys[start:start + count])))
            covered = start + count - 1
            if len(raw_deltas) > 100000:
                raise ValueError("too many links")
        if covered != len(xs) - 1:
            raise ValueError("incomplete segment link coverage")
        segment_link_counts.append(segment_link_count)
        segment_boundary_properties.append(boundary_properties)
        segment_adcodes.append(adcodes)
    if not raw_deltas:
        raise ValueError("route without links")
    ids = decode_v51_link_deltas(int.from_bytes(base_bytes, "little"), raw_deltas)
    segment_ids: list[list[int]] = []
    offset = 0
    for count in segment_link_counts:
        segment_ids.append(ids[offset:offset + count])
        offset += count
    return {
        "navigation_id_candidate": session,
        "eta_data_vers": data_vers,
        "wire_route_field6": int.from_bytes(path_bytes, "little"),
        # libassembly_kit.so 0xbaa8c-0xbaa98 stores wire route field 1 / 100
        # in DrivePathImpl+0x18. Horus event length reads that same slot.
        "length_candidate": raw_length // 100,
        # libamaphorus.so 0x6ad56c-0x6ad588 initializes the before-navigation
        # segment window to [0, segment_count - 1]; mode 3 can narrow it.
        "startsegmentidx_candidate": 0,
        "endsegmentidx_candidate": len(segment_link_counts) - 1,
        "route_links_candidate": encode_link_ids(ids),
        "segment_candidate": encode_segment_link_ids(segment_ids),
        "links_prop_start_end_candidate": encode_link_boundary_properties(segment_boundary_properties),
        "links_adcode_candidate": encode_link_adcodes(segment_adcodes),
        # For beforeNavi, the native event constructor zero-initializes
        # these vectors and the builder does not populate either field.
        "segment_distance_candidate": [],
        "links_eta_candidate": [],
        "route_links_length_candidate": lengths,
        "route_links_road_class_candidate": road_classes,
        "route_links_start_point_candidate": link_starts,
        "route_links_points_candidate": link_points,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    parser.add_argument("--route", type=int, default=0)
    args = parser.parse_args()
    result = extract(args.response.read_bytes(), args.route)
    print(json.dumps({"navigation_id_candidate_length": len(result["navigation_id_candidate"]),
                      "wire_route_field6": result["wire_route_field6"],
                      "link_count": len(result["route_links_candidate"]),
                      "first_link": result["route_links_candidate"][0],
                      "last_link_start": result["route_links_start_point_candidate"][-1]}))
