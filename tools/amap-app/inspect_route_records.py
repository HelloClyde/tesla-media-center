"""Experimental automatic reference-record reader validated on three samples.

This does not decode route geometry, travel time, or confirm distance units.
Unknown fields remain opaque; unobserved profiles fail closed.
"""
import argparse
import json
from pathlib import Path

from inspect_envelope import inspect as envelope
from inspect_route_nodes import inspect as nodes, inspect_reference_run


def read_records(payload: bytes, offset: int, group_count: int, node_count: int):
    def take(size):
        nonlocal offset
        if offset < 0 or offset + size > len(payload):
            raise ValueError("route record crosses native payload boundary")
        data = payload[offset:offset + size]
        offset += size
        return data

    if group_count < 1 or group_count > 255:
        raise ValueError("unsupported candidate group count")
    records = []
    for _ in range(group_count):
        start = offset
        header = take(10)
        if header[0] not in (0, 128):
            raise ValueError("unknown record header profile")
        count = int.from_bytes(header[1:3], "little")
        if count == 0:
            raise ValueError("empty candidate reference run")
        labels = []
        for _ in range(header[9]):
            kind, units = take(2)
            text = take(units * 2).decode("utf-16-le")
            if take(1) != b"\0":
                raise ValueError("unknown label terminator")
            labels.append(dict(unknown_kind=kind, text=text))
        unknown_before_refs = take(3)
        if unknown_before_refs != b"\x02\0\0":
            raise ValueError("unknown reference prefix profile")
        refs = inspect_reference_run(payload, offset, count, node_count)
        take(count * 6)
        trailer = take(12)
        if trailer[:3] != b"\x01\0\x0a" or trailer[4:] != b"\0\0\x04\0\0\0\0\xfd":
            raise ValueError("unknown record trailer profile")
        records.append(dict(payload_offset=start, unknown_header=header.hex(),
                            labels=labels, reference_count_candidate=count,
                            references=refs, unknown_trailer=trailer.hex(),
                            next_payload_offset=offset))
    return records, offset


def inspect(data: bytes) -> dict:
    result = nodes(data)
    payload = data[10:10 + envelope(data)["extension_offset_in_payload"]]
    records, end = read_records(payload, result["unparsed_from_payload_offset"],
                                len(result["summary_groups"]), result["node_count"])
    for record in records:
        record["length_value_sum_candidate"] = sum(
            result["nodes"][ref["node_index_candidate"]]["length_value_candidate"]
            for ref in record["references"])
    result.update(status="experimental-three-sample-records", candidate_records=records,
                  route_node_mapping="candidate-record-references-unverified-semantics",
                  unparsed_from_payload_offset=end, unparsed_native_bytes=len(payload) - end)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.response.read_bytes()), ensure_ascii=True, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot inspect records: {exc}\n")
