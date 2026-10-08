"""Authenticated, bounded viewport batches with a process-isolated decoder."""
import os
import gzip
import base64
import struct
from ffvideo.amap_cache import MapCache
from storage import data_path
import json
from pathlib import Path
import subprocess
import sys
import threading
import sqlite3
import re
import uuid
import math
from flask import request, current_app, send_file, abort, Response
from ffvideo.utils import login_check, json_ok, json_fail

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.Lock()
BMD_BATCH_MIME = 'application/vnd.tmc.amap-bmd'
BMD_FIELDS = ('collectionBmd', 'surfacesBmd', 'transitBmd', 'placeLabelsBmd', 'buildingsBmd')


def pack_bmd_batch(data):
    """Send verified inner BMD bytes without the JSON/Base64 expansion."""
    manifest = {'version': 1, 'paints': data.get('paints', {}), 'tiles': []}
    chunks = []
    length = 0
    for tile in data['tiles']:
        metadata = {key: value for key, value in tile.items() if key not in BMD_FIELDS}
        spans = {}
        for name in BMD_FIELDS:
            if not tile.get(name):
                continue
            raw = base64.b64decode(tile[name], validate=True)
            if len(raw) > 16 * 1024 * 1024 or length + len(raw) > 24 * 1024 * 1024:
                raise ValueError('BMD batch too large')
            spans[name] = [length, len(raw)]
            chunks.append(raw)
            length += len(raw)
        metadata['bmd'] = spans
        manifest['tiles'].append(metadata)
    header = json.dumps(manifest, ensure_ascii=True, separators=(',', ':')).encode()
    if len(header) > 2 * 1024 * 1024:
        raise ValueError('BMD manifest too large')
    return b'TMCBMD1!' + struct.pack('<I', len(header)) + header + b''.join(chunks)



def grids(payload):
    tiles = payload.get('tiles') if isinstance(payload, dict) else None
    level = payload.get('level', 14) if isinstance(payload, dict) else 14
    if type(level) is not int or level not in (3, 6, 8, 10, 12, 14, 15):
        raise ValueError('invalid level')
    layer = payload.get('layer', 'base') if isinstance(payload, dict) else 'base'
    if layer not in ('base', 'lanes'):
        raise ValueError('invalid layer')
    if not isinstance(tiles, list) or not 1 <= len(tiles) <= 24:
        raise ValueError('invalid batch')
    if layer == 'lanes' and (level != 15 or len(tiles) != 1):
        raise ValueError('invalid lane batch')
    if any(not isinstance(t, list) or len(t) != 2 or any(type(v) is not int or not 0 <= v < 1 << level for v in t) for t in tiles):
        raise ValueError('invalid tile')
    return list(dict.fromkeys(tuple(t) for t in tiles))


