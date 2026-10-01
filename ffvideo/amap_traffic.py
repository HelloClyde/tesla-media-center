"""Small, authenticated proxy for AMap's licensed traffic-status service."""
import math
import os
import threading
import time

import requests
from flask import request

from config import get_config_by_key
from ffvideo.utils import json_fail, json_ok, login_check

_URL = 'https://restapi.amap.com/v3/traffic/status/rectangle'
_cache = {}
_lock = threading.Lock()


def _center(value):
    if not isinstance(value, list) or len(value) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError('路况位置无效')
    lng, lat = value
    if not (73 <= lng <= 135 and 18 <= lat <= 54):
        raise ValueError('当前位置不在支持的路况区域')
    return round(lng / .005) * .005, round(lat / .005) * .005


def _roads(payload):
    info = payload.get('trafficinfo') or {}
    if not isinstance(info, dict):
        return []
    roads = info.get('roads') or []
    clean = []
    point_count = 0
    if not isinstance(roads, list):
        return clean
    for road in roads[:500]:
        if not isinstance(road, dict):
            continue
        status = str(road.get('status', ''))
        if status not in ('1', '2', '3'):
            continue
        raw = road.get('polyline', '')
        if not isinstance(raw, str) or len(raw) > 24000:
            continue
        points = []
        try:
            for pair in raw.split(';')[:800]:
                lng, lat = (float(part) for part in pair.split(','))
                if not (73 <= lng <= 135 and 18 <= lat <= 54):
                    raise ValueError('invalid point')
                points.append([lng, lat])
        except ValueError:
            continue
        if len(points) >= 2:
            if point_count + len(points) > 16000:
                break
            item = {'status': int(status), 'path': points}
            name = road.get('name')
            if isinstance(name, str) and len(name) <= 100:
                item['name'] = name
            try:
                angle = float(road.get('angle'))
                if math.isfinite(angle) and 0 <= angle <= 360:
                    item['angle'] = angle
            except (TypeError, ValueError):
                pass
            clean.append(item)
            point_count += len(points)
    return clean


def add_amap_traffic_route(app):
    @app.post('/api/amap-app/traffic')
    @login_check
    def amap_traffic():
        if request.content_length and request.content_length > 256:
            return json_fail(message='路况请求过大'), 413
        try:
            center = _center((request.get_json(silent=True) or {}).get('center'))
        except (AttributeError, ValueError):
            return json_fail(message='路况位置无效'), 400
        key = os.environ.get('TMC_AMAP_TRAFFIC_KEY') or get_config_by_key('amap_traffic_key')
        if not key:
            return json_fail(message='请先在设置中填写已开通交通态势服务的高德 Web 服务 Key'), 409
        cache_key = center
        now = time.monotonic()
        with _lock:
            cached = _cache.get(cache_key)
            if cached and now - cached[0] < 60:
                return json_ok(cached[1])
        lng, lat = center
        # About 5 x 5 km, safely below AMap's 10 km diagonal limit.
        dx = 2.5 / (111.32 * math.cos(math.radians(lat)))
        dy = 2.5 / 110.57
        rectangle = f'{lng-dx:.6f},{lat-dy:.6f};{lng+dx:.6f},{lat+dy:.6f}'
        try:
            response = requests.get(_URL, params={'key': key, 'rectangle': rectangle, 'level': 5,
                'extensions': 'all', 'output': 'json'}, timeout=(3, 8))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or str(payload.get('status')) != '1':
                return json_fail(message='高德路况服务不可用，请检查 Web 服务 Key 的交通态势权限'), 502
            result = {'roads': _roads(payload), 'updatedAt': int(time.time())}
        except (requests.RequestException, ValueError):
            return json_fail(message='高德路况请求超时或返回异常'), 502
        with _lock:
            if len(_cache) >= 64:
                _cache.pop(next(iter(_cache)))
            _cache[cache_key] = (now, result)
        return json_ok(result)
