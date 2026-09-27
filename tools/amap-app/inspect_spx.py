"""Offline SPX filename index decoder for the observed Amap 17.00 APK.
Does not decode file contents or issue network requests.
"""
import argparse
import json
from pathlib import Path
import struct
import zipfile
from inspect_oajx import inspect


def elf_hash(data):
    value = 0
    for byte in data:
        value = (byte + (value << 4)) & 0xffffffff
        high = value & 0xf0000000
        value = (value ^ (high >> 24)) & ~high
    return value & 0x7fffffff


def rc4(key, data):
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    result = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        result.append(byte ^ state[(state[i] + state[j]) % 256])
    return bytes(result)


def lz4_block(data, expected):
    if not 0 <= expected <= 10 * 1024 * 1024:
        raise ValueError('unreasonable name table size')
    output = bytearray()
    pos = 0

    def length(base):
        nonlocal pos
        if base == 15:
            while True:
                if pos >= len(data):
                    raise ValueError('truncated length')
                extra = data[pos]
                pos += 1
                base += extra
                if extra != 255:
                    break
        return base

    while pos < len(data):
        token = data[pos]
        pos += 1
        size = length(token >> 4)
        if pos + size > len(data) or len(output) + size > expected:
            raise ValueError('invalid literal length')
        output.extend(data[pos:pos + size])
        pos += size
        if pos == len(data):
            break
        if pos + 2 > len(data):
            raise ValueError('truncated match offset')
        offset = int.from_bytes(data[pos:pos + 2], 'little')
        pos += 2
        size = length(token & 15) + 4
        if not 0 < offset <= len(output) or len(output) + size > expected:
            raise ValueError('invalid match')
        for _ in range(size):
            output.append(output[-offset])
    if len(output) != expected:
        raise ValueError('name table size mismatch')
    return bytes(output)


def inspect_spx(data):
    if len(data) < 480 or data[:8] != b'spx\n003\0':
        raise ValueError('unsupported SPX header')
    table, names, names_size, field3, field4, count = struct.unpack_from('<6I', data, 0x1c0)
    if table != 480 or table + count * 36 != names or names_size < 4 or names + names_size > len(data):
        raise ValueError('invalid SPX index bounds')
    key = struct.pack('<4I', elf_hash(data[:8]), elf_hash(data[8:29]),
                      (field3 + field4) & 0xffffffff, (names + count) & 0xffffffff)
    expected = struct.unpack_from('<I', data, names)[0]
    decoded = lz4_block(rc4(key, data[names + 4:names + names_size]), expected)
    entries = []
    cursor = 0
    for i in range(count):
        fields = struct.unpack_from('<9I', data, table + i * 36)
        size, offset = fields[5:7]
        if offset != cursor or offset + size > len(decoded):
            raise ValueError('invalid filename range')
        name = decoded[offset:offset + size].decode('utf-8')
        entries.append(dict(name=name, raw_fields=list(fields)))
        cursor += size
    if cursor != len(decoded):
        raise ValueError('unaccounted filename bytes')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.apk) as archive:
        data = archive.read('assets/ajx.bundle/bundles.oajx')
    result = []
    for entry in inspect(data)['entries']:
        start = entry['offset']
        files = inspect_spx(data[start:start + entry['size']])
        result.append(dict(bundle_index=entry['index'], files=files))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('bundles:', len(result), 'files:', sum(len(b['files']) for b in result))
    for bundle in result:
        for file in bundle['files']:
            if 'plan_page/PlanPage.page.js' in file['name'] or 'plan_page_preload' in file['name']:
                print(bundle['bundle_index'], file['name'])
