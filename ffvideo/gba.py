from flask import abort, request, send_file
from io import BytesIO
import json
import os
from urllib.parse import quote
import requests

from config import get_config_by_key
from ffvideo.utils import json_ok


DEFAULT_GBA_PATH = './roms/gba'
DEFAULT_GBA_SAVE_PATH = './roms/gba/saves'
SUPPORTED_ROM_EXTENSIONS = ('.gba', '.agb', '.bin')
REMOTE_GBA_CATALOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'catalogs', 'gba-js-org.json'))


def get_gba_root_path():
    prefix = get_config_by_key('gba_path', DEFAULT_GBA_PATH) or DEFAULT_GBA_PATH
    prefix = os.path.abspath(prefix)
    os.makedirs(prefix, exist_ok=True)
    return prefix


def get_gba_save_root_path():
    prefix = get_config_by_key('gba_save_path', DEFAULT_GBA_SAVE_PATH) or DEFAULT_GBA_SAVE_PATH
    prefix = os.path.abspath(prefix)
    os.makedirs(prefix, exist_ok=True)
    return prefix


def safe_join(root_path: str, current_path: str):
    normalized = (current_path or '').lstrip('/')
    abs_path = os.path.abspath(os.path.join(root_path, normalized))
    if abs_path != root_path and not abs_path.startswith(f'{root_path}{os.sep}'):
        abort(403)
    return abs_path, normalized


def get_remote_gba_catalog():
    if not os.path.exists(REMOTE_GBA_CATALOG_PATH):
        return {}
    with open(REMOTE_GBA_CATALOG_PATH, 'r', encoding='utf-8') as rf:
        data = json.load(rf)
    items = data.get('items', []) if isinstance(data, dict) else []
    return {item.get('id'): item for item in items if item.get('id')}


def get_save_file_path(save_key: str):
    normalized = ''.join(ch if ch.isalnum() or ch in ['-', '_', '.'] else '_' for ch in (save_key or '').strip())
    if not normalized:
        abort(400)
    root_path = get_gba_save_root_path()
    return os.path.join(root_path, f'{normalized}.sav')


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
            normalized_rel_path = '' if rel_path == '.' else rel_path.replace('\\', '/')
            if os.path.isdir(full_path):
                items.append({
                    'type': 'dir',
                    'name': entry,
                    'path': normalized_rel_path,
                })
                continue

            if not entry.lower().endswith(SUPPORTED_ROM_EXTENSIONS):
                continue

            items.append({
                'type': 'file',
                'name': entry,
                'path': normalized_rel_path,
                'size': os.path.getsize(full_path),
                'url': f"/api/gba/files/{quote(normalized_rel_path, safe='/')}",
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

    @app.route('/api/gba/remote/<slug>', methods=['GET'])
    def gba_remote_file(slug):
        item = get_remote_gba_catalog().get(slug)
        if not item:
            abort(404)

        remote_url = item.get('remoteUrl')
        if not remote_url:
            abort(404)

        response = requests.get(remote_url, timeout=60)
        if response.status_code != 200:
            abort(response.status_code if response.status_code in (404, 403) else 502)

        return send_file(
            BytesIO(response.content),
            mimetype='application/octet-stream',
            download_name=f'{slug}.gba'
        )

    @app.route('/api/gba/saves/<save_key>', methods=['GET'])
    def gba_save_get(save_key):
        save_path = get_save_file_path(save_key)
        if not os.path.exists(save_path) or not os.path.isfile(save_path):
            abort(404)
        return send_file(save_path, mimetype='application/octet-stream', download_name=os.path.basename(save_path))

    @app.route('/api/gba/saves/<save_key>', methods=['PUT'])
    def gba_save_put(save_key):
        save_path = get_save_file_path(save_key)
        data = request.get_data()
        if not data:
            abort(400)
        with open(save_path, 'wb') as wf:
            wf.write(data)
        return json_ok({
            'path': save_path,
            'size': len(data),
        })
