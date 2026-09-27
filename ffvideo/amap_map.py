"""Authenticated, bounded viewport batches with a process-isolated decoder."""
from collections import OrderedDict
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from flask import request
from ffvideo.utils import login_check, json_ok, json_fail

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.Lock()
CACHE = OrderedDict()


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
        # Completed tiles remain available while another viewport is loading.
        cached = [CACHE.get(t) for t in tiles]
        if all(item and time.monotonic() - item[0] <= 600 and not item[1].get('missingLayers') for item in cached):
            return json_ok({'tiles': [item[1] for item in cached]})
        # A disconnected browser does not stop the bounded helper. Do not
        # launch duplicate work or treat normal contention as rate limiting.
        if not LOCK.acquire(blocking=False):
            return json_ok({'tiles': [], 'pending': True, 'retryAfterMs': 750}), 202
        try:
            now = time.monotonic()
            missing = [t for t in tiles if t not in CACHE or now - CACHE[t][0] > 600 or CACHE[t][1].get('missingLayers')]
            if missing:
                process = subprocess.run([sys.executable, str(ROOT / 'tools/amap-app/tmc_map_helper.py')],
                    input=json.dumps({'level': level, 'tiles': [t[1:] for t in missing]}).encode(), stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, cwd=ROOT, timeout=65, check=True)
                if len(process.stdout) > 24 * 1024 * 1024:
                    raise ValueError('output limit')
                result = json.loads(process.stdout)
                if 'error' in result:
                    raise ValueError('helper unavailable')
                for tile in result.get('tiles', []):
                    key = (level, tile['x'], tile['y'])
                    if key not in missing:
                        raise ValueError('unexpected tile')
                    if not tile.get('error'):
                        CACHE[key] = (time.monotonic(), tile)
                        CACHE.move_to_end(key)
                while len(CACHE) > 96:
                    CACHE.popitem(last=False)
            return json_ok({'tiles': [CACHE[t][1] if t in CACHE and time.monotonic() - CACHE[t][0] <= 600
                            else {'level': t[0], 'x': t[1], 'y': t[2], 'error': 'unsupported-tile'} for t in tiles]})
        except (ValueError, KeyError, OSError, subprocess.SubprocessError):
            return json_fail(message='App 地图暂不可用，请重试'), 502
        finally:
            LOCK.release()
