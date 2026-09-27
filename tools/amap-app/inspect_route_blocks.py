"""Experimental length-delimited detail blocks; partial geometry only.

All framing may be consumed while block contents remain uninterpreted.
No navigation, coordinate-system or distance/time-unit guarantees.
"""
import argparse
import json
from pathlib import Path
import struct

from inspect_envelope import inspect as envelope
from inspect_route_records import inspect as records


class UnsupportedGeometry(ValueError):
    pass


def simple_geometry(block: bytes, origin: list) -> dict:
    offset = 6

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(block):
            raise UnsupportedGeometry("field crosses detail block boundary")
        value = block[offset:offset + size]
        offset += size
        return value

    def u16():
        return int.from_bytes(take(2), "little")

    if len(block) < 6 or block[5] not in (5, 7):
        raise UnsupportedGeometry("unimplemented detail flags")
    unknown_code = take(1).hex()
    take(u16())  # Opaque length-delimited metadata; not claimed decoded.
    optional_name = None
    if block[5] & 2:
        optional_name = take(u16() * 2).decode("utf-16-le")
    links = []
    x, y = origin
    points = [[x, y]]
    for _ in range(u16()):
        attribute_bytes = take(7).hex()
        link_count = take(1)[0]
        if not link_count:
            raise UnsupportedGeometry("empty attribute group")
        for _ in range(link_count):
            link_id, length = struct.unpack("<IH", take(6))
            flags = take(1)[0]
            if flags & ~0xf3:
                raise UnsupportedGeometry(f"unimplemented link flags 0x{flags:x}")
            extension = take(1)[0] if flags & 128 else 0
            if extension & ~0x15:
                raise UnsupportedGeometry(f"unimplemented extension 0x{extension:x}")
            take(4 * bool(flags & 1) + 4 * bool(flags & 2))
            meta = take(1)[0]
            descriptor = take(1)[0]
            if descriptor & ~0xc1: raise UnsupportedGeometry(f"unknown descriptor {descriptor:x}")
            optional = take(bool(descriptor & 64) + 8 * bool(descriptor & 128)).hex()
            unknown_pair = take(1).hex()
            if flags & 16:
                take((take(1)[0] if extension & 1 else 1) * 7)
            mask = u16()
            if mask not in (7, 263):
                raise UnsupportedGeometry(f"unimplemented field mask 0x{mask:x}")
            scalar = take(1)[0]
            scalar16 = u16()
            packed = u16()
            mode, count = packed >> 14, packed & 0x3FFF
            if mode not in (0, 1) or not count:
                raise UnsupportedGeometry("unimplemented coordinate mode/count")
            for _ in range(count):
                dx, dy = struct.unpack("<hh" if mode != 1 else "<bb", take(4 if mode != 1 else 2))
                x += dx
                y += dy
                points.append([x, y])
            links.append(dict(id_candidate=link_id, length_value_candidate=length,
                              unknown_attributes=attribute_bytes, unknown_flags=flags,
                              unknown_optional=optional, unknown_pair=unknown_pair,
                              unknown_extension=extension, unknown_metadata=meta,
                              unknown_descriptor=descriptor,
                              unknown_mask=mask, unknown_scalar8=scalar,
                              unknown_scalar16=scalar16, coordinate_mode=mode,
                              coordinate_count=count))
    if offset != len(block):
        raise UnsupportedGeometry("uninterpreted bytes after candidate geometry")
    return dict(status="candidate-relative-points", optional_name=optional_name,
                unknown_code=unknown_code, links=links, points_raw=points,
                length_value_sum_candidate=sum(link["length_value_candidate"] for link in links))


def read_blocks(payload, offset, candidate_records):
    output = []
    for group_index, record in enumerate(candidate_records):
        for local_index, reference in enumerate(record["references"]):
            if offset < 0 or offset + 6 > len(payload):
                raise ValueError("truncated detail block header")
            size, index, group, flags = struct.unpack_from("<HHBB", payload, offset)
            if size < 6 or offset + size > len(payload):
                raise ValueError("invalid detail block size")
            if (index, group) != (local_index, group_index):
                raise ValueError("detail group/index disagrees with reference order")
            output.append(dict(payload_offset=offset, size=size, group=group, index=index,
                               unknown_flags=flags,
                               node_index_candidate=reference["node_index_candidate"]))
            offset += size
    if offset != len(payload):
        raise ValueError("detail blocks do not consume native payload boundary")
    return output


def inspect(data):
    result = records(data)
    payload = data[10:10 + envelope(data)["extension_offset_in_payload"]]
    blocks = read_blocks(payload, result["unparsed_from_payload_offset"], result["candidate_records"])
    decoded = 0
    for block in blocks:
        node = result["nodes"][block["node_index_candidate"]]
        start = block["payload_offset"]
        raw = payload[start:start + block["size"]]
        try:
            geometry = simple_geometry(raw, node["coordinate_raw"])
            if geometry["length_value_sum_candidate"] != node["length_value_candidate"]:
                raise UnsupportedGeometry("length sum differs from referenced node")
            refs = result["candidate_records"][block["group"]]["references"]
            if block["index"] + 1 < len(refs):
                next_node = result["nodes"][refs[block["index"] + 1]["node_index_candidate"]]
                match = geometry["points_raw"][-1] == next_node["coordinate_raw"]
                geometry["next_origin_matches"] = match
                if not match:
                    raise UnsupportedGeometry("endpoint differs from next referenced node")
            block["geometry_candidate"] = geometry
            decoded += 1
        except (UnsupportedGeometry, UnicodeDecodeError) as exc:
            block["geometry_candidate"] = dict(status="unsupported", reason=str(exc))
    result.update(status="experimental-block-framing", detail_blocks=blocks,
                  framing_consumed_all=True, native_route_decoded=False, complete_polyline=False,
                  candidate_geometry_block_count=decoded,
                  uninterpreted_geometry_block_count=len(blocks) - decoded,
                  unparsed_from_payload_offset=len(payload), unparsed_native_bytes=0,
                  framing_note="zero unframed bytes does not mean block contents decoded")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.response.read_bytes()), ensure_ascii=True, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot inspect blocks: {exc}\n")
