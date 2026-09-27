"""Isolated bounded App BMD download -> named geographic line DTO."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
import requests
from bmd_tile import catalog, tile_id, unpack, LIMIT
from bmd_geometry import geographic_features
from bmd_surfaces import geographic_surfaces
from bmd_styles import load_paints
from bmd_points import geographic_labels
from route_v51 import fields, one
from tmc_route_helper import check_assets, ASSETS


def download(url, params):
    with requests.get(url, params=params, headers={'Accept': 'application/x-protobuf'},
                      timeout=(5, 12), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('unexpected status')
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > LIMIT:
                raise ValueError('response too large')
        return bytes(data)


def main(payload):
    tiles = payload['tiles']
    level = payload.get('level', 14)
    if type(level) is not int or level not in (3, 6, 8, 10, 12, 14):
        raise ValueError('invalid level')
    if not isinstance(tiles, list) or not 1 <= len(tiles) <= 24:
        raise ValueError('invalid tiles')
    for tile in tiles:
        if not isinstance(tile, list) or len(tile) != 2 or any(type(v) is not int or not 0 <= v < 1 << level for v in tile):
            raise ValueError('invalid grid')
    check_assets()
    from native_signer import load_material
    material = load_material(ASSETS)
    channel = material['getAosChannel']
    sign = hashlib.md5((channel + '@' + material['getAosKey']).encode()).hexdigest().upper()
    raw = download('https://m5.amap.com/ws/render/bmd/version/',
                   dict(channel=channel, diu='', sign=sign, output='bin', isolTag=162500, cSrc=1))
    versions = catalog(raw)
    paints = load_paints(ASSETS / 'amap-release.apk')
    host = one(fields(raw), 5).decode()
    # The version service cannot redirect this helper to an arbitrary host.
    if host not in {'https://render-prod-tile.amap.com', 'https://render-prod-backup-tile.amap.com'}:
        raise ValueError('unsupported tile host')
    def fetch(tile):
        x, y = tile
        identity = tile_id(level, x, y)
        result = {'x': x, 'y': y, 'level': level}
        failures = []
        layers = [(2, 'collection'), (1, 'surfaces'), (6, 'transit')]
        # These two source levels cover the App's far-view labels at zoom 3–9.
        result['placeLabels'] = []
        if level in (3, 6):
            layers.append((0, 'placeLabels'))
        for kind, field in layers:
            try:
                response = download(host + '/ws/render/bmd/tile', dict(version=versions[kind], tileType=kind, tileId=identity,
                                    i18nVer=0, ct=1, isolTag=162500, cSrc=1))
                data = unpack(response, identity, kind)
                if kind == 2:
                    result[field] = geographic_features(data, (level, x, y)) if data else {'type': 'FeatureCollection', 'features': []}
                elif kind in (0, 6):
                    result[field] = geographic_labels(data, (level, x, y), places=kind == 0) if data else []
                else:
                    result[field] = geographic_surfaces(data, (level, x, y), paints) if data else []
            except Exception:
                failures.append(field)
        if len(failures) == len(layers):
            result['error'] = 'unsupported-tile'
        elif failures:
            result['missingLayers'] = failures
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        return {'tiles': list(pool.map(fetch, tiles))}


if __name__ == '__main__':
    try:
        result = main(json.loads(sys.stdin.buffer.read(4096)))
    except Exception:
        result = {'error': 'map-unavailable'}
    print(json.dumps(result, ensure_ascii=False))
