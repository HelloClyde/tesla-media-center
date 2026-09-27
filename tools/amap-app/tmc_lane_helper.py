"""One LNDS tile per isolated request, returned as compact ground boundary XY."""
import hashlib
import math
import zipfile

from bmd_tile import tile_id
from lane_render import version_catalog, inspect_response
from lane_render_blocks import decode_render_blocks
from lane_native_decoder import decode
from lane_tile_boundaries import extract_boundaries
from tmc_route_helper import ASSETS, check_assets


def boundary_dto(lines):
    result, seen, count = [], set(), 0
    for line in lines:
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
            continue
        seen.add(key)
        count += len(points)
        if count > 150000:
            raise ValueError('lane geometry limit')
        result.append(points)
    return result


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
    channel = material['getAosChannel']
    sign = hashlib.md5((channel + '@' + material['getAosKey']).encode()).hexdigest().upper()
    host, versions = version_catalog(download('https://m5.amap.com/ws/render/lnds/version/',
                                             dict(channel=channel, diu='', sign=sign, output='bin')))
    identity = tile_id(15, *tile)
    raw = download(host + '/ws/render/lnds/tile', dict(version=versions[22], tileType=22,
                                                     tileId=identity, i18nVer=0, ct=1))
    body, _ = inspect_response(raw, identity, 22)
    blocks = decode_render_blocks(body, identity)['blocks'] if body else []
    if len(blocks) > 8:
        raise ValueError('lane block limit')
    # The already pinned APK is shipped by the existing Release workflow.
    # No external filesystem extraction, writable asset mount or extra download.
    with zipfile.ZipFile(ASSETS / 'amap-release.apk') as archive:
        info = archive.getinfo('lib/arm64-v8a/libamapr.so')
        if info.file_size > 40 * 1024 * 1024:
            raise ValueError('lane library limit')
        library = archive.read(info)
    lines = []
    for block in blocks:
        flatbuffer = decode(block['data'], library, identity, block['id'])
        lines.extend(extract_boundaries(flatbuffer)['lines'])
    return {'tiles': [{'level': 15, 'x': tile[0], 'y': tile[1],
                       'laneBoundaries': boundary_dto(lines), 'laneVersion': versions[22],
                       'heightMode': 'ground', 'source': 'app-lnds'}]}
