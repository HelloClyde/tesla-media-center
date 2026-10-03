"""Decode the App's original V4 junction picture response.

The response carries a JPEG road scene and a palette PNG route arrow. The
PNG uses palette index zero (magenta) as a color key; add the corresponding
PNG transparency chunk without recompressing or repainting the App pixels.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from route_v51 import fields


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_RESPONSE = 4 * 1024 * 1024


@dataclass(frozen=True)
class CrossPicture:
    navigation_id: bytes
    road_jpeg: bytes
    arrow_png: bytes
    width: int
    height: int


def _png_chunks(data: bytes):
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("cross arrow is not PNG")
    offset = len(PNG_SIGNATURE)
    while offset + 12 <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        if size > MAX_RESPONSE or offset + 12 + size > len(data):
            raise ValueError("truncated PNG chunk")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        crc = struct.unpack_from(">I", data, offset + 8 + size)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError("bad PNG chunk CRC")
        yield kind, payload, offset + 12 + size
        offset += 12 + size
        if kind == b"IEND":
            if offset != len(data):
                raise ValueError("trailing PNG data")
            return
    raise ValueError("PNG has no end chunk")


def transparent_arrow_png(data: bytes) -> bytes:
    """Make only palette index 0 transparent (the App's magenta color key)."""
    chunks = list(_png_chunks(data))
    if not chunks or chunks[0][0] != b"IHDR":
        raise ValueError("PNG has no IHDR")
    header = chunks[0][1]
    if len(header) != 13 or header[8] != 8 or header[9] != 3:
        raise ValueError("unsupported junction arrow PNG")
    palette = next(((payload, end) for kind, payload, end in chunks if kind == b"PLTE"), None)
    if palette is None or len(palette[0]) % 3 or palette[0][:3] != b"\xff\x00\xff":
        raise ValueError("missing magenta color key")
    if any(kind == b"tRNS" for kind, _, _ in chunks):
        return data
    count = len(palette[0]) // 3
    if not 1 <= count <= 256:
        raise ValueError("invalid PNG palette")
    alpha = b"\x00" + b"\xff" * (count - 1)
    chunk = struct.pack(">I", len(alpha)) + b"tRNS" + alpha
    chunk += struct.pack(">I", zlib.crc32(b"tRNS" + alpha) & 0xFFFFFFFF)
    return data[:palette[1]] + chunk + data[palette[1]:]


def decode_cross_picture(raw: bytes, *, expected_navigation_id: str | None = None) -> CrossPicture:
    if not 0 < len(raw) <= MAX_RESPONSE:
        raise ValueError("invalid cross response size")
    frame = fields(raw)
    navi_ids = frame.get(2, [])
    if len(navi_ids) != 1 or not isinstance(navi_ids[0], bytes) or len(navi_ids[0]) != 32:
        raise ValueError("cross response navigation ID missing")
    navi_id = navi_ids[0]
    if expected_navigation_id is not None and navi_id != expected_navigation_id.encode("ascii"):
        raise ValueError("cross response belongs to another route")
    if frame.get(6) != [0]:
        raise ValueError("cross response status is not ready")
    images = frame.get(5, [])
    jpeg = [value for value in images if isinstance(value, bytes)
            and value.startswith(b"\xff\xd8\xff") and value.endswith(b"\xff\xd9")]
    png = [value for value in images if isinstance(value, bytes) and value.startswith(PNG_SIGNATURE)]
    if len(jpeg) != 1 or len(png) != 1:
        raise ValueError("cross response image layers are incomplete")
    arrow = transparent_arrow_png(png[0])
    width, height = struct.unpack_from(">II", arrow, 16)
    if not 0 < width <= 4096 or not 0 < height <= 4096:
        raise ValueError("invalid cross image dimensions")
    return CrossPicture(navi_id, jpeg[0], arrow, width, height)
