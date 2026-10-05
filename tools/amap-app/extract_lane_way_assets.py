"""Extract the App's lane-arrow SVGs used by its drive lane widget.

The APK and decoded AJX files are local research inputs, not repository files.
Run from the repository root after preparing .local-data/amap-app.
"""
import json
from pathlib import Path
import re
import zipfile

from extract_spx_file import extract
from inspect_oajx import inspect


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.local-data/amap-app'
OUTPUT = ROOT / 'web/public/amap/lane'
MANIFEST = ROOT / 'web/src/views/apps/amapLaneAssets.json'


def main():
    icons = (SOURCE / 'ajx-drive-js/amap_bundle_drive_ajx_modules_amap_bundle_lib_travel_src_components_lane_way_utils_LaneWayImageUtil.js').read_text(encoding='utf-8')
    common = (SOURCE / 'ajx-drive-js/amap_bundle_drive_ajx_modules_amap_bundle_lib_travel_src_components_lane_way_utils_LaneWayCommonUtil.js').read_text(encoding='utf-8')
    default = icons.split('DRIVE_WAY_ICON', 1)[1].split('DRIVE_SMALL_WAY_ICON', 1)[0]
    paths = dict(re.findall(r'(NAVI_HUD_VIEW_(?:LANDBACK|FRONT)_[A-Z0-9_]+): _resolveLib\(\x27([^\x27]+)', default))
    # The App chooses these two Chinese resources through its locale helper.
    for letter in ('K', 'O'):
        paths[f'NAVI_HUD_VIEW_LANDBACK_{letter}'] = (
            f'amap_bundle_lib_travel/src/components/lane_way/imgs/main_diff/Symbol_Lane_Back_{letter}.min.svg')
    back_codes = dict(re.findall(r'(\d+): e\.(NAVI_HUD_VIEW_LANDBACK_[A-Z0-9]+)', common))
    front_codes = dict(re.findall(r"'(\d+_\d+)': _LaneWayImageUtil\.default\[a\]\.(NAVI_HUD_VIEW_FRONT_\d+_\d+)", common))
    index = json.loads((SOURCE / 'spx-file-index.json').read_text(encoding='utf-8'))
    catalog = {file['name']: (bundle['bundle_index'], file['raw_fields'])
               for bundle in index for file in bundle['files']}
    with zipfile.ZipFile(SOURCE / 'amap-release.apk') as archive:
        data = archive.read('assets/ajx.bundle/bundles.oajx')
    bundles = inspect(data)['entries']
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {'back': {}, 'front': {}}
    for group, codes in (('back', back_codes), ('front', front_codes)):
        for code, identifier in codes.items():
            path = paths.get(identifier)
            if not path:
                continue
            source = 'amap_bundle_drive/ajx_modules/' + path
            if source not in catalog:
                continue
            payload = extract(data, bundles, *catalog[source])
            if not payload.startswith(b'<svg') or len(payload) > 32768:
                raise ValueError(f'invalid SVG: {source}')
            filename = f'{group}-{code.replace("_", "-")}.svg'
            (OUTPUT / filename).write_bytes(payload)
            manifest[group][code] = '/amap/lane/' + filename
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False,
                                   separators=(',', ':')), encoding='utf-8')
    print({key: len(value) for key, value in manifest.items()})


if __name__ == '__main__':
    main()
