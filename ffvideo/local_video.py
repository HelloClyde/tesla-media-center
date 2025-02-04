from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file
from loguru import logger
from ffvideo import utils as futils
from ffvideo.utils import json_ok, json_fail
from config import put_config_by_key, get_config_by_key, get_all_config_safe
import os

def add_local_video_route(app):

    @app.route('/api/video/list', methods=['GET'])
    def video_list():
        prefix = get_config_by_key('video_path')
        path = request.args.get("path", "")
        abs_path = os.path.normpath(os.path.join(prefix, path))
        
        # if not abs_path.startswith(prefix):
        #     # 防止目录遍历攻击
        #     abort(403)
            
        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            abort(404)
        
        files = os.listdir(abs_path)
        files.sort()
        ret = []
        
        for f in files:
            abs_f = os.path.join(abs_path, f)
            if os.path.isdir(abs_f):
                ret.append({
                    'fileType': 'DIR',
                    'fileName': f,
                })
            else:
                if f.endswith('.mp4'):
                    ret.append({
                        'fileType': 'FILE',
                        'fileName': f,
                        'url': os.path.normpath(f'/api/video/files/{path}/{f}')
                    })
        
        return json_ok(ret)

    @app.route('/api/video/files/<path:filepath>', methods=['GET'])
    def video_files(filepath):
        prefix = get_config_by_key('video_path')
        abs_path = os.path.normpath(os.path.join(prefix, filepath))
        logger.info(f'play path: {abs_path}')
        
        # if not abs_path.startswith(prefix):
        #     # 防止目录遍历攻击
        #     abort(403)
            
        if os.path.exists(abs_path) and os.path.isfile(abs_path):
            return send_file(abs_path)
        else:
            abort(404)
