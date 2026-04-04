from flask import abort, request, send_file
import os
from urllib.parse import quote

from config import get_config_by_key
from ffvideo.utils import json_ok


DEFAULT_GBA_PATH = './roms/gba'
SUPPORTED_ROM_EXTENSIONS = ('.gba', '.agb', '.bin')


def get_gba_root_path():
    prefix = get_config_by_key('gba_path', DEFAULT_GBA_PATH) or DEFAULT_GBA_PATH
    prefix = os.path.abspath(prefix)
    os.makedirs(prefix, exist_ok=True)
    return prefix


def safe_join(root_path: str, current_path: str):
    normalized = (current_path or '').lstrip('/')
    abs_path = os.path.abspath(os.path.join(root_path, normalized))
    if abs_path != root_path and not abs_path.startswith(f'{root_path}{os.sep}'):
        abort(403)
    return abs_path, normalized


def add_gba_route(app):
    @app.route('/api/gba/list', methods=['GET'])
    def gba_list():
        root_path = get_gba_root_path()
        current_path = request.args.get('path', '')
        abs_path, normalized = safe_join(root_path, current_path)

        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            abort(404)

        items = []
        for entry in sorted(os.listdir(abs_path), key=lambda item: item.lower()):
            full_path = os.path.join(abs_path, entry)
            rel_path = os.path.normpath(os.path.join(normalized, entry))
            if os.path.isdir(full_path):
                items.append({
                    'type': 'dir',
                    'name': entry,
                    'path': '' if rel_path == '.' else rel_path.replace('\\', '/'),
                })
                continue

            if not entry.lower().endswith(SUPPORTED_ROM_EXTENSIONS):
                continue

            items.append({
                'type': 'file',
                'name': entry,
                'path': '' if rel_path == '.' else rel_path.replace('\\', '/'),
                'size': os.path.getsize(full_path),
                'url': f"/api/gba/files/{quote('' if rel_path == '.' else rel_path.replace('\\', '/'), safe='/')}",
            })

        return json_ok({
            'rootPath': root_path,
            'path': normalized.replace('\\', '/'),
            'items': items,
        })

    @app.route('/api/gba/files/<path:filepath>', methods=['GET'])
    def gba_files(filepath):
        root_path = get_gba_root_path()
        abs_path, _ = safe_join(root_path, filepath)
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            abort(404)
        return send_file(abs_path)
