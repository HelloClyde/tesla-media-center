"""Extract the four SVGs used by APK 17.00's direct road-switch widgets."""
import hashlib
import json
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from extract_spx_file import extract
from inspect_oajx import inspect

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.local-data/amap-app'
OUTPUT = ROOT / 'web/public/amap/road-switch'
RESOURCES = {
    'main': 'ic-lane-o-b.svg', 'side': 'ic-siderode-o-b.svg',
    'ground': 'ic-bridgedown-o-b.svg', 'elevated': 'ic-bridgeup-o-b.svg',
}


def main():
    index = json.loads((SOURCE / 'spx-file-index.json').read_text(encoding='utf8'))
    catalog = {item['name']: (bundle['bundle_index'], item['raw_fields'])
               for bundle in index for item in bundle['files']}
    with zipfile.ZipFile(SOURCE / 'amap-release.apk') as archive:
        data = archive.read('assets/ajx.bundle/bundles.oajx')
    bundles = inspect(data)['entries']
    entries = {}
    for target, filename in RESOURCES.items():
        resource = 'amap_bundle_framework/src/resource/svg/navigation/' + filename
        payload = extract(data, bundles, *catalog[resource])
        if not payload.startswith(b'<svg') or len(payload) > 32768:
            raise ValueError('unexpected road-switch resource')
        root = ET.fromstring(payload)
        if root.tag.split('}')[-1] != 'svg' or any(
            element.tag.split('}')[-1] in ('script', 'foreignObject')
            or any(key.lower().startswith('on') for key in element.attrib) for element in root.iter()):
            raise ValueError('unsupported active SVG')
        entries[target] = (filename, resource, payload)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {'source': 'AMap APK 17.00.0.2005 OAJX/SPX', 'icons': {}}
    for target, (filename, resource, payload) in entries.items():
        (OUTPUT / filename).write_bytes(payload)
        manifest['icons'][target] = {'resource': resource, 'file': filename,
            'sha256': hashlib.sha256(payload).hexdigest()}
    (OUTPUT / 'source.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf8', newline='\n')
    print(json.dumps({'extractedIcons': len(entries), 'bytes': sum(len(item[2]) for item in entries.values())}))


if __name__ == '__main__':
    main()
