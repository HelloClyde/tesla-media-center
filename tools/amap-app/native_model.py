"""Bounded reader for the verified App raw_gltf model container.

This is an offline investigation tool, not a geographic landmark source.
Only the observed type-12/type-13 layout is supported; unknown variants fail.
Native references (17.00.0.2005 libamapr.so): 16d6634, 16d8004, 16d77a4.
"""
import argparse
import json
import struct
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024


def u32(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('truncated integer')
    return struct.unpack_from('<I', data, offset)[0]


def validate_glb(data):
    """Validate chunk boundaries and reject external buffer/image references."""
    if len(data) < 20 or len(data) > MAX_BYTES:
        raise ValueError('invalid GLB size')
    if data[:4] != b'glTF' or u32(data, 4) != 2 or u32(data, 8) != len(data):
        raise ValueError('invalid GLB header')
    pos, chunks = 12, []
    while pos < len(data):
        size, kind = u32(data, pos), u32(data, pos + 4)
        end = pos + 8 + size
        if size % 4 or end > len(data):
            raise ValueError('invalid GLB chunk bounds')
        chunks.append((kind, data[pos + 8:end]))
        pos = end
    if not chunks or chunks[0][0] != 0x4E4F534A:
        raise ValueError('missing GLB JSON')
    if len(chunks) != 2 or chunks[1][0] != 0x004E4942:
        raise ValueError('unsupported GLB chunks')
    try:
        doc = json.loads(chunks[0][1])
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid GLB JSON') from exc
    if not isinstance(doc, dict) or doc.get('asset', {}).get('version') != '2.0':
        raise ValueError('unsupported glTF version')
    buffers = doc.get('buffers', [])
    if len(buffers) != 1 or 'uri' in buffers[0]:
        raise ValueError('only one embedded buffer is supported')
    length = buffers[0].get('byteLength')
    if type(length) is not int or not 0 <= len(chunks[1][1]) - length <= 3:
        raise ValueError('invalid embedded buffer length')
    views = doc.get('bufferViews', [])
    for view in views:
        start, size = view.get('byteOffset', 0), view.get('byteLength')
        if (view.get('buffer', 0) != 0 or type(start) is not int or
                type(size) is not int or start < 0 or size < 0 or start + size > length):
            raise ValueError('invalid buffer view')
    for image in doc.get('images', []):
        index = image.get('bufferView')
        if 'uri' in image or type(index) is not int or not 0 <= index < len(views):
            raise ValueError('only embedded images are supported')
    return doc


def extract_models(data):
    """Return embedded GLBs without altering normals, UVs or texture bytes.

    Bounds/transform fields are deliberately not interpreted as geolocation.
    The second header word is an opaque format tag, not a verified checksum.
    """
    if len(data) < 28 or len(data) > MAX_BYTES:
        raise ValueError('invalid container size')
    if (u32(data, 0), u32(data, 4), u32(data, 8)) != (0xffffffff, 0x8f0584f6, 20):
        raise ValueError('unsupported container header')
    if u32(data, 12) != len(data) or data[16:24] != bytes(8):
        raise ValueError('invalid container length or flags')
    count, pos, models = u32(data, 24), 28, []
    if not 1 <= count <= 128:
        raise ValueError('invalid model count')
    for _ in range(count):
        start = pos
        kind, size = u32(data, pos), u32(data, pos + 4)
        if kind != 12 or size < 68 or size % 4 or pos + size > len(data):
            raise ValueError('unsupported model metadata')
        name_size = u32(data, pos + 36)
        if name_size != 8 or data[pos + 40:pos + 48] != b'raw_gltf' or size != 76:
            raise ValueError('unsupported model encoding')
        resource_size = u32(data, pos + 72)
        pos += size
        kind, size = u32(data, pos), u32(data, pos + 4)
        end = pos + size
        if kind != 13 or size < 24 or end > len(data) or end - start != resource_size:
            raise ValueError('invalid model payload bounds')
        glb_size = u32(data, pos + 8)
        if glb_size + 24 != size or data[end - 12:end] != struct.pack('<III', 11, 0, 0):
            raise ValueError('unsupported model payload trailer')
        glb = data[pos + 12:pos + 12 + glb_size]
        validate_glb(glb)
        models.append(glb)
        pos = end
    if pos != len(data):
        raise ValueError('unexpected container trailing bytes')
    return models


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.stat().st_size > MAX_BYTES:
        parser.error('container exceeds size limit')
    models = extract_models(args.source.read_bytes())
    args.output.mkdir(parents=True, exist_ok=True)
    for index, model in enumerate(models):
        target = args.output / f'model-{index}.glb'
        target.write_bytes(model)
        doc = validate_glb(model)
        print(json.dumps({'file': str(target), 'bytes': len(model),
                          'meshes': len(doc.get('meshes', [])),
                          'images': len(doc.get('images', []))}))
