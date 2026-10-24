from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file, session
import requests
from bilibili_api import video, Credential, HEADERS, bangumi, sync, homepage, hot, rank, search
from loguru import logger
import imageio_ffmpeg
import subprocess
import threading
from ffvideo import utils as futils
from ffvideo.utils import login_check, confined_path
from config import put_config_by_key, get_config_by_key, get_all_config_safe
import os
from ffvideo import bv, gba, gam4980, local_video, tesla, qqmusic, amap_app, amap_favorites, amap_recent_places, tencent_video, monitor
from ffvideo.tesla_skins import add_tesla_skin_routes
from ffvideo.tesla_appearance import add_routes as add_tesla_appearance_routes
from ffvideo.security import install_security
import time
from cryptography import fernet
import mimetypes
import secrets
import json

app = Flask(__name__)
mimetypes.add_type('model/gltf-binary', '.glb')
mimetypes.add_type('model/gltf+json', '.gltf')
secret_key = get_config_by_key('secret_key', default_value=fernet.Fernet.generate_key().decode('utf-8'))
put_config_by_key('secret_key', secret_key)
app.secret_key = secret_key 
install_security(app)

@app.route('/')
def home():
    return redirect("/index.html")

@app.route('/api/login', methods=['POST'])
def login():
    limiter = app.extensions['login_throttle']
    client = request.remote_addr or 'unknown'
    retry = limiter.retry_after(client)
    if retry:
        response = futils.json_fail('rate_limited', message='登录尝试过于频繁，请稍后重试')
        response.headers['Retry-After'] = str(retry)
        return response, 429
    if request.content_length is not None and request.content_length > 2048:
        return futils.json_fail('invalid_request'), 413
    if not request.is_json:
        return futils.json_fail('invalid_request'), 400
    body = request.stream.read(2049)
    if len(body) > 2048:
        return futils.json_fail('invalid_request'), 413
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        return futils.json_fail('invalid_request'), 400
    if not isinstance(data, dict) or not isinstance(data.get('password'), str):
        return futils.json_fail('invalid_request'), 400
    password = data['password']
    expected = get_config_by_key('password')
    try:
        matches = isinstance(expected, str) and expected and secrets.compare_digest(expected.encode(), password.encode())
    except UnicodeError:
        return futils.json_fail('invalid_request'), 400
    if matches:
        limiter.clear(client)
        session.clear()
        session['last_visit'] = int(time.time())
        return futils.json_ok({})
    limiter.failed(client)
    return futils.json_fail(), 401

# 登出接口
@app.route('/api/logout', methods=['GET'])
def logout():
    monitor.relay.revoke(session.pop('monitor_client', None))
    session.pop('last_visit', None)
    return futils.json_ok({})

@app.route('/api/config', methods=['GET'])
@login_check
def get_config():
    return futils.json_ok(get_all_config_safe())

@app.route('/api/config', methods=['POST'])
@login_check
def update_config():
    data = request.json or {}
    allowed_keys = {
        'amap_key',
        'amap_security_js_code',
        'video_path',
        'home_page_iframe',
        'bilibili_cache_size_mb',
        'bilibili_max_quality',
        'bilibili_danmaku_area',
        'bilibili_danmaku_max_count',
        'bilibili_danmaku_opacity',
        'bilibili_danmaku_font_size',
    }

    if 'bilibili_danmaku_font_size' in data:
        value = data['bilibili_danmaku_font_size']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 12 <= value <= 32 or int(value) != value:
            return jsonify({'status': 'fail', 'message': '弹幕字号须为 12–32 的整数'}), 400
        data['bilibili_danmaku_font_size'] = int(value)

    updated = {}
    for key, value in data.items():
        if key not in allowed_keys:
            continue
        put_config_by_key(key, value)
        updated[key] = value

    return futils.json_ok({
        'updated': updated,
        'config': get_all_config_safe(),
    })

@app.route('/<path:name>')
def static_web(name):
    # 排除以api开头的路径
    if name.startswith('api'):
        abort(404)
        
    logger.info(f'static file request:{name}')
    
    web_root = os.path.join(app.root_path, 'web', 'dist')
    fpath = str(confined_path(web_root, name))
    if os.path.exists(fpath):
        accept_encoding = request.headers.get('Accept-Encoding', '')
        preferred_suffix = None
        if 'br' in accept_encoding and os.path.exists(f'{fpath}.br'):
            preferred_suffix = '.br'
        elif 'gzip' in accept_encoding and os.path.exists(f'{fpath}.gz'):
            preferred_suffix = '.gz'

        if preferred_suffix:
            mimetype, _ = mimetypes.guess_type(fpath)
            compressed = confined_path(web_root, name + preferred_suffix)
            response = send_file(compressed, mimetype=mimetype or 'application/octet-stream')
            response.headers['Content-Encoding'] = 'br' if preferred_suffix == '.br' else 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
            # The HTML chooses the hashed app bundle and versioned player workers.
            # Revalidate it so a deployment cannot keep selecting an older player.
            response.headers['Cache-Control'] = 'no-cache' if name == 'index.html' else 'public, max-age=86400'
            return response

        return send_from_directory(web_root, name)
    else:
        return abort(404)

if __name__ == '__main__':
    # 运行Flask应用，并启用多线程支持
    local_video.add_local_video_route(app)
    monitor.add_routes(app)
    gba.add_gba_route(app)
    gam4980.add_gam4980_route(app)
    bv.add_bv_route(app)
    tencent_video.add_routes(app)
    from ffvideo import douyin
    douyin.add_routes(app)
    qqmusic.add_qqmusic_route(app)
    amap_app.add_amap_app_route(app)
    amap_favorites.add_routes(app)
    amap_recent_places.add_routes(app)
    from ffvideo.amap_map import add_amap_map_route
    add_amap_map_route(app)
    tesla.add_tesla_route(app)
    add_tesla_skin_routes(app)
    add_tesla_appearance_routes(app)
    tesla.start_tesla_background_sync()
    app.run(host='0.0.0.0', threaded=True, port=8080)
