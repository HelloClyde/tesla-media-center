"""Read candidate node records in the two observed legacy samples, offline.

Coordinates use an inferred 230400 scale. Length units and route semantics
are unconfirmed. This is not a navigation decoder or complete polyline.
"""

import argparse
import json
from pathlib import Path
import struct

from inspect_envelope import inspect as envelope
from inspect_route_prefix import inspect as prefix


def inspect_reference_run(payload: bytes, offset: int, count: int, node_count: int) -> list:
    """Read an explicitly located candidate run; does not discover its header."""
    if offset < 0 or count < 0 or offset + count * 6 > len(payload):
        raise ValueError("reference run outside native payload")
    references = []
    for pos in range(offset, offset + count * 6, 6):
        flags = int.from_bytes(payload[pos:pos + 3], "little")
        index = int.from_bytes(payload[pos + 3:pos + 6], "little")
        if index >= node_count:
            raise ValueError("candidate reference outside node table")
        references.append(dict(payload_offset=pos, unknown_flags=flags, node_index_candidate=index))
    return references


def inspect(data: bytes) -> dict:
    summary = prefix(data)
    payload = data[10:10 + envelope(data)["extension_offset_in_payload"]]
    offset = summary["unparsed_from_payload_offset"]

    def take(size):
        nonlocal offset
        if offset + size > len(payload):
            raise ValueError("node field crosses native payload boundary")
        value = payload[offset:offset + size]
        offset += size
        return value

    count = int.from_bytes(take(2), "little")
    # Dictionary offsets are UTF-16 code units, not Python Unicode code points.
    dictionary = summary["concatenated_names"].encode("utf-16-le")
    nodes = []
    for _ in range(count):
        start = offset
        header = take(11)
        name_size = header[10]
        name_offset = int.from_bytes(take(2), "little") if name_size else 0
        if (name_offset + name_size) * 2 > len(dictionary):
            raise ValueError("node name outside dictionary")
        name = dictionary[name_offset * 2:(name_offset + name_size) * 2].decode("utf-16-le")
        x, y = struct.unpack("<II", take(8))
        lon, lat = x / 230400, y / 230400
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("candidate coordinate outside geographic bounds")
        nodes.append(dict(payload_offset=start, name=name,
                          length_value_candidate=int.from_bytes(header[:4], "little"),
                          unknown_header=header[4:10].hex(), coordinate_raw=[x, y],
                          coordinate_candidate=[lon, lat]))

    groups = []
    for records in summary["groups"]:
        expected = 0
        spans = []
        for record in records:
            first, size, flag = struct.unpack("<HBH", bytes.fromhex(record["unknown_trailer"]))
            if first != expected or size == 0:
                raise ValueError("summary spans do not form contiguous candidate group")
            spans.append(dict(first_candidate=first, count_candidate=size,
                              unknown_flag=flag, text=record["text"]))
            expected += size
        groups.append(dict(span_total_candidate=expected, spans=spans))
    return dict(status="experimental-two-sample-nodes", native_route_decoded=False,
                complete_polyline=False, coordinate_system="unverified",
                coordinate_scale_candidate=230400, length_units="unverified",
                summary_groups=groups, node_count=len(nodes), nodes=nodes,
                route_node_mapping="unresolved-do-not-split-sequentially",
                unparsed_from_payload_offset=offset,
                unparsed_native_bytes=len(payload) - offset)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    parser.add_argument("--reference-run", action="append", default=[], metavar="OFFSET:COUNT",
                        help="explicit candidate payload offset/count (decimal or 0x hex); repeatable")
    args = parser.parse_args()
    try:
        data = args.response.read_bytes()
        result = inspect(data)
        payload = data[10:10 + envelope(data)["extension_offset_in_payload"]]
        runs = []
        for spec in args.reference_run:
            start, count = (int(part, 0) for part in spec.split(":"))
            runs.append(inspect_reference_run(payload, start, count, result["node_count"]))
        result["manually_located_candidate_reference_runs"] = runs
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Cannot inspect nodes: {exc}\n")
