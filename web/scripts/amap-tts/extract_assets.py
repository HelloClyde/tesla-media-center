"""Extract the pinned APK's default offline voice for the browser build."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]
APK_SHA256 = '022c844511dce2958fd37c8d0941feb72587a434701debc9b2fda3e69ec07152'
PREFIX = 'assets/voicesqure/default_voice_ip/gaolaoshi_amap/'
FILES = ('am_encoder.mnn', 'am_decoder.mnn', 'ddspganV2_f0.mnn',
         'ddspganV2_ctrl.mnn', 'am_dict.json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk', type=Path,
                        default=ROOT / 'docker_build/amap-assets/amap-release.apk')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'web/public/tts/amap-1.0')
    args = parser.parse_args()
    with args.apk.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != APK_SHA256:
        raise ValueError(f'Unexpected AMap APK hash: {actual}')
    args.output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.apk) as archive:
        for name in FILES:
            entry = archive.getinfo(PREFIX + name)
            if not (0 < entry.file_size < 8 * 1024 * 1024):
                raise ValueError(f'Unexpected voice asset size: {name}')
            target = args.output / name
            with archive.open(entry) as source, target.open('wb') as destination:
                destination.write(source.read())
            print(f'Extracted {name}: {target.stat().st_size} bytes')


if __name__ == '__main__':
    main()
