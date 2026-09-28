"""Download pinned, verified browser TTS runtime/model for local and Docker builds."""
import hashlib
from pathlib import Path
import shutil
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
NAME = 'sherpa-onnx-wasm-simd-1.13.8-matcha-icefall-zh-baker'
SHA256 = 'bf17d3373493ae69695c3671b1c637e41c6937f755dd2c7ac9be07ca35f03cc4'
FILES = ['sherpa-onnx-tts.js', 'sherpa-onnx-wasm-main-tts.js',
         'sherpa-onnx-wasm-main-tts.data', 'sherpa-onnx-wasm-main-tts.wasm']

def main():
    archive = ROOT / '.local-data/tts/matcha.tar.bz2'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        url = f'https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/{NAME}.tar.bz2'
        partial = archive.with_suffix('.download')
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as target:
            shutil.copyfileobj(response, target)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('TTS archive checksum mismatch')
        partial.replace(archive)
    out = ROOT / '.local-data/tts/source'
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        for name in FILES:
            member = source.getmember(f'./{NAME}/{name}')
            if not member.isfile():
                raise RuntimeError('Unexpected asset type')
            with source.extractfile(member) as data, (out / name).open('wb') as target:
                shutil.copyfileobj(data, target)
    print('Verified and installed local Chinese TTS assets:', out)
    from quantize_assets import main as quantize
    quantize()

if __name__ == '__main__':
    main()
