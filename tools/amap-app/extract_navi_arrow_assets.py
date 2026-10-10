"""Extract the APK navigation-header arrows selected by TripNaviManeuverUtil.

Inputs are the local APK, SPX filename index and decoded CarImageUtil module.
The image bytes are copied unchanged; no redraw or recolouring is performed.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

from extract_spx_file import extract
from inspect_oajx import inspect


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.local-data/amap-app'
OUTPUT = ROOT / 'web/public/amap/navigation-arrows'
MANIFEST = ROOT / 'web/src/components/navigationArrowAssets.json'


def main():
    util = (SOURCE / 'ajx-drive-js/amap_bundle_drive_ajx_modules_amap_bundle_lib_drivecommon_src_util_CarImageUtil.js').read_text(encoding='utf-8')
    section = util.split('"DRIVE_ARROW_ICON"', 1)[1].split('"COMMON_AJX_ICON"', 1)[0]
    resources = re.findall(r"NAVI_ARROW_SOU_(\d+): _resolveLib\('([^']+)'", section)
    if not resources:
        raise ValueError('navigation arrow table missing')
    index = json.loads((SOURCE / 'spx-file-index.json').read_text(encoding='utf-8'))
    catalog = {file['name']: (bundle['bundle_index'], file['raw_fields'])
               for bundle in index for file in bundle['files']}
    with zipfile.ZipFile(SOURCE / 'amap-release.apk') as archive:
        data = archive.read('assets/ajx.bundle/bundles.oajx')
    bundles = inspect(data)['entries']
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest, provenance = {}, []
    for icon, path in resources:
        source = 'amap_bundle_drive/ajx_modules/' + path.replace('.webp', '@3x.webp')
        if source not in catalog:
            raise ValueError(f'navigation arrow resource missing: {source}')
        payload = extract(data, bundles, *catalog[source])
        if payload[:4] != b'RIFF' or payload[8:12] != b'WEBP' or len(payload) > 65536:
            raise ValueError(f'invalid WebP: {source}')
        filename = f'action-{icon}.webp'
        (OUTPUT / filename).write_bytes(payload)
        manifest[icon] = '/amap/navigation-arrows/' + filename
        provenance.append({'icon': int(icon), 'source': source, 'bytes': len(payload),
                           'sha256': hashlib.sha256(payload).hexdigest()})
    MANIFEST.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
    (OUTPUT / 'source.json').write_bytes((json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode())
    print(f'Extracted {len(manifest)} original navigation arrows, {sum(item["bytes"] for item in provenance)} bytes')


if __name__ == '__main__':
    main()
