"""Last ten selected search places, shared through TMC's persistent data root."""
import json
import threading

from flask import request

from ffvideo.amap_favorites import clean_place, read_places, write_places
from ffvideo.utils import json_fail, json_ok, login_check
from storage import data_path


RECENT_LOCK = threading.Lock()
MAX_RECENT = 10
MAX_REQUEST_BYTES = 8192


def recent_path():
    return data_path('amap', 'recent-places.json')


def add_routes(app):
    @app.route('/api/amap-app/recent-places', methods=['GET', 'POST'])
    @login_check
    def amap_recent_places():
        action = None
        if request.method == 'POST':
            if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
                return json_fail(message='最近搜索请求内容过大'), 413
            raw = request.stream.read(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                return json_fail(message='最近搜索请求内容过大'), 413
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError('最近搜索请求格式不正确')
                action = payload.get('action')
                if action == 'add':
                    place = clean_place(payload.get('place'))
                    # Coordinate searches share a generic UI id; distinct
                    # coordinates must still occupy distinct history entries.
                    if place['id'] == 'coordinate':
                        place['id'] = 'coordinate:' + ','.join(f'{v:.6f}' for v in place['location'])
                elif action != 'clear':
                    raise ValueError('最近搜索操作无效')
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                return json_fail(message='最近搜索地点或操作无效'), 400
        try:
            with RECENT_LOCK:
                places = read_places(recent_path(), MAX_RECENT)
                if action == 'add':
                    places = ([place] + [item for item in places if item['id'] != place['id']])[:MAX_RECENT]
                elif action == 'clear':
                    places = []
                if action is not None:
                    write_places(recent_path(), places)
        except (OSError, ValueError):
            return json_fail(message='读取或保存最近搜索失败，请检查服务器数据目录'), 500
        response = json_ok({'places': places})
        response.headers['Cache-Control'] = 'no-store'
        return response
