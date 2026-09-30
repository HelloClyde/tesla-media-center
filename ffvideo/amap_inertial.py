"""Authenticated bounded session transport for an installed VDR factory.

AMAP_VDR_FACTORY must construct an engine with consume_batch(samples). No
unverified browser-to-native conversion is enabled by registering this route.
"""
import hashlib
import json
import secrets
import threading
import time
from flask import request, session, current_app
from ffvideo.utils import login_check, json_ok, json_fail


def add_amap_inertial_routes(app):
    entries = {}
    lock = threading.Lock()

    @app.after_request
    def inertial_no_cache(response):
        if request.path.startswith('/api/amap-app/inertial/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def sweep():
        now = time.monotonic()
        for key, entry in list(entries.items()):
            if now-entry['used'] > 120:
                del entries[key]

    def owner():
        if 'vdr_owner' not in session:
            session['vdr_owner'] = secrets.token_hex(24)
        return session['vdr_owner']

    @app.get('/api/amap-app/inertial/status')
    @login_check
    def inertial_status():
        ready = callable(current_app.config.get('AMAP_VDR_FACTORY'))
        return json_ok({'available': ready, 'experimental': True,
                        'reason': None if ready else current_app.config.get(
                            'AMAP_VDR_UNAVAILABLE_REASON', 'input_adapter_not_verified')})

    @app.post('/api/amap-app/inertial/sessions')
    @login_check
    def inertial_create():
        payload = request.get_json(silent=True)
        if payload is not None and not isinstance(payload, dict):
            return json_fail(message='输入协议无效'), 400
        input_format = (payload or {}).get('format', 'native')
        if input_format not in ('native', 'browser'):
            return json_fail(message='输入协议无效'), 400
        factory = current_app.config.get('AMAP_VDR_FACTORY')
        if not callable(factory):
            reason = current_app.config.get('AMAP_VDR_UNAVAILABLE_REASON')
            message = {'profile_missing': '尚未配置惯性引擎的设备参数',
                       'profile_invalid': '惯性引擎配置加载失败，请检查服务日志'}.get(
                           reason, '惯性输入转换尚未验证，导航会话暂未启用')
            return json_fail(message=message), 503
        if not lock.acquire(blocking=False):
            return json_fail(message='定位服务忙，请重试'), 503
        try:
            sweep()
            identity = owner()
            owned = [key for key, entry in entries.items() if entry['owner'] == identity]
            if len(entries) - len(owned) >= 8:
                return json_fail(message='定位会话已满'), 503
            try:
                engine = factory()
                actual_format = getattr(engine, 'input_format', 'native')
                if not isinstance(actual_format, str):
                    actual_format = 'native'
                if actual_format != input_format:
                    return json_fail(message='惯性服务输入协议不匹配'), 409
            except Exception:
                current_app.logger.exception('inertial session initialization failed')
                return json_fail(message='惯性定位初始化失败，请稍后重试'), 503
            # A browser replaces its own old session, avoiding abandoned tabs.
            for key in owned:
                del entries[key]
            key = secrets.token_urlsafe(24)
            entries[key] = dict(owner=identity, engine=engine, used=time.monotonic(),
                                sequence=-1, digest=None, result=None)
            return json_ok({'id': key, 'nextSequence': 0, 'format': actual_format})
        finally:
            lock.release()

    @app.route('/api/amap-app/inertial/sessions/<key>', methods=['POST', 'DELETE'])
    @login_check
    def inertial_session(key):
        if request.content_length is None or request.content_length > 65536:
            if request.method != 'DELETE':
                return json_fail(message='数据批次过大或长度未知'), 413
        if not lock.acquire(blocking=False):
            return json_fail(message='定位服务忙，请重试'), 503
        try:
            sweep()
            entry = entries.get(key)
            if entry is None or entry['owner'] != session.get('vdr_owner'):
                return json_fail(message='定位会话不存在或已过期'), 404
            if request.method == 'DELETE':
                del entries[key]
                return json_ok({'closed': True})
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return json_fail(message='数据批次无效'), 400
            sequence, samples = payload.get('sequence'), payload.get('samples')
            if type(sequence) is not int or sequence < 0 or not isinstance(samples, list) or not 1 <= len(samples) <= 100:
                return json_fail(message='序号或样本数量无效'), 400
            try:
                digest = hashlib.sha256(json.dumps(samples, sort_keys=True, allow_nan=False).encode()).digest()
            except (ValueError, TypeError):
                return json_fail(message='样本格式无效'), 400
            if sequence == entry['sequence'] and digest == entry['digest']:
                entry['used'] = time.monotonic()
                return json_ok(entry['result'])
            if sequence != entry['sequence']+1:
                return json_fail(message='批次顺序冲突，请重新建立会话'), 409
            try:
                result = entry['engine'].consume_batch(samples)
            except ValueError as error:
                # A partially processed batch cannot be retried against stale state.
                del entries[key]
                return json_fail(message=str(error)), 400
            except Exception:
                del entries[key]
                current_app.logger.exception('inertial session processing failed')
                return json_fail(message='惯性定位处理失败，请重新建立会话'), 500
            response = {'sequence': sequence, 'result': result}
            entry.update(sequence=sequence, digest=digest, result=response, used=time.monotonic())
            return json_ok(response)
        finally:
            lock.release()
