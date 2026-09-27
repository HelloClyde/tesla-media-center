"""Fetch pinned public Release assets or verify an existing build directory."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
from tmc_route_helper import HASHES

RELEASE = 'amap-runtime-17.00.0.2005'
BASE = f'https://github.com/HelloClyde/tesla-media-center/releases/download/{RELEASE}'

def verify(path, expected):
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError(f'Checksum mismatch: {path.name}')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('docker_build/amap-assets'))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, expected in HASHES.items():
        target = args.directory / name
        if not args.verify_only:
            temporary = target.with_suffix(target.suffix + '.part')
            try:
                with urllib.request.urlopen(f'{BASE}/{name}', timeout=60) as response, temporary.open('wb') as output:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > 256 * 1024 * 1024:
                            raise ValueError('Asset exceeds size limit')
                        output.write(chunk)
                verify(temporary, expected)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        verify(target, expected)
        print(f'Verified {name}')

if __name__ == '__main__':
    main()
