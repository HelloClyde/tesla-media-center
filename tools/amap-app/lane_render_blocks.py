"""Decode the rendering LNDS type-22 block envelope, not lane geometry.

libamapr 16693d0 uses descriptor 1b9c460, nested descriptor 4e4448.
166a240 passes bytes to the data provider; 1669304 retains field 1 as u16.
The two verified live blocks have a little-endian CRC32 of bytes [4:].
Their remaining binary contents are deliberately preserved without guessing.
"""
import hashlib
import struct
import zlib

from lane_response import _message


def decode_render_blocks(payload, expected_id):
    if type(expected_id) is not int or not 0 <= expected_id < 2**64:
        raise ValueError('invalid expected tile ID')
    budget = [4096]
    root = _message(payload, {1: ('u64', False), 2: ('bytes', True)}, budget)
    if root.get(1) != [expected_id]:
        raise ValueError('LNDS block tile identity mismatch')
    entries = root.get(2, [])
    if len(entries) > 64:
        raise ValueError('LNDS block count limit')
    blocks, seen = [], set()
    for raw in entries:
        record = _message(raw, {1: ('u32', False), 2: ('u32', False),
                                3: ('bytes', False)}, budget)
        identifier = record.get(1, [0])[0]
        if identifier > 65535 or identifier in seen:
            raise ValueError('unsupported or duplicate LNDS block ID')
        seen.add(identifier)
        data = record.get(3, [b''])[0]
        if len(data) < 4:
            raise ValueError('missing LNDS block data')
        checksum = struct.unpack_from('<I', data)[0]
        if checksum != zlib.crc32(data[4:]):
            raise ValueError('LNDS block checksum mismatch')
        blocks.append({'id': identifier, 'field2': record.get(2, [None])[0],
                       'data': data, 'crc32': f'{checksum:08x}',
                       'sha256': hashlib.sha256(data).hexdigest()})
    return {'tileId': str(expected_id), 'blocks': blocks, 'geometryDecoded': False}
