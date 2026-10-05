"""Extract the building-material images from the pinned Amap APK.

Asset-generation helper, not a server dependency. ETC2 decoding requires
``pip install Pillow texture2ddecoder==1.0.6`` in the local tool environment.
"""
import argparse
import io
from pathlib import Path
import struct
import zipfile

import zstandard

from release_assets import APK_HASH, verify


ENTRY = 'assets/map_assets/icons_5_26_1788435033.data'
IDS = (23000029, 23000030, 2100031, 23100029, 1112, 30)
ATLAS_SIZE = (1024, 512)
CELL = 256


def extract(apk: Path, output: Path):
    from PIL import Image
    import texture2ddecoder

    verify(apk, APK_HASH)
    with zipfile.ZipFile(apk) as archive:
        info = archive.getinfo(ENTRY)
        if info.file_size > 256 * 1024:
            raise ValueError('icon pack exceeds size limit')
        payload = zstandard.ZstdDecompressor().decompress(archive.read(info), max_output_size=512 * 1024)
    with zipfile.ZipFile(io.BytesIO(payload)) as icons:
        output.mkdir(parents=True, exist_ok=True)
        atlas = Image.new('RGB', ATLAS_SIZE, 'white')
        for icon_id in IDS:
            raw = icons.read(f'{icon_id}.png')
            if len(raw) > 128 * 1024:
                raise ValueError(f'oversized icon {icon_id}')
            if raw[:4] == b'PVR\x03':
                height, width = struct.unpack_from('<II', raw, 24)
                metadata_size = struct.unpack_from('<I', raw, 48)[0]
                if struct.unpack_from('<Q', raw, 8)[0] != 23 or width * height > 256 * 256:
                    raise ValueError(f'unsupported PVR icon {icon_id}')
                blocks = ((width + 3) // 4) * ((height + 3) // 4) * 16
                compressed = raw[52 + metadata_size:]
                if len(compressed) != blocks:
                    raise ValueError(f'truncated PVR icon {icon_id}')
                pixels = texture2ddecoder.decode_etc2a8(compressed, width, height)
                image = Image.frombytes('RGBA', (width, height), pixels, 'raw', 'BGRA')
            else:
                image = Image.open(io.BytesIO(raw))
                image.load()
                if image.format != 'PNG' or image.width * image.height > 256 * 256:
                    raise ValueError(f'unsupported PNG icon {icon_id}')
            target = output / f'{icon_id}.png'
            image.save(target)
            slot = IDS.index(icon_id) + 1  # slot zero is white for roofs/untextured walls
            atlas.paste(image.convert('RGB').resize((CELL, CELL), Image.Resampling.BILINEAR),
                        ((slot % 4) * CELL, (slot // 4) * CELL))
            print(f'{target}: {image.width}x{image.height}')
        atlas.save(output / 'atlas.png', optimize=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk', type=Path, default=Path('.local-data/amap-app/amap-release.apk'))
    parser.add_argument('--output', type=Path, default=Path('web/public/amap/buildings'))
    args = parser.parse_args()
    extract(args.apk, args.output)
