"""Bounded App BMD transport decoder. Does not claim to decode map geometry.

Verified against libamapr.so: tile ID 0x160cfbc/0x160d02c,
base payload decompression 0x1669594. Unknown compression fails closed.
"""
import hashlib
import math
import struct
import zlib
from route_v51 import fields, one, varint

LIMIT = 16 * 1024 * 1024


def geographic_grid(longitude, latitude, level):
    """Experimental geographic grid; Beijing level 14 verified with road names.

    This is not the Web Mercator/XYZ grid used by the current Leaflet layer.
    Broader region and zoom validation is still needed before UI integration.
    """
    if type(level) is not int or not 0 <= level <= 23:
        raise ValueError("invalid level")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (longitude, latitude)):
        raise ValueError("invalid coordinate")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("invalid coordinate")
    size = 1 << level
    return level, min(size - 1, int((longitude + 180) / 360 * size)), min(size - 1, int((90 - latitude) / 180 * size))


def directory(data):
    """Parse the verified BMD 8000 header and bounded section directory.

    libamapr 0x1abd1a8: u32 checksum, u8 flags, u32 format, u16 count;
    entries contain u16 kind followed by three unsigned varints.
    Section offsets are relative to the end of the complete directory.
    The third varint is preserved as metadata, not assigned a guessed meaning.
    """
    if not 11 <= len(data) <= LIMIT:
        raise ValueError("invalid BMD size")
    checksum, flags, version, count = struct.unpack_from('<IBIH', data)
    if checksum != zlib.crc32(data[4:]):
        raise ValueError("BMD checksum mismatch")
    if flags >= 16 or version != 8000 or not 1 <= count <= 256:
        raise ValueError("unsupported BMD header")
    offset, entries, kinds = 11, [], set()
    for _ in range(count):
        if offset + 2 > len(data):
            raise ValueError("truncated BMD directory")
        kind = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        start, offset = varint(data, offset)
        size, offset = varint(data, offset)
        metadata, offset = varint(data, offset)
        if kind in kinds:
            raise ValueError("duplicate BMD section")
        kinds.add(kind)
        entries.append(dict(kind=kind, offset=start, size=size, metadata=metadata))
    end = 0
    for entry in sorted(entries, key=lambda entry: entry['offset']):
        start, size = entry['offset'], entry['size']
        if start < end or start + size > len(data) - offset:
            raise ValueError("invalid BMD section range")
        end = start + size
    return dict(format=version, flags=flags, bodyOffset=offset, sections=entries)


def tile_id(level, x, y):
    # This encodes an App grid coordinate, not an assumed Web Mercator tile.
    if any(type(v) is not int for v in (level, x, y)):
        raise ValueError("integer grid required")
    if not 0 <= level <= 23 or not 0 <= x < 1 << level or not 0 <= y < 1 << 24:
        raise ValueError("invalid grid")
    return level << 48 | y << 24 | x


def tile_grid(value):
    if type(value) is not int or not 0 <= value < 1 << 53:
        raise ValueError("invalid tile ID")
    level = value >> 48
    x = value & 0xffffff
    if x & 0x800000:
        x -= 1 << 24
    return level, x % (1 << level), (value >> 24) & 0xffffff


def catalog(raw):
    message = fields(raw)
    versions = {}
    for entry in message.get(1, []):
        entry = fields(entry)
        kind, version = one(entry, 1, 0), one(entry, 2)
        if type(kind) is not int or type(version) is not int or kind in versions:
            raise ValueError("invalid version catalog")
        versions[kind] = version
    if not versions:
        raise ValueError("empty version catalog")
    return versions


def lz4_block(data, size):
    """Decode an App raw LZ4 block with strict input/output bounds."""
    if not 0 <= size <= LIMIT or len(data) > LIMIT:
        raise ValueError('LZ4 size limit')
    output, offset = bytearray(), 0
    def length(value):
        nonlocal offset
        if value == 15:
            while True:
                if offset >= len(data):
                    raise ValueError('truncated LZ4 length')
                extra = data[offset]; offset += 1; value += extra
                if value > size:
                    raise ValueError('LZ4 output limit')
                if extra != 255:
                    break
        return value
    while offset < len(data):
        token = data[offset]; offset += 1
        count = length(token >> 4)
        if offset + count > len(data) or len(output) + count > size:
            raise ValueError('invalid LZ4 literals')
        output.extend(data[offset:offset + count]); offset += count
        if offset == len(data):
            break
        if offset + 2 > len(data):
            raise ValueError('truncated LZ4 offset')
        distance = int.from_bytes(data[offset:offset + 2], 'little'); offset += 2
        count = length(token & 15) + 4
        if not 0 < distance <= len(output) or len(output) + count > size:
            raise ValueError('invalid LZ4 match')
        # Repeat in bounded chunks; supports overlapping back references.
        while count:
            take = min(count, distance)
            output.extend(output[len(output) - distance:len(output) - distance + take])
            count -= take
    if len(output) != size:
        raise ValueError('LZ4 size mismatch')
    return bytes(output)


def unpack(raw, expected_id, expected_type):
    message = fields(raw)
    if one(message, 1) != expected_id or one(message, 2, 0) != expected_type:
        raise ValueError("tile identity mismatch")
    payload = one(message, 5, b"")
    if not isinstance(payload, bytes):
        raise ValueError("invalid payload")
    if not payload:
        return b""
    block = fields(payload)
    data, size = one(block, 1), one(block, 2)
    if not isinstance(data, bytes) or type(size) is not int or not 0 <= size <= LIMIT:
        raise ValueError("invalid payload size")
    compressed, codec = one(block, 3, 0), one(block, 4, 0)
    if compressed == 0:
        result = data
    elif compressed == 1 and codec == 0:
        result = lz4_block(data, size)
    elif compressed == 1 and codec == 1:
        import zstandard
        try:
            # A streaming read imposes a bound even when the frame advertises
            # its own size (max_output_size alone does not cover that case).
            with zstandard.ZstdDecompressor().stream_reader(data) as stream:
                result = stream.read(size + 1)
        except zstandard.ZstdError:
            raise ValueError("invalid zstandard payload") from None
    else:
        raise ValueError("unsupported compression")
    if len(result) != size:
        raise ValueError("payload size mismatch")
    return result


def summary(raw):
    message = fields(raw)
    identity, kind = one(message, 1), one(message, 2, 0)
    result = unpack(raw, identity, kind)
    result_summary = {"tileId": identity, "grid": tile_grid(identity), "tileType": kind,
            "version": one(message, 4), "decodedBytes": len(result),
            "sha256": hashlib.sha256(result).hexdigest(),
            "geometryDecoded": False}
    if len(result) >= 11:
        result_summary['directory'] = directory(result)
    return result_summary


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    if args.response.stat().st_size > LIMIT:
        parser.error("response exceeds limit")
    print(json.dumps(summary(args.response.read_bytes()), indent=2))