def add_amap_map_route(app):
    landmark_cache = Path(data_path('amap-cache/landmarks')).resolve()

    @app.get('/api/amap-app/landmarks')
    @login_check
    def amap_landmarks():
        try:
            longitude = float(request.args['lon'])
            latitude = float(request.args['lat'])
            radius = float(request.args.get('radius', '300'))
            if (not all(math.isfinite(x) for x in (longitude, latitude, radius)) or
                    not -180 <= longitude <= 180 or not -90 <= latitude <= 90 or
                    not 100 <= radius <= 600):
                raise ValueError('invalid coordinates')
        except (KeyError, ValueError):
            return json_fail(message='地标范围无效'), 400
        try:
            policy = disk.status()
            process = subprocess.run([sys.executable, str(ROOT / 'tools/amap-app/landmark_models.py')],
                input=json.dumps({'lon': longitude, 'lat': latitude, 'radius': radius,
                                  'cacheDir': str(landmark_cache), 'ttlHours': policy['ttlHours'],
                                  'maxBytes': max(0, policy['maxMB'] * 1024 * 1024 - policy['usedBytes'])}).encode(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, timeout=65, check=True)
            if len(process.stdout) > 64 * 1024:
                raise ValueError('output limit')
            result = json.loads(process.stdout)
            if 'error' in result:
                raise ValueError(result['error'])
            return json_ok(result)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            current_app.logger.error('amap landmarks failure=%s', type(error).__name__)
            return json_fail(message='特色地标暂不可用'), 502

    @app.get('/api/amap-app/landmarks/<model_name>')
    @login_check
    def amap_landmark_model(model_name):
        if not re.fullmatch(r'[0-9]{1,19}-[0-9a-f]{12}\.glb', model_name):
            abort(404)
        target = landmark_cache / model_name
        if not target.is_file() or target.stat().st_size > 32 * 1024 * 1024:
            abort(404)
        response = send_file(target, mimetype='model/gltf-binary', conditional=True)
        response.headers['Cache-Control'] = 'private, max-age=86400'
        return response

    @app.after_request
    def compress_map_response(response):
        if request.path not in ('/api/amap-app/map', '/api/amap-app/map/prefetch',
                                '/api/amap-app/map/bmd', '/api/amap-app/map/bmd/prefetch'):
            return response
        response.vary.add('Accept-Encoding')
        if request.path in ('/api/amap-app/map/bmd', '/api/amap-app/map/bmd/prefetch'):
            response.vary.add('Accept')
        # Authenticated map responses must not enter shared proxy caches.
        response.headers['Cache-Control'] = 'private, no-store'
        if (request.path not in ('/api/amap-app/map', '/api/amap-app/map/bmd') or response.status_code != 200 or response.is_streamed or
                response.headers.get('Content-Encoding') or
                request.accept_encodings.quality('gzip') <= 0):
            return response
        raw = response.get_data()
        if len(raw) < 1024:
            return response
        encoded = gzip.compress(raw, compresslevel=5, mtime=0)
        if len(encoded) < len(raw):
            response.set_data(encoded)
            response.headers['Content-Encoding'] = 'gzip'
        return response

    disk = MapCache(app.config.get('AMAP_CACHE_PATH') or data_path('amap-cache/map.sqlite3'))
    version_cache = disk.path.with_name('bmd-version-v1.json')
    lane_version_cache = disk.path.with_name('lnds-version-v1.json')

    @app.route('/api/amap-app/cache', methods=['GET', 'PUT', 'DELETE'])
    @login_check
    def map_cache_settings():
        try:
            settings = request.get_json(silent=True) if request.method == 'PUT' else None
            if request.method == 'PUT' and not isinstance(settings, dict):
                raise ValueError('缓存设置无效')
            status = disk.status(settings, clear=request.method == 'DELETE')
            if request.method == 'DELETE':
                version_cache.unlink(missing_ok=True)
                lane_version_cache.unlink(missing_ok=True)
            if request.method == 'DELETE' and landmark_cache.is_dir():
                for path in landmark_cache.iterdir():
                    if path.is_file() and (re.fullmatch(r'tile-(?:15|16)-[0-9]+-[0-9]+\.bin', path.name) or
                                           re.fullmatch(r'[0-9]{1,19}-[0-9a-f]{12}\.glb', path.name)):
                        path.unlink()
            if landmark_cache.is_dir():
                status['landmarkBytes'] = sum(path.stat().st_size for path in landmark_cache.iterdir() if path.is_file())
                status['usedBytes'] += status['landmarkBytes']
            return json_ok(status)
        except ValueError as error:
            return json_fail(message=str(error)), 400
        except (OSError, sqlite3.Error):
            current_app.logger.error('amap cache storage unavailable')
            return json_fail(message='缓存目录不可写或数据库不可用'), 503

    @app.post('/api/amap-app/map')
    @app.post('/api/amap-app/map/prefetch')
    @app.post('/api/amap-app/map/bmd')
    @app.post('/api/amap-app/map/bmd/prefetch')
    @login_check
    def amap_map():
        prefetch = request.path.endswith('/prefetch')
        raw_mode = '/bmd' in request.path
        binary_requested = raw_mode and any(
            part.strip().split(';', 1)[0] == BMD_BATCH_MIME
            for part in request.headers.get('Accept', '').split(','))
        if request.content_length and request.content_length > 4096:
            return json_fail(message='请求过大'), 413
        try:
            payload = request.get_json(silent=True)
            tiles = grids(payload)
            level = payload.get('level', 14)
            layer = payload.get('layer', 'base')
            if raw_mode and layer != 'base':
                raise ValueError('invalid raw map request')
            if prefetch and (level not in (14, 15) or
                             layer != 'base' or len(tiles) > 2):
                raise ValueError('invalid prefetch batch')
            prefix = ('lanes-v2', level) if layer == 'lanes' else ('raw-buildings-v7', level) if raw_mode and level == 15 else ('raw-v2', level) if raw_mode else ('buildings-v8', level) if level == 15 else (level,)
            tiles = [(*prefix, *t) for t in tiles]
        except ValueError:
            return json_fail(message='地图范围无效'), 400
        try:
            cached, cache_generation = disk.read(tiles)
        except (OSError, sqlite3.Error):
            current_app.logger.error('amap disk cache read failed; continuing without cache')
            cached, cache_generation = {}, -1
        def response_data():
            result_tiles = [cached.get(t, {'level': level, 'x': t[-2], 'y': t[-1],
                'error': 'unsupported-tile'}) for t in tiles]
            if raw_mode:
                paints = next((tile.get('paints') for tile in result_tiles if tile.get('paints')), {})
                result_tiles = [{k: v for k, v in tile.items() if k != 'paints'} for tile in result_tiles]
                return {'tiles': result_tiles, 'paints': paints}
            return {'tiles': result_tiles}
        def successful_response():
            if prefetch and not binary_requested:
                # Distant-route warmup has no browser payload. Nearby tiles
                # negotiate BMD and receive the cached bytes in this request.
                return Response(status=204)
            data = response_data()
            if binary_requested:
                try:
                    return Response(pack_bmd_batch(data), mimetype=BMD_BATCH_MIME)
                except (ValueError, TypeError, KeyError):
                    current_app.logger.error('amap BMD binary pack failed; falling back to JSON')
            return json_ok(data)
        if len(cached) == len(tiles):
            return successful_response()
        # A disconnected browser does not stop the bounded helper. Do not
        # launch duplicate work or treat normal contention as rate limiting.
        if not LOCK.acquire(blocking=False):
            if prefetch:
                return Response(status=202, headers={'Retry-After': '1'})
            return json_ok({'tiles': [], 'pending': True, 'retryAfterMs': 750}), 202
        request_id = uuid.uuid4().hex[:12]
        try:
            helper = ROOT / 'tools/amap-app/tmc_map_helper.py'
            if not helper.is_file():
                current_app.logger.error('amap map request=%s missing_helper=tools/amap-app/tmc_map_helper.py rebuild deployment image', request_id)
                raise FileNotFoundError(2, 'map helper missing')
            missing = [t for t in tiles if t not in cached]
            if missing:
                process = subprocess.run([sys.executable, str(helper)],
                    input=json.dumps({'layer': layer, 'level': level, 'tiles': [t[-2:] for t in missing],
                                      'versionCachePath': str(lane_version_cache if layer == 'lanes' else version_cache),
                                      **({'format': 'bmd'} if raw_mode else {})}).encode(), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, cwd=ROOT, timeout=10 if prefetch else 65, check=True)
                if len(process.stdout) > 24 * 1024 * 1024:
                    raise ValueError('output limit')
                result = json.loads(process.stdout)
                if 'error' in result:
                    current_app.logger.error('amap map request=%s helper diagnostic=%s', request_id, json.dumps(result.get('diagnostic', {}), ensure_ascii=False)[:3000])
                    raise ValueError('helper unavailable')
                paints = result.get('paints', {}) if raw_mode else {}
                for tile in result.get('tiles', []):
                    key = (*prefix, tile['x'], tile['y'])
                    if key not in missing:
                        raise ValueError('unexpected tile')
                    if not tile.get('error'):
                        if raw_mode:
                            tile['paints'] = paints
                        cached[key] = tile
                        try:
                            disk.write(key, tile, cache_generation)
                        except (OSError, sqlite3.Error):
                            current_app.logger.error('amap disk cache write failed; serving downloaded tile')
            return successful_response()
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            # Never log raw stderr or exception messages containing signed URLs.
            detail = ''
            if isinstance(error, subprocess.CalledProcessError):
                stderr = (error.stderr or b'').decode('utf-8', errors='replace')
                missing = re.search(r"ModuleNotFoundError: No module named '([a-zA-Z0-9_.]+)'", stderr)
                detail = 'exit=' + str(error.returncode)
                if missing:
                    detail += ' missing_module=' + missing.group(1)
                # Log only the Python exception class, never stderr text: it
                # may contain a signed upstream URL or request parameters.
                failures = re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):', stderr)
                if failures:
                    detail += ' worker_error=' + failures[-1]
                elif not stderr:
                    detail += ' stderr_empty=true'
            elif isinstance(error, subprocess.TimeoutExpired):
                detail = 'timeout=' + ('10s' if prefetch else '65s')
            elif isinstance(error, OSError):
                detail = 'errno=' + str(error.errno)
            current_app.logger.error('amap map request=%s level=%s tiles=%s failure=%s %s', request_id, level, len(tiles), type(error).__name__, detail)
            return json_fail(message=f'App 地图暂不可用，请重试（错误编号：{request_id}）'), 502
        finally:
            LOCK.release()
