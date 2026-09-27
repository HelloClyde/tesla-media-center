"""Offline LNDS lane-tile request encoder for the pinned App native library.

This is NOT a working lane downloader. Tile IDs must be LNDS IDs, not BMD
tile_id() values. The host and version-discovery chain remain unverified.
No requests, signing, credentials, or guessed versions are generated here.

Evidence (libamapr 17.00.0.2005):
167d8f4 builds a request from tile_id_list, tile_id_versions and hd_version;
167db1c encodes descriptor 1b9d450, nested descriptor 4e4630.
167dd04 selects qc/hd/lnds/tile/data/?is_bin=1.
"""
import argparse
import json
from pathlib import Path

ENDPOINT = 'qc/hd/lnds/tile/data/?is_bin=1'
CONTENT_TYPE = 'application/x-protobuf'
MAX_TILES = 64  # TMC diagnostic limit, not an inferred App limit.


def _varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _string(value, label):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError(f'{label} must be a nonempty string without NUL')
    raw = value.encode('utf-8')
    if len(raw) > 1024:
        raise ValueError(f'{label} too long')
    return raw


def _bytes_field(number, value):
    return _varint(number << 3 | 2) + _varint(len(value)) + value


def encode_lane_request(tile_ids, tile_versions, hd_version):
    """Preserve ordered ID/version pairs; never silently truncate zip()."""
    if not isinstance(tile_ids, (list, tuple)) or not isinstance(tile_versions, (list, tuple)):
        raise ValueError('tile lists required')
    if not 1 <= len(tile_ids) <= MAX_TILES or len(tile_ids) != len(tile_versions):
        raise ValueError('equal nonempty tile ID/version lists required')
    version = _string(hd_version, 'hd_version')
    parts, seen = [], set()
    for tile_id, tile_version in zip(tile_ids, tile_versions):
        if type(tile_id) is not int or not 0 <= tile_id <= 0xffffffff:
            raise ValueError('LNDS tile ID must be uint32; BMD tile IDs are not accepted')
        if tile_id in seen:
            raise ValueError('duplicate LNDS tile ID')
        seen.add(tile_id)
        entry = b'\x08' + _varint(tile_id) + _bytes_field(2, _string(tile_version, 'tile version'))
        parts.append(_bytes_field(1, entry))
    return b''.join(parts) + _bytes_field(2, version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path, help='JSON: tile_id_list, tile_id_versions, hd_version')
    parser.add_argument('output', type=Path, help='offline protobuf request body')
    args = parser.parse_args()
    if args.manifest.stat().st_size > 128 * 1024:
        parser.error('manifest size limit')
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    body = encode_lane_request(data['tile_id_list'], data['tile_id_versions'], data['hd_version'])
    args.output.write_bytes(body)
    print(json.dumps({'bytes': len(body), 'endpointPath': ENDPOINT, 'contentType': CONTENT_TYPE,
                      'networkRequestSent': False, 'liveLaneDataVerified': False}))


if __name__ == '__main__':
    main()
