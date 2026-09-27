"""Authenticated, bounded viewport batches with a process-isolated decoder."""
import os
import gzip
from ffvideo.amap_cache import MapCache
import json
from pathlib import Path
import subprocess
import sys
import threading
import sqlite3
import re
import uuid
from flask import request, current_app
from ffvideo.utils import login_check, json_ok, json_fail

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.Lock()



def grids(payload):
    tiles = payload.get('tiles') if isinstance(payload, dict) else None
    level = payload.get('level', 14) if isinstance(payload, dict) else 14
    if type(level) is not int or level not in (3, 6, 8, 10, 12, 14):
        raise ValueError('invalid level')
    if not isinstance(tiles, list) or not 1 <= len(tiles) <= 24:
        raise ValueError('invalid batch')
    if any(not isinstance(t, list) or len(t) != 2 or any(type(v) is not int or not 0 <= v < 1 << level for v in t) for t in tiles):
        raise ValueError('invalid tile')
    return list(dict.fromkeys(tuple(t) for t in tiles))


def add_amap_map_route(app):
    @app.after_request
    def compress_map_response(response):
        if request.path != '/api/amap-app/map':
            return response
        response.vary.add('Accept-Encoding')
        # Authenticated map responses must not enter shared proxy caches.
        response.headers['Cache-Control'] = 'private, no-store'
        if (response.status_code != 200 or response.is_streamed or
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

    disk = MapCache(app.config.get('AMAP_CACHE_PATH') or Path(os.environ.get('TMC_AMAP_CACHE_DIR', ROOT / '.local-data/amap-cache')) / 'map.sqlite3')

    @app.route('/api/amap-app/cache', methods=['GET', 'PUT', 'DELETE'])
    @login_check
    def map_cache_settings():
        try:
            settings = request.get_json(silent=True) if request.method == 'PUT' else None
            if request.method == 'PUT' and not isinstance(settings, dict):
                raise ValueError('缓存设置无效')
            return json_ok(disk.status(settings, clear=request.method == 'DELETE'))
        except ValueError as error:
            return json_fail(message=str(error)), 400
        except (OSError, sqlite3.Error):
            current_app.logger.error('amap cache storage unavailable')
            return json_fail(message='缓存目录不可写或数据库不可用'), 503

    @app.post('/api/amap-app/map')
    @login_check
    def amap_map():
        if request.content_length and request.content_length > 4096:
            return json_fail(message='请求过大'), 413
        try:
            payload = request.get_json(silent=True)
            tiles = grids(payload)
            level = payload.get('level', 14)
            tiles = [(level, *t) for t in tiles]
        except ValueError:
            return json_fail(message='地图范围无效'), 400
        try:
            cached, cache_generation = disk.read(tiles)
        except (OSError, sqlite3.Error):
            current_app.logger.error('amap disk cache read failed; continuing without cache')
            cached, cache_generation = {}, -1
        if len(cached) == len(tiles):
            return json_ok({'tiles': [cached[t] for t in tiles]})
        # A disconnected browser does not stop the bounded helper. Do not
        # launch duplicate work or treat normal contention as rate limiting.
        if not LOCK.acquire(blocking=False):
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
                    input=json.dumps({'level': level, 'tiles': [t[1:] for t in missing]}).encode(), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, cwd=ROOT, timeout=65, check=True)
                if len(process.stdout) > 24 * 1024 * 1024:
                    raise ValueError('output limit')
                result = json.loads(process.stdout)
                if 'error' in result:
                    current_app.logger.error('amap map request=%s helper diagnostic=%s', request_id, json.dumps(result.get('diagnostic', {}), ensure_ascii=False)[:3000])
                    raise ValueError('helper unavailable')
                for tile in result.get('tiles', []):
                    key = (level, tile['x'], tile['y'])
                    if key not in missing:
                        raise ValueError('unexpected tile')
                    if not tile.get('error'):
                        cached[key] = tile
                        try:
                            disk.write(key, tile, cache_generation)
                        except (OSError, sqlite3.Error):
                            current_app.logger.error('amap disk cache write failed; serving downloaded tile')
            return json_ok({'tiles': [cached.get(t, {'level': t[0], 'x': t[1], 'y': t[2], 'error': 'unsupported-tile'}) for t in tiles]})
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            # Never log raw stderr or exception messages containing signed URLs.
            detail = ''
            if isinstance(error, subprocess.CalledProcessError):
                stderr = (error.stderr or b'').decode('utf-8', errors='replace')
                missing = re.search(r"ModuleNotFoundError: No module named '([a-zA-Z0-9_.]+)'", stderr)
                detail = 'exit=' + str(error.returncode)
                if missing:
                    detail += ' missing_module=' + missing.group(1)
            elif isinstance(error, subprocess.TimeoutExpired):
                detail = 'timeout=65s'
            elif isinstance(error, OSError):
                detail = 'errno=' + str(error.errno)
            current_app.logger.error('amap map request=%s level=%s tiles=%s failure=%s %s', request_id, level, len(tiles), type(error).__name__, detail)
            return json_fail(message=f'App 地图暂不可用，请重试（错误编号：{request_id}）'), 502
        finally:
            LOCK.release()
