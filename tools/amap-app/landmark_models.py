"""Fetch geographic model instances through the App's two-level BMD index.

The index tile IDs are packed coordinates, not ordinary map grid IDs. The
second-level record's field 7 is the ID of a type-16 resource descriptor.
"""
import hashlib
import json
import math
import os
import re
import struct
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
import zstandard

from bmd_tile import catalog, unpack
from model_index_coordinates import index_bounds
from native_signer import load_material
from route_v51 import fields, one
from tmc_route_helper import ASSETS, check_assets

ROOT_ID = 1 << 48
MAX_DOWNLOAD = 16 * 1024 * 1024
MODEL_URL = re.compile(rb'https://mapstudio-data\.amap\.com/mapstudio-model/publish/model/online/[A-Za-z0-9_./-]+\.dat')


def bounded_get(url, params=None):
    with requests.get(url, params=params, timeout=(5, 18), stream=True,
                      allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('unexpected response')
        output = bytearray()
        for chunk in response.iter_content(65536):
            output.extend(chunk)
            if len(output) > MAX_DOWNLOAD:
                raise ValueError('resource too large')
        return bytes(output)


def atomic_write(target, data):
    temporary = target.with_name(f'.{target.name}.{os.getpid()}.tmp')
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def version_info():
    check_assets()
    material = load_material(ASSETS)
    channel = material['getAosChannel']
    sign = hashlib.md5((channel + '@' + material['getAosKey']).encode()).hexdigest().upper()
    raw = bounded_get('https://m5.amap.com/ws/render/bmd/version/',
                      dict(channel=channel, diu='', sign=sign, output='bin', isolTag=162500, cSrc=1))
    host = one(fields(raw), 5).decode('ascii')
    if host not in ('https://render-prod-tile.amap.com', 'https://render-prod-backup-tile.amap.com'):
        raise ValueError('unsupported tile host')
    versions = catalog(raw)
    return host, {kind: versions[kind] for kind in (15, 16)}


def tile(host, versions, kind, identity, cache_dir, ttl_seconds):
    if not 0 <= identity < 1 << 63 or kind not in (15, 16):
        raise ValueError('invalid model tile')
    target = cache_dir / f'tile-{kind}-{versions[kind]}-{identity}.bin'
    if target.is_file() and time.time() - target.stat().st_mtime < min(ttl_seconds, 86400):
        return target.read_bytes()
    response = bounded_get(host + '/ws/render/bmd/tile',
                           dict(version=versions[kind], tileType=kind, tileId=identity,
                                i18nVer=0, ct=1, isolTag=162500, cSrc=1))
    result = unpack(response, identity, kind)
    atomic_write(target, result)
    return result


def index_records(payload):
    outer = fields(payload)
    if one(outer, 1) != 15:
        raise ValueError('wrong model index type')
    result = []
    for section in outer.get(3, []):
        for entry in fields(section).get(4, []):
            record = fields(entry)
            identity, width, height = (one(record, n) for n in (1, 2, 3))
            if not all(isinstance(v, int) for v in (identity, width, height)):
                raise ValueError('invalid index record')
            bounds = index_bounds(identity, width, height)
            resource = one(record, 7) if 7 in record else None
            if resource is not None and (not isinstance(resource, bytes) or
                                         not re.fullmatch(rb'[0-9]{1,19}', resource)):
                raise ValueError('invalid model resource ID')
            result.append((identity, bounds, int(resource) if resource is not None else None))
    return result


def intersects(bounds, longitude, latitude, radius_m):
    lon_radius = radius_m / (111320 * max(0.1, math.cos(math.radians(latitude))))
    lat_radius = radius_m / 111320
    return (min(bounds[0], bounds[2]) <= longitude + lon_radius and
            max(bounds[0], bounds[2]) >= longitude - lon_radius and
            min(bounds[1], bounds[3]) <= latitude + lat_radius and
            max(bounds[1], bounds[3]) >= latitude - lat_radius)


def descriptor(payload):
    root = fields(payload)
    container = one(fields(one(root, 1)), 1)
    found = MODEL_URL.search(container)
    if not found:
        raise ValueError('model URL absent')
    url = found.group().decode('ascii')
    parsed = urlsplit(url)
    if (parsed.hostname != 'mapstudio-data.amap.com' or parsed.scheme != 'https' or
            parsed.query or '..' in parsed.path.split('/')):
        raise ValueError('invalid model URL')
    transform = fields(one(fields(one(root, 2)), 1))
    position = one(transform, 1)
    coordinates = fields(position)
    longitude, latitude = one(coordinates, 1), one(coordinates, 2)
    if not isinstance(longitude, int) or not isinstance(latitude, int):
        raise ValueError('invalid model coordinates')
    point = [longitude / 1_000_000, latitude / 1_000_000]
    if not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90:
        raise ValueError('invalid model position')
    angle_raw, scale_raw = one(transform, 2), one(transform, 3)
    if (not isinstance(angle_raw, bytes) or len(angle_raw) != 4 or
            not isinstance(scale_raw, bytes) or len(scale_raw) != 4):
        raise ValueError('invalid model transform')
    angle, scale = struct.unpack('<f', angle_raw)[0], struct.unpack('<f', scale_raw)[0]
    if not math.isfinite(angle) or not -360 <= angle <= 360 or not math.isfinite(scale) or not 0 < scale <= 10:
        raise ValueError('invalid model transform')
    return url, point, angle, scale


def model_glb(compressed):
    raw = zstandard.ZstdDecompressor().decompress(compressed, max_output_size=32 * 1024 * 1024)
    if (len(raw) < 140 or raw[:12] != bytes.fromhex('fffffffff684058f14000000') or
            struct.unpack_from('<I', raw, 12)[0] != len(raw)):
        raise ValueError('unsupported App model container')
    start = raw.find(b'glTF', 28, 256)
    if start < 0 or start + 20 > len(raw):
        raise ValueError('GLB missing')
    size = struct.unpack_from('<I', raw, start + 8)[0]
    if size < 20 or start + size + 12 != len(raw):
        raise ValueError('invalid GLB bounds')
    glb = raw[start:start + size]
    json_size, json_kind = struct.unpack_from('<II', glb, 12)
    if json_kind != 0x4e4f534a or 20 + json_size > len(glb):
        raise ValueError('invalid GLB JSON chunk')
    document = json.loads(glb[20:20 + json_size])
    if document.get('asset', {}).get('version') != '2.0':
        raise ValueError('unsupported glTF version')
    if any('uri' in part for part in document.get('buffers', []) + document.get('images', [])):
        raise ValueError('external model resource')
    return glb


def prune(cache_dir, ttl_seconds, max_bytes):
    files = [path for path in cache_dir.iterdir() if path.is_file() and
             (re.fullmatch(r'tile-(?:15|16)-[0-9]+-[0-9]+\.bin', path.name) or
              re.fullmatch(r'[0-9]{1,19}-[0-9a-f]{12}\.glb', path.name))]
    now = time.time()
    for path in files:
        if now - path.stat().st_mtime > ttl_seconds:
            path.unlink()
    files = sorted((path for path in files if path.exists()), key=lambda path: path.stat().st_mtime)
    total = sum(path.stat().st_size for path in files)
    for path in files:
        if total <= max_bytes:
            break
        size = path.stat().st_size
        path.unlink()
        total -= size


def nearby(longitude, latitude, radius_m, cache_dir, ttl_hours=168, max_bytes=128 * 1024 * 1024):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ttl_seconds = ttl_hours * 3600
    prune(cache_dir, ttl_seconds, max_bytes)
    if max_bytes < 256 * 1024:
        return []
    host, versions = version_info()
    parents = [record for record in index_records(tile(host, versions, 15, ROOT_ID, cache_dir, ttl_seconds))
               if intersects(record[1], longitude, latitude, radius_m)]
    parents.sort(key=lambda record:
                 ((record[1][0] + record[1][2]) / 2 - longitude) ** 2 +
                 ((record[1][1] + record[1][3]) / 2 - latitude) ** 2)
    result = []
    for parent_id, _, _ in parents[:12]:
        payload = tile(host, versions, 15, parent_id, cache_dir, ttl_seconds)
        if not payload:
            continue
        for child_id, bounds, resource_id in index_records(payload):
            if resource_id is None or not intersects(bounds, longitude, latitude, radius_m):
                continue
            resource = tile(host, versions, 16, resource_id, cache_dir, ttl_seconds)
            if not resource:
                continue
            url, point, angle, scale = descriptor(resource)
            model_name = f'{resource_id}-{hashlib.sha256(url.encode()).hexdigest()[:12]}.glb'
            target = cache_dir / model_name
            if not target.is_file():
                atomic_write(target, model_glb(bounded_get(url)))
            result.append({'id': str(resource_id), 'position': point, 'bounds': bounds,
                           'rotationDegrees': angle, 'scale': scale,
                           'model': model_name})
            if len(result) >= 8:
                prune(cache_dir, ttl_seconds, max_bytes)
                return [item for item in result if (cache_dir / item['model']).is_file()]
    prune(cache_dir, ttl_seconds, max_bytes)
    return [item for item in result if (cache_dir / item['model']).is_file()]


if __name__ == '__main__':
    try:
        arguments = json.loads(sys.stdin.buffer.read(1024))
        lon, lat, radius = arguments['lon'], arguments['lat'], arguments['radius']
        path = Path(arguments['cacheDir'])
        ttl_hours, max_bytes = arguments.get('ttlHours', 168), arguments.get('maxBytes', 128 * 1024 * 1024)
        if (not all(type(x) in (int, float) and math.isfinite(x) for x in (lon, lat, radius)) or
                not -180 <= lon <= 180 or not -90 <= lat <= 90 or not 100 <= radius <= 600 or
                not path.is_absolute() or type(ttl_hours) is not int or not 1 <= ttl_hours <= 2160 or
                type(max_bytes) is not int or not 0 <= max_bytes <= 4096 * 1024 * 1024):
            raise ValueError('invalid landmark query')
        print(json.dumps({'models': nearby(lon, lat, radius, path, ttl_hours, max_bytes)}))
    except Exception as error:
        print(json.dumps({'error': type(error).__name__}))
