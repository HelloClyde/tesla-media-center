"""Offline inventory of App map dependencies; does not request map data.

Only allowlisted engine identifiers and endpoint paths are emitted. Binary
strings are evidence of a dependency, not proof of a working HTTP protocol.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

LIBRARIES = ('libmap_kit.so', 'libamapr.so', 'libamapdsl.so')
IDENTIFIERS = (
    'CreateVmapModule', 'GLMapEngine_nativeAttachSurfaceToRenderDevice',
    'nativeBindMapEngineToRenderDevice', 'eglCreateContext',
    'eglCreateWindowSurface', 'glDrawElements', 'MapTileDownloadManger',
    'MapOnlineParseBmdTile', 'MapOnlineParseBmdTmc', 'MapOnlineParseMapConfig',
    'getMapVectorTileInterface',
)


def inspect(apk):
    result = {'map_protocol_verified': False, 'web_renderer_ported': False, 'libraries': []}
    with zipfile.ZipFile(apk) as archive:
        for name in LIBRARIES:
            data = archive.read('lib/arm64-v8a/' + name)
            endpoints = sorted({match.decode() for match in re.findall(
                rb'https://mps\.amap\.com/ws/mps/(?:vmap|rtt|sdplus|smap|spot)\b', data)})
            result['libraries'].append({
                'name': name, 'sha256': hashlib.sha256(data).hexdigest(),
                'identifiers': [text for text in IDENTIFIERS if text.encode() in data],
                'candidate_endpoints': endpoints,
            })
        result['vmap_assets'] = [name for name in archive.namelist() if name.startswith('assets/vmap/')]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.apk), ensure_ascii=False, indent=2))
