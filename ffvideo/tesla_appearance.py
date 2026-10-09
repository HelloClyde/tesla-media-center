"""Server-backed Tesla appearance preferences, scoped to a linked VIN."""

import json
import os
import re
import tempfile
import threading
from pathlib import Path

from flask import request

from ffvideo.tesla_skins import SKIN_VARIANTS
from ffvideo.utils import json_fail, json_ok, login_check
from storage import data_path


_lock = threading.Lock()
_vin_pattern = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')
_color_pattern = re.compile(r'^#[0-9a-fA-F]{6}$')
_finishes = frozenset({'gloss', 'metallic', 'matte', 'satin'})
_plate_styles = frozenset({'green', 'blue', 'black', 'white'})
_max_file_bytes = 64 * 1024


def appearance_path():
    return data_path('tesla', 'appearance.json')


def _linked(vin):
    from ffvideo.tesla import cached_vehicles
    return any(vehicle.get('vin') == vin for vehicle in cached_vehicles())


def _read():
    path = appearance_path()
    if not path.exists():
        return {'selectedVin': '', 'vehicles': {}, 'scene': None}
    if path.stat().st_size > _max_file_bytes:
        raise ValueError('车辆外观文件过大')
    saved = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(saved, dict) or not isinstance(saved.get('vehicles'), dict):
        raise ValueError('车辆外观文件格式无效')
    return saved


def _write(saved):
    target = appearance_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(saved, output, ensure_ascii=False, separators=(',', ':'))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _clean_record(payload):
    if not isinstance(payload, dict) or set(payload) != {'appearance', 'manualModel'}:
        raise ValueError('车辆外观请求格式不正确')
    appearance = payload['appearance']
    if not isinstance(appearance, dict) or set(appearance) != {'color', 'finish', 'plate', 'plateStyle'}:
        raise ValueError('车辆外观参数不完整')
    color, finish = appearance['color'], appearance['finish']
    plate, plate_style = appearance['plate'], appearance['plateStyle']
    if (not isinstance(color, str) or not _color_pattern.fullmatch(color)
            or finish not in _finishes or plate_style not in _plate_styles
            or not isinstance(plate, str) or not 1 <= len(plate) <= 10
            or any(ord(char) < 32 or ord(char) == 127 for char in plate)):
        raise ValueError('车色、材质或牌照设置无效')
    manual = payload['manualModel']
    if manual is not None and manual not in SKIN_VARIANTS:
        raise ValueError('手动选择的车型无效')
    return {'appearance': {'color': color.lower(), 'finish': finish, 'plate': plate,
                           'plateStyle': plate_style}, 'manualModel': manual}


def _body():
    if request.content_length is not None and request.content_length > 4096:
        raise ValueError('车辆外观请求过大')
    raw = request.stream.read(4097)
    if len(raw) > 4096:
        raise ValueError('车辆外观请求过大')
    return json.loads(raw)


def add_routes(app):
    @app.route('/api/tesla/appearance/scene', methods=['GET', 'PUT'])
    @login_check
    def tesla_appearance_scene():
        if request.method == 'PUT':
            try:
                scene = _body()
                if (not isinstance(scene, dict) or set(scene) != {'weatherMode', 'sceneNight'}
                        or scene['weatherMode'] not in {'auto', 'clear', 'cloudy', 'rain', 'fog', 'snow'}
                        or type(scene['sceneNight']) is not bool):
                    raise ValueError('场景设置无效')
                with _lock:
                    saved = _read()
                    if request.headers.get('If-None-Match') == '*' and saved.get('scene') is not None:
                        return json_fail('already_exists', message='服务器已有场景设置'), 412
                    saved['scene'] = scene
                    _write(saved)
            except (ValueError, TypeError, json.JSONDecodeError):
                return json_fail(message='场景设置参数无效'), 400
            except OSError:
                return json_fail(message='场景设置保存失败'), 500
            return json_ok(scene)
        try:
            scene = _read().get('scene')
        except (OSError, ValueError, json.JSONDecodeError):
            return json_fail(message='无法读取服务器上的场景设置'), 500
        if scene is None:
            return '', 204
        response = json_ok(scene)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/api/tesla/appearance/selection', methods=['GET', 'PUT'])
    @login_check
    def tesla_appearance_selection():
        if request.method == 'PUT':
            try:
                body = _body()
                vin = body.get('selectedVin') if isinstance(body, dict) else None
                if not isinstance(vin, str) or not _vin_pattern.fullmatch(vin) or not _linked(vin):
                    return json_fail(message='车辆未关联到当前 Tesla 账号'), 400
                with _lock:
                    saved = _read()
                    if request.headers.get('If-None-Match') == '*' and saved.get('selectedVin'):
                        return json_fail('already_exists', message='服务器已经保存车辆选择'), 412
                    saved['selectedVin'] = vin
                    _write(saved)
            except (ValueError, TypeError, json.JSONDecodeError):
                return json_fail(message='车辆选择请求无效'), 400
            except OSError:
                return json_fail(message='车辆选择保存失败'), 500
            return json_ok({'selectedVin': vin})
        try:
            selected = _read().get('selectedVin', '')
        except (OSError, ValueError, json.JSONDecodeError):
            return json_fail(message='无法读取服务器上的车辆选择'), 500
        response = json_ok({'selectedVin': selected if isinstance(selected, str) else ''})
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/api/tesla/appearance/<vin>', methods=['GET', 'PUT'])
    @login_check
    def tesla_appearance(vin):
        vin = vin.upper()
        if vin != 'DEFAULT' and (not _vin_pattern.fullmatch(vin) or not _linked(vin)):
            return json_fail(message='车辆未关联到当前 Tesla 账号'), 404
        if request.method == 'PUT':
            try:
                record = _clean_record(_body())
                with _lock:
                    saved = _read()
                    if request.headers.get('If-None-Match') == '*' and vin in saved['vehicles']:
                        return json_fail('already_exists', message='服务器已有车辆外观设置'), 412
                    saved['vehicles'][vin] = record
                    _write(saved)
            except (ValueError, TypeError, json.JSONDecodeError):
                return json_fail(message='车辆外观参数无效'), 400
            except OSError:
                return json_fail(message='车辆外观保存失败'), 500
            return json_ok(record)
        try:
            record = _read()['vehicles'].get(vin)
        except (OSError, ValueError, json.JSONDecodeError):
            return json_fail(message='无法读取服务器上的车辆外观'), 500
        if record is None:
            return '', 204
        response = json_ok(record)
        response.headers['Cache-Control'] = 'no-store'
        return response
