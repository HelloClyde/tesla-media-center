from pathlib import Path
import os
import re
import tempfile
from urllib.parse import quote
from flask import abort, request, send_file
from ffvideo.utils import json_fail

from storage import data_path
DEFAULT_GAME_ROOT = data_path('gam4980')
DEFAULT_SAVE_ROOT = data_path('gam4980/saves')
from ffvideo.utils import json_ok, login_check


def game_root():
    root = DEFAULT_GAME_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_game_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        abort(403)
    return path


def add_gam4980_route(app):
    @app.route('/api/gam4980/saves/<key>', methods=['GET', 'PUT'])
    @login_check
    def gam4980_save(key):
        if not re.fullmatch(r'(?:[a-f0-9]{64}|[0-9]{1,8}-[0-9]{1,10}-[0-9]{1,10})', key):
            abort(400)
        root = DEFAULT_SAVE_ROOT.resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = resolve_game_path(root, key + '.sav')
        if request.method == 'GET':
            if not target.is_file():
                abort(404)
            response = send_file(target, mimetype='application/octet-stream')
            response.headers['Cache-Control'] = 'no-store'
            return response
        if request.content_length is not None and request.content_length != 0x14000:
            return json_fail(message='存档必须为 80 KB'), 413
        data = request.stream.read(0x14001)
        if len(data) != 0x14000:
            return json_fail(message='存档必须为 80 KB'), 413
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except OSError:
            return json_fail(message='服务端存档失败，请检查磁盘空间和目录权限'), 500
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return json_ok({'size': len(data)})

    @app.post('/api/gam4980/upload')
    @login_check
    def gam4980_upload():
        name = request.args.get('name', '').strip()
        if (not name or len(name) > 180 or any(c in name for c in '/\\:*?"<>|')
                or any(ord(c) < 32 for c in name) or not name.lower().endswith('.gam')):
            return json_fail(message='请选择有效的 .gam 文件'), 400
        limit = 0x1e0000
        if request.content_length is not None and not 0x46 <= request.content_length <= limit:
            return json_fail(message='游戏大小须为 70 字节至 1.875 MB'), 413
        data = request.stream.read(limit + 1)
        if not 0x46 <= len(data) <= limit:
            return json_fail(message='游戏大小须为 70 字节至 1.875 MB'), 413
        target = game_root() / name
        try:
            with target.open('xb') as output:
                try:
                    output.write(data)
                except OSError:
                    target.unlink(missing_ok=True)
                    raise
        except FileExistsError:
            return json_fail(message='同名游戏已存在，请重命名后上传'), 409
        except OSError:
            return json_fail(message='无法保存游戏，请检查目录写入权限及磁盘空间'), 500
        return json_ok(dict(name=name, size=len(data)))

    @app.get('/api/gam4980/list')
    @login_check
    def gam4980_list():
        root = game_root()
        folder = resolve_game_path(root, request.args.get('path', ''))
        if not folder.is_dir():
            abort(404)
        items = []
        for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
            target = entry.resolve()
            if not target.is_relative_to(root):
                continue
            path = entry.relative_to(root).as_posix()
            if entry.is_dir():
                items.append(dict(type='dir', name=entry.name, path=path))
            elif entry.is_file() and entry.suffix.lower() == '.gam':
                size = entry.stat().st_size
                items.append(dict(type='file', name=entry.name, path=path, size=size,
                                  playable=0x46 <= size <= 0x1e0000,
                                  url='/api/gam4980/files/' + quote(path, safe='/')))
        return json_ok(dict(rootPath=str(root), path='' if folder == root else folder.relative_to(root).as_posix(), items=items))

    @app.get('/api/gam4980/files/<path:filepath>')
    @login_check
    def gam4980_file(filepath):
        path = resolve_game_path(game_root(), filepath)
        if not path.is_file() or path.suffix.lower() != '.gam':
            abort(404)
        if not 0x46 <= path.stat().st_size <= 0x1e0000:
            abort(413)
        return send_file(path, mimetype='application/octet-stream', conditional=True)
