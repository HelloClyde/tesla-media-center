"""Inspect the observed ion/002 container; does not decode names or JS.

Field meanings are inferred from the 17.00.0.2005 APK, not a format spec.
Usage: python tools/amap-app/inspect_oajx.py path/to/amap.apk
"""
import argparse
import json
from pathlib import Path
import struct
import zipfile


def inspect(data):
    if len(data) < 48 or data[:8] != b"ion\n002\0":
        raise ValueError("unsupported or truncated OAJX header")
    table, count, names, names_size = struct.unpack_from("<4I", data, 24)
    if table != 48 or table + count * 20 != names:
        raise ValueError("unrecognized index layout")
    if names + names_size > len(data):
        raise ValueError("name table out of bounds")
    name_cursor, payload_cursor = names, names + names_size
    entries = []
    for index in range(count):
        unknown, name_offset, name_size, offset, size = struct.unpack_from(
            "<5I", data, table + index * 20
        )
        if name_offset != name_cursor or name_offset + name_size > names + names_size:
            raise ValueError("noncontiguous or out-of-bounds name entry")
        if offset != payload_cursor or size < 8 or offset + size > len(data):
            raise ValueError("noncontiguous or out-of-bounds payload entry")
        if data[offset:offset + 8] != b"spx\n003\0":
            raise ValueError("unsupported child bundle header")
        entries.append(dict(index=index, unknown=unknown, name_offset=name_offset,
                            name_size=name_size, offset=offset, size=size))
        name_cursor += name_size
        payload_cursor += size
    if name_cursor != names + names_size or payload_cursor != len(data):
        raise ValueError("unaccounted container bytes")
    return dict(format="ion/002", child_format="spx/003", size=len(data),
                count=count, names_decoded=False, entries=entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if zipfile.is_zipfile(args.path):
        with zipfile.ZipFile(args.path) as archive:
            raw = archive.read("assets/ajx.bundle/bundles.oajx")
    else:
        raw = args.path.read_bytes()
    print(json.dumps(inspect(raw), ensure_ascii=False, indent=2))
