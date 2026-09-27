"""Decode one exact APK resource to an explicitly chosen local output file.

Observed ion/002 + spx/003 layout only; no network or script execution.
"""
import argparse
import json
from pathlib import Path
import struct
import zipfile
from inspect_oajx import inspect
from inspect_spx import elf_hash, rc4, lz4_block


def extract(data, bundles, bundle_index, fields):
    source = bundles[bundle_index]
    offset = fields[4]
    signed = offset if offset < 0x80000000 else offset - 0x100000000
    start = source['offset'] + signed
    size, expected = fields[2:4]
    owner = next((b for b in bundles if b['offset'] <= start
                  and start + size <= b['offset'] + b['size']), None)
    if owner is None or size == 0:
        raise ValueError('content outside child bundle bounds')
    header = data[owner['offset']:owner['offset'] + 480]
    if len(header) != 480 or header[:8] != b'spx\n003\0':
        raise ValueError('unsupported content owner')
    f = struct.unpack_from('<6I', header, 0x1c0)
    if start < owner['offset'] + f[1] + f[2]:
        raise ValueError('content overlaps bundle metadata')
    key = struct.pack('<4I', elf_hash(header[:8]), elf_hash(header[8:29]),
                      (f[3] + f[4]) & 0xffffffff, (f[1] + f[5]) & 0xffffffff)
    return lz4_block(rc4(key, data[start:start + size]), expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('index', type=Path)
    parser.add_argument('resource', help='exact resource name from the filename index')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding='utf-8'))
    matches = [(b['bundle_index'], f['raw_fields']) for b in index for f in b['files']
               if f['name'] == args.resource]
    if len(matches) != 1:
        raise ValueError('resource must resolve to exactly one index entry')
    with zipfile.ZipFile(args.apk) as archive:
        data = archive.read('assets/ajx.bundle/bundles.oajx')
    result = extract(data, inspect(data)['entries'], *matches[0])
    args.output.write_bytes(result)
    print('Decoded bytes:', len(result))
