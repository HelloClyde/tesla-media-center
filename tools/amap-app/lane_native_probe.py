"""Offline CLI for the same bounded native decoder used by the lane helper."""
import argparse
import hashlib
import json
from pathlib import Path
from lane_native_decoder import decode

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lib', required=True)
    p.add_argument('--block', required=True)
    p.add_argument('--tile-id', required=True, type=int)
    p.add_argument('--block-id', required=True, type=int)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = decode(Path(a.block).read_bytes(), Path(a.lib).read_bytes(), a.tile_id, a.block_id)
    Path(a.output).write_bytes(result)
    print(json.dumps({'flatbufferBytes': len(result), 'sha256': hashlib.sha256(result).hexdigest()}))
