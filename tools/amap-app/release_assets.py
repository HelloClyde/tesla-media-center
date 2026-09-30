"""Verify the pinned APK, then stage only the files used by the server."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile

from tmc_route_helper import HASHES

RELEASE = 'amap-runtime-17.00.0.2005'
BASE = f'https://github.com/HelloClyde/tesla-media-center/releases/download/{RELEASE}'
APK_HASH = '022c844511dce2958fd37c8d0941feb72587a434701debc9b2fda3e69ec07152'
APK_ENTRIES = {
    'libamapr.so': 'lib/arm64-v8a/libamapr.so',
    'style-day.data': 'assets/map_assets/style_X_MainStd_Std_D_s_26_1788435170.data',
    'style-night.data': 'assets/map_assets/style_X_MainStd_Std_N_s_26_1788435163.data',
    'signing-certificate.rsa': 'META-INF/MINIMAP_.RSA',
}
MAX_SIZES = {'libamapr.so': 40 * 1024 * 1024, 'style-day.data': 1024 * 1024,
             'style-night.data': 1024 * 1024, 'signing-certificate.rsa': 4096}


def verify(path, expected):
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError(f'Checksum mismatch: {path.name}')


def download(name, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
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


def extract(apk, directory):
    with zipfile.ZipFile(apk) as archive:
        for name, entry in APK_ENTRIES.items():
            target = directory / name
            if target.is_file():
                try:
                    verify(target, HASHES[name])
                    continue
                except ValueError:
                    pass
            info = archive.getinfo(entry)
            if not 0 < info.file_size <= MAX_SIZES[name]:
                raise ValueError(f'Unexpected APK entry size: {entry}')
            temporary = target.with_suffix(target.suffix + '.part')
            try:
                with archive.open(info) as source, temporary.open('wb') as output:
                    total = 0
                    while chunk := source.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_SIZES[name]:
                            raise ValueError(f'APK entry exceeds size limit: {entry}')
                        output.write(chunk)
                verify(temporary, HASHES[name])
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('docker_build/amap-assets'))
    parser.add_argument('--apk', type=Path, default=Path('.local-data/amap-app/amap-release.apk'))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    if not args.verify_only:
        if not args.apk.is_file():
            download('amap-release.apk', args.apk, APK_HASH)
        verify(args.apk, APK_HASH)
        extract(args.apk, args.directory)
        signer = args.directory / 'libserverkey.so'
        if not signer.is_file():
            download('libserverkey.so', signer, HASHES['libserverkey.so'])
        # Earlier builds staged the full APK here. The Dockerfile also excludes it.
        legacy = args.directory / 'amap-release.apk'
        if legacy.is_file() and legacy.resolve() != args.apk.resolve():
            legacy.unlink()
    for name, expected in HASHES.items():
        verify(args.directory / name, expected)
        print(f'Verified {name}')


if __name__ == '__main__':
    main()
