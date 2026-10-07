"""Shared, authenticated AMap place favorites under TMC's persistent data root."""
import json
import math
import os
from pathlib import Path
import tempfile
import threading

from flask import request

from ffvideo.utils import json_fail, json_ok, login_check
from storage import data_path


FAVORITES_LOCK = threading.Lock()
MAX_FAVORITES = 100
MAX_REQUEST_BYTES = 64 * 1024
MAX_FILE_BYTES = 128 * 1024


def favorites_path():
    return data_path('amap', 'favorites.json')


def valid_point(value):
    return (isinstance(value, list) and len(value) == 2
            and all(type(coordinate) in (int, float) and math.isfinite(coordinate)
                    for coordinate in value)
            and abs(value[0]) <= 180 and abs(value[1]) <= 85)


def clean_place(value):
    if not isinstance(value, dict):
        raise ValueError('收藏地点格式不正确')
    place_id, name, address = value.get('id'), value.get('name'), value.get('address', '')
    if (not isinstance(place_id, str) or not 0 < len(place_id.strip()) <= 128
            or not isinstance(name, str) or not 0 < len(name.strip()) <= 160
            or not isinstance(address, str) or len(address) > 300
            or not valid_point(value.get('location'))):
        raise ValueError('收藏地点信息不完整或坐标无效')
    cleaned = {'id': place_id.strip(), 'name': name.strip(),
               'address': address.strip(), 'location': value['location']}
    if 'entrance' in value:
        if not valid_point(value['entrance']):
            raise ValueError('收藏地点入口坐标无效')
        cleaned['entrance'] = value['entrance']
    return cleaned


def read_favorites():
    return read_places(favorites_path(), MAX_FAVORITES)


def read_places(target, maximum):
    if not target.exists():
        return []
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('收藏文件大小异常')
    stored = json.loads(target.read_text(encoding='utf-8'))
    if (not isinstance(stored, dict) or not isinstance(stored.get('places'), list)
            or len(stored['places']) > maximum):
        raise ValueError('收藏文件格式异常')
    places = [clean_place(place) for place in stored['places']]
    if len({place['id'] for place in places}) != len(places):
        raise ValueError('收藏文件含重复地点')
    return places


def write_favorites(places):
    write_places(favorites_path(), places)


def write_places(target, places):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                         delete=False) as output:
            temporary = Path(output.name)
            json.dump({'places': places}, output, ensure_ascii=False, separators=(',', ':'))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def add_routes(app):
    @app.route('/api/amap-app/favorites', methods=['GET', 'POST'])
    @login_check
    def amap_favorites():
        if request.method == 'POST':
            if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
                return json_fail(message='收藏请求内容过大'), 413
            raw = request.stream.read(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                return json_fail(message='收藏请求内容过大'), 413
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('收藏请求格式不正确')
                action = payload.get('action')
                if action == 'add':
                    place = clean_place(payload.get('place'))
                elif action == 'remove':
                    place_id = payload.get('id')
                    if not isinstance(place_id, str) or not 0 < len(place_id) <= 128:
                        raise ValueError('收藏地点 ID 无效')
                elif action == 'import':
                    raw_places = payload.get('places')
                    if not isinstance(raw_places, list) or len(raw_places) > MAX_FAVORITES:
                        raise ValueError('导入收藏数量无效')
                    imported = [clean_place(item) for item in raw_places]
                else:
                    raise ValueError('收藏操作无效')
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                return json_fail(message=str(error)), 400
        else:
            action = None

        try:
            with FAVORITES_LOCK:
                places = read_favorites()
                if action == 'add':
                    if len(places) >= MAX_FAVORITES and all(item['id'] != place['id'] for item in places):
                        return json_fail(message='收藏地点已满，请先取消一个收藏'), 409
                    places = [place] + [item for item in places if item['id'] != place['id']]
                elif action == 'remove':
                    places = [item for item in places if item['id'] != place_id]
                elif action == 'import':
                    known = {item['id'] for item in places}
                    if len(known | {item['id'] for item in imported}) > MAX_FAVORITES:
                        return json_fail(message='收藏地点已满，浏览器旧收藏尚未迁移，请先整理服务器收藏'), 409
                    for item in imported:
                        if item['id'] not in known:
                            places.append(item)
                            known.add(item['id'])
                if action is not None:
                    write_favorites(places)
        except (OSError, ValueError, json.JSONDecodeError):
            return json_fail(message='读取或保存收藏失败，请检查服务器数据目录'), 500
        response = json_ok({'places': places})
        response.headers['Cache-Control'] = 'no-store'
        return response
