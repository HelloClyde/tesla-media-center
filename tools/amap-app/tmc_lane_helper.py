"""One LNDS tile per isolated request, returned as compact ground boundary XY."""
import hashlib
import json
import math
import os
import time
from pathlib import Path
from uuid import uuid4

from bmd_tile import tile_id
from lane_render import HOSTS, version_catalog, inspect_response
from lane_render_blocks import decode_render_blocks
from lane_native_decoder import decode
from lane_tile_boundaries import extract_boundaries
from tmc_route_helper import ASSETS, check_assets

VERSION_URL = 'https://m5.amap.com/ws/render/lnds/version/'
VERSION_TTL_SECONDS = 120


def lnds_version_catalog(material, cache_path=None):
    """Share the verified LNDS catalog across isolated one-tile decoders."""
    channel = material['getAosChannel']
    path = Path(cache_path) if cache_path else None
    now = time.time()
    if path:
        try:
            if path.stat().st_size <= 4096:
                saved = json.loads(path.read_text(encoding='utf-8'))
                versions = {int(k): v for k, v in saved['versions'].items()}
                if (saved['channel'] == channel and 0 <= now - saved['fetchedAt'] <= VERSION_TTL_SECONDS
                        and saved['host'] in HOSTS and all(type(versions.get(k)) is int
                            and 0 < versions[k] < 2**32 for k in (22, 23))):
                    return saved['host'], {k: versions[k] for k in (22, 23)}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
    from tmc_map_helper import download
    sign = hashlib.md5((channel + '@' + material['getAosKey']).encode()).hexdigest().upper()
    host, versions = version_catalog(download(VERSION_URL,
                                             dict(channel=channel, diu='', sign=sign, output='bin')))
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


def boundary_dto_with_kinds(lines, kinds):
    if len(lines) != len(kinds):
        raise ValueError('lane metadata does not match geometry')
    result, result_kinds, seen, count = [], [], {}, 0
    for line, kind in zip(lines, kinds):
        if kind not in (1, 3):
            raise ValueError('unknown lane metadata kind')
        points = []
        for point in line:
            lng, lat = point[:2]
            if not math.isfinite(lng) or not math.isfinite(lat) or not -180 <= lng <= 180 or not -85 <= lat <= 85:
                raise ValueError('invalid lane coordinate')
            xy = (round(lng, 7), round(lat, 7))
            if not points or xy != points[-1]:
                points.append(xy)
        if len(points) < 2:
            continue
        key = min(tuple(points), tuple(reversed(points)))
        if key in seen:
            # Different native segments can trace the same boundary in reverse.
            # Retain the richer type while keeping a single line of geometry.
            if kind == 3:
                result_kinds[seen[key]] = 3
            continue
        seen[key] = len(result)
        count += len(points)
        if count > 150000:
            raise ValueError('lane geometry limit')
        result.append(points)
        result_kinds.append(kind)
    return result, result_kinds


def boundary_dto(lines):
    return boundary_dto_with_kinds(lines, [1] * len(lines))[0]


def main(payload):
    from tmc_map_helper import download
    from native_signer import load_material
    tiles = payload.get('tiles')
    if payload.get('level') != 15 or not isinstance(tiles, list) or len(tiles) != 1:
        raise ValueError('one level-15 lane tile required')
    tile = tiles[0]
    if not isinstance(tile, list) or len(tile) != 2 or any(type(v) is not int or not 0 <= v < 32768 for v in tile):
        raise ValueError('invalid lane tile')
    check_assets()
    material = load_material(ASSETS)
    host, versions = lnds_version_catalog(material, payload.get('versionCachePath'))
    identity = tile_id(15, *tile)
    raw = download(host + '/ws/render/lnds/tile', dict(version=versions[22], tileType=22,
                                                     tileId=identity, i18nVer=0, ct=1))
    body, _ = inspect_response(raw, identity, 22)
    blocks = decode_render_blocks(body, identity)['blocks'] if body else []
    if len(blocks) > 8:
        raise ValueError('lane block limit')
    library_path = ASSETS / 'libamapr.so'
    if library_path.stat().st_size > 40 * 1024 * 1024:
        raise ValueError('lane library limit')
    library = library_path.read_bytes()
    lines, kinds = [], []
    for block in blocks:
        flatbuffer = decode(block['data'], library, identity, block['id'])
        extracted = extract_boundaries(flatbuffer, include_raw_metadata=True)
        lines.extend(extracted['lines'])
        kinds.extend(3 if any(record['kindRaw'] == 3 for record in meta['records']) else 1
                     for meta in extracted['lineMetadataRaw'])
    boundaries, boundary_kinds = boundary_dto_with_kinds(lines, kinds)
    return {'tiles': [{'level': 15, 'x': tile[0], 'y': tile[1],
                       'laneBoundaries': boundaries, 'laneBoundaryKindsRaw': boundary_kinds,
                       'laneVersion': versions[22],
                       'heightMode': 'ground', 'source': 'app-lnds'}]}
