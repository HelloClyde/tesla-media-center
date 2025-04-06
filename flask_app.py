from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file, session
import requests
from bilibili_api import video, Credential, HEADERS, bangumi, sync, homepage, hot, rank, search
from loguru import logger
import imageio_ffmpeg
import subprocess
import threading
from ffvideo import utils as futils
from ffvideo.utils import login_check
from config import put_config_by_key, get_config_by_key, get_all_config_safe
import os
from ffvideo import bv, local_video
import time
from cryptography import fernet

app = Flask(__name__)
secret_key = get_config_by_key('secret_key', default_value=fernet.Fernet.generate_key().decode('utf-8'))
put_config_by_key('secret_key', secret_key)
app.secret_key = secret_key 

@app.route('/')
def home():
    return redirect("/index.html")

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    password = data.get('password')
    if get_config_by_key('password') == password:
        session['last_visit'] = int(time.time())
        return futils.json_ok({})
    return futils.json_fail(), 401

# 登出接口
@app.route('/api/logout', methods=['GET'])
def logout():
    session.pop('last_visit', None)
    return futils.json_ok({})

@app.route('/api/config', methods=['GET'])
@login_check
def get_config():
    return futils.json_ok(get_all_config_safe())

@app.route('/<path:name>')
def static_web(name):
    # 排除以api开头的路径
    if name.startswith('api'):
        abort(404)
        
    logger.info(f'static file request:{name}')
    
    fpath = os.path.join('./web/dist', name)
    if os.path.exists(fpath):
        return send_from_directory('./web/dist', name)
    else:
        return abort(404)

if __name__ == '__main__':
    # 运行Flask应用，并启用多线程支持
    local_video.add_local_video_route(app)
    bv.add_bv_route(app)
    app.run(host='0.0.0.0', threaded=True, port=8080)