"""Offline inspection of the legacy route response envelope; no network access."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys


def inspect(data: bytes) -> dict:
    """Strict research parser, not a replacement for the App's native decoder."""
    if len(data) < 10:
        raise ValueError("response needs a 10-byte envelope header")
    marker, offset = struct.unpack_from("<HQ", data)
    if marker != 200:
        raise ValueError(f"unsupported body marker {marker} (not HTTP status)")
    payload = data[10:]
    # App narrows this field to a signed Java int. Reject wrapped values.
    if offset > 0x7FFFFFFF or offset > len(payload):
        raise ValueError("extension offset outside payload or signed-int range")
    result = {
        "format": "legacy-route-envelope-candidate",
        "sha256": hashlib.sha256(data).hexdigest(),
        "body_marker": marker,
        "payload_bytes": len(payload),
        "extension_offset_in_payload": offset,
        "extension_marker": None,
        "taxi_cost_values": None,
        "native_route_decoded": False,
    }
    tail = payload[offset:]
    if not tail:
        result["extension_state"] = "absent-unverified"
        return result
    if len(tail) < 2:
        raise ValueError("truncated extension marker")
    result["extension_marker"] = struct.unpack_from("<H", tail)[0]
    if result["extension_marker"] != 100:
        result["extension_state"] = "unknown"
        return result
    if len(tail) < 10:
        raise ValueError("truncated taxi extension header")
    size = struct.unpack_from("<Q", tail, 2)[0]
    if size > 0x7FFFFFFF or size > len(tail) - 10 or size % 2:
        raise ValueError("invalid UTF-16LE byte length")
    try:
        text = tail[10:10 + size].decode("utf-16-le", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid UTF-16LE text") from exc
    # Strictly reject malformed tokens instead of mirroring Java's trailing split.
    values = []
    if text:
        for token in text.split(","):
            if not re.fullmatch(r"[+-]?[0-9]{1,10}", token):
                raise ValueError("invalid taxi cost integer")
            value = int(token)
            if not -(2**31) <= value < 2**31:
                raise ValueError("taxi cost outside signed-int range")
            values.append(value)
    result.update(extension_state="taxi", taxi_cost_values=values,
                  unparsed_trailing_bytes=len(tail) - 10 - size)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path, help="saved raw response body")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.response.read_bytes()), indent=2))
    except (OSError, ValueError) as exc:
        print(f"Cannot inspect response: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
