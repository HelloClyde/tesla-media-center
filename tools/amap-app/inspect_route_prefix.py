"""Experimental prefix reader for two observed legacy route samples, not a decoder.

Offsets and group semantics remain hypotheses. Reject other header profiles;
never use this output to navigate or report validated route counts/distances.
"""

import argparse
import json
from pathlib import Path
import struct

from inspect_envelope import inspect as inspect_envelope


def inspect(data: bytes) -> dict:
    envelope = inspect_envelope(data)
    boundary = envelope["extension_offset_in_payload"]
    payload = data[10:10 + boundary]
    if len(payload) < 88:
        raise ValueError("truncated observed prefix")
    if int.from_bytes(payload[:3], "little") != boundary:
        raise ValueError("unrecognized 24-bit length field")
    if payload[3] != 5 or payload[9:13] != b"\x03\x0aGj":
        raise ValueError("unrecognized sample header profile")

    def take(offset, size):
        if offset < 0 or size < 0 or offset + size > len(payload):
            raise ValueError("prefix field crosses native payload boundary")
        return payload[offset:offset + size]

    groups = []
    offset = 87
    for _ in range(payload[52]):
        count = take(offset, 1)[0]
        offset += 1
        records = []
        for _ in range(count):
            record_offset = offset
            kind, chars = take(offset, 2)
            offset += 2
            text = take(offset, chars * 2).decode("utf-16-le")
            offset += chars * 2
            trailer = take(offset, 5).hex()
            offset += 5
            records.append(dict(payload_offset=record_offset, unknown_kind=kind,
                                text=text, unknown_trailer=trailer))
        groups.append(records)
    chars = struct.unpack("<H", take(offset, 2))[0]
    offset += 2
    dictionary = take(offset, chars * 2).decode("utf-16-le")
    offset += chars * 2
    return dict(status="experimental-two-sample-prefix", native_route_decoded=False,
                group_count_candidate=len(groups), groups=groups,
                concatenated_names=dictionary, unparsed_from_payload_offset=offset,
                unparsed_native_bytes=len(payload) - offset)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.response.read_bytes()), ensure_ascii=True, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot inspect prefix: {exc}\n")
