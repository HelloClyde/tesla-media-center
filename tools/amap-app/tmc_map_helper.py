"""Isolated bounded App BMD download -> named geographic line DTO."""
import hashlib
import base64
import json
import os
import sys
import time
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import requests
from bmd_tile import catalog, tile_id, unpack, LIMIT
from bmd_geometry import geographic_features
from bmd_surfaces import geographic_surfaces
from bmd_styles import load_paints
from bmd_points import geographic_labels
from bmd_buildings import geographic_buildings
from route_v51 import fields, one
from tmc_route_helper import check_assets, ASSETS

VERSION_URL = 'https://m5.amap.com/ws/render/bmd/version/'
VERSION_TTL_SECONDS = 120
TILE_HOSTS = {'https://render-prod-tile.amap.com', 'https://render-prod-backup-tile.amap.com'}


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


def version_catalog(material, cache_path=None):
    """Reuse the small APK BMD catalog across short-lived tile helpers."""
    channel = material['getAosChannel']
    path = Path(cache_path) if cache_path else None
    now = time.time()
    if path:
        try:
            if path.stat().st_size <= 4096:
                saved = json.loads(path.read_text(encoding='utf-8'))
                versions = {int(k): v for k, v in saved['versions'].items()}
                if (saved['channel'] == channel and 0 <= now - saved['fetchedAt'] <= VERSION_TTL_SECONDS
                        and saved['host'] in TILE_HOSTS and all(type(v) is int and v >= 0 for v in versions.values())
                        and {0, 1, 2, 5, 6}.issubset(versions)):
                    return saved['host'], versions
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
    sign = hashlib.md5((channel + '@' + material['getAosKey']).encode()).hexdigest().upper()
    raw = download(VERSION_URL, dict(channel=channel, diu='', sign=sign, output='bin', isolTag=162500, cSrc=1))
    versions = catalog(raw)
    host = one(fields(raw), 5).decode()
    # The version service cannot redirect this helper to an arbitrary host.
    if host not in TILE_HOSTS:
        raise ValueError('unsupported tile host')
    if path:
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps({'channel': channel, 'fetchedAt': now,
                                             'host': host, 'versions': versions}), encoding='utf-8')
            os.replace(temporary, path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return host, versions


def main(payload):
    if payload.get('layer') == 'lanes':
        from tmc_lane_helper import main as lane_main
        return lane_main(payload)
    tiles = payload['tiles']
    raw_mode = payload.get('format') == 'bmd'
    level = payload.get('level', 14)
    if type(level) is not int or level not in (3, 6, 8, 10, 12, 14, 15):
        raise ValueError('invalid level')
    if not isinstance(tiles, list) or not 1 <= len(tiles) <= 24:
        raise ValueError('invalid tiles')
    for tile in tiles:
        if not isinstance(tile, list) or len(tile) != 2 or any(type(v) is not int or not 0 <= v < 1 << level for v in tile):
            raise ValueError('invalid grid')
    check_assets()
    from native_signer import load_material
    material = load_material(ASSETS)
    host, versions = version_catalog(material, payload.get('versionCachePath'))
    paints = load_paints(ASSETS, 8, variant='navigation') if level == 15 else load_paints(ASSETS, 2)
    road_paints = load_paints(ASSETS, 1) if level != 15 else {}
    def fetch(tile):
        x, y = tile
        identity = tile_id(level, x, y)
        result = {'x': x, 'y': y, 'level': level}
        failures = []
        layers = [(5, 'buildings')] if level == 15 else [(2, 'collection'), (1, 'surfaces'), (6, 'transit')]
        # These two source levels cover the App's far-view labels at zoom 3–9.
        result['placeLabels'] = []
        if level in (3, 6):
            layers.append((0, 'placeLabels'))
        for kind, field in layers:
            try:
                response = download(host + '/ws/render/bmd/tile', dict(version=versions[kind], tileType=kind, tileId=identity,
                                    i18nVer=0, ct=1, isolTag=162500, cSrc=1))
                data = unpack(response, identity, kind)
                if raw_mode:
                    result[field + 'Bmd'] = base64.b64encode(data).decode('ascii')
                    if kind == 2 and data:
                        from bmd_geometry import decode as decode_roads
                        from bmd_styles import style_bindings
                        bindings = style_bindings(data, 31, len(decode_roads(data)))
                        used = {f'{category}/{subtype}' for category, subtype in bindings.values()}
                        result['roadPaints'] = {
                            theme: {f'{category}/{subtype}': stops for (category, subtype), stops in lookup.items()
                                    if f'{category}/{subtype}' in used}
                            for theme, lookup in road_paints.items()
                        }
                elif kind == 5:
                    result['buildings'], skipped = geographic_buildings(data, (level, x, y), paints) if data else ([], 0)
                    if skipped:
                        result['unsupportedBuildingParts'] = skipped
                        failures.append('building-parts')
                elif kind == 2:
                    result[field] = geographic_features(data, (level, x, y), road_paints) if data else {'type': 'FeatureCollection', 'features': []}
                    used = {f['properties'].get('paintKey') for f in result[field]['features']}
                    result['roadPaints'] = {theme: {f'{k[0]}/{k[1]}': v for k, v in lookup.items() if f'{k[0]}/{k[1]}' in used}
                                            for theme, lookup in road_paints.items()}
                elif kind in (0, 6):
                    result[field] = geographic_labels(data, (level, x, y), places=kind == 0) if data else []
                else:
                    result[field] = geographic_surfaces(data, (level, x, y), paints) if data else []
            except Exception:
                failures.append(field)
        if all(field in failures for _, field in layers):
            result['error'] = 'unsupported-tile'
        elif failures:
            result['missingLayers'] = failures
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = {'tiles': list(pool.map(fetch, tiles))}
        if raw_mode:
            result['paints'] = {theme: {f'{key[0]}/{key[1]}': stops for key, stops in table.items()}
                                for theme, table in paints.items()}
        return result


if __name__ == '__main__':
    try:
        result = main(json.loads(sys.stdin.buffer.read(4096)))
    except Exception as error:
        # HTTP exception messages may contain signed URLs; retain only safe metadata.
        reason = str(error) if str(error) in {'missing-runtime', 'asset-version-mismatch', 'unsupported tile host', 'unexpected status', 'response too large'} else type(error).__name__
        frames = [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                  for f in traceback.extract_tb(error.__traceback__)[-8:]]
        result = {'error': 'map-unavailable', 'diagnostic': {'reason': reason, 'frames': frames}}
        if isinstance(error, ImportError):
            result['diagnostic']['module'] = error.name
        if isinstance(error, requests.HTTPError) and error.response is not None:
            result['diagnostic']['httpStatus'] = error.response.status_code
    # The Flask parent decodes subprocess stdout as UTF-8. Keep the wire JSON
    # ASCII-only so Windows console encodings cannot corrupt map labels.
    print(json.dumps(result, ensure_ascii=True))
