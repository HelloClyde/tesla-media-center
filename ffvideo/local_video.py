from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file
from loguru import logger
from ffvideo import utils as futils
from ffvideo.utils import json_ok, json_fail, login_check, confined_path
from config import put_config_by_key, get_config_by_key, get_all_config_safe
import os
from pathlib import Path

def add_local_video_route(app):

    @app.route('/api/video/list', methods=['GET'])
    @login_check
    def video_list():
        prefix = get_config_by_key('video_path')
        path = request.args.get("path", "")
        if path.startswith('/'):
            path = path[1:]
        abs_path = confined_path(prefix, path)
            
        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            abort(404)
        
        files = os.listdir(abs_path)
        files.sort()
        ret = []
        
        for f in files:
            abs_f = os.path.join(abs_path, f)
            if not Path(abs_f).resolve().is_relative_to(Path(prefix).resolve()):
                continue
            if os.path.isdir(abs_f):
                ret.append({
                    'fileType': 'DIR',
                    'fileName': f,
                })
            else:
                if f.endswith('.mp4') or f.endswith('.flv'):
                    ret.append({
                        'fileType': 'FILE',
                        'fileName': f,
                        'url': os.path.normpath(f'/api/video/files/{path}/{f}')
                    })
        
        return json_ok(ret)

    @app.route('/api/video/files/<path:filepath>', methods=['GET'])
    @login_check
    def video_files(filepath):
        prefix = get_config_by_key('video_path')
        abs_path = confined_path(prefix, filepath)
            
        if os.path.exists(abs_path) and os.path.isfile(abs_path):
            return send_file(abs_path)
        else:
            abort(404)
