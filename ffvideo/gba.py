from flask import abort, request, send_file, Response, stream_with_context
from io import BytesIO
import json
import os
from urllib.parse import quote
import requests

from config import get_config_by_key
from ffvideo.utils import json_ok


DEFAULT_GBA_PATH = './roms/gba'
DEFAULT_GBA_SAVE_PATH = './roms/gba/saves'
DEFAULT_GBA_STATE_PATH = './roms/gba/states'
SUPPORTED_ROM_EXTENSIONS = ('.gba', '.agb', '.bin')
REMOTE_GBA_CATALOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'catalogs', 'gba-js-org.json'))
MAX_GBA_STATE_SLOTS = 5


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


def get_gba_state_root_path():
    prefix = get_config_by_key('gba_state_path', DEFAULT_GBA_STATE_PATH) or DEFAULT_GBA_STATE_PATH
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


def normalize_state_key(save_key: str):
    normalized = ''.join(ch if ch.isalnum() or ch in ['-', '_', '.'] else '_' for ch in (save_key or '').strip())
    if not normalized:
        abort(400)
    return normalized


def get_state_file_path(save_key: str, slot: int):
    if slot < 1 or slot > MAX_GBA_STATE_SLOTS:
        abort(400)
    root_path = get_gba_state_root_path()
    normalized = normalize_state_key(save_key)
    return os.path.join(root_path, f'{normalized}.slot{slot}.state')


def infer_remote_file_size(headers):
    content_range = headers.get('Content-Range') or ''
    if '/' in content_range:
        total = content_range.rsplit('/', 1)[-1].strip()
        if total.isdigit():
            return total

    etag = headers.get('ETag') or headers.get('etag') or ''
    if '-' in etag:
        suffix = etag.rsplit('-', 1)[-1].strip().strip('"')
        try:
            return str(int(suffix, 16))
        except ValueError:
            return None

    content_length = headers.get('Content-Length')
    if content_length and content_length.isdigit():
        return content_length

    return None


def add_gba_route(app):
    @app.route('/api/gba/list', methods=['GET'])
    def gba_list():
        root_path = get_gba_root_path()
        save_root_path = get_gba_save_root_path()
        current_path = request.args.get('path', '')
        abs_path, normalized = safe_join(root_path, current_path)

        if abs_path == save_root_path or abs_path.startswith(f'{save_root_path}{os.sep}'):
            abort(404)

        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            abort(404)

        items = []
        for entry in sorted(os.listdir(abs_path), key=lambda item: item.lower()):
            full_path = os.path.join(abs_path, entry)
            if full_path == save_root_path:
                continue
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

    @app.route('/api/gba/remote/<slug>', methods=['GET', 'HEAD'])
    def gba_remote_file(slug):
        item = get_remote_gba_catalog().get(slug)
        if not item:
            abort(404)

        remote_url = item.get('remoteUrl')
        if not remote_url:
            abort(404)

        upstream_headers = {}
        if request.headers.get('Range'):
            upstream_headers['Range'] = request.headers.get('Range')

        method = request.method.upper()
        requester = requests.head if method == 'HEAD' else requests.get
        response = requester(
            remote_url,
            headers=upstream_headers,
            timeout=60,
            allow_redirects=True,
            stream=method != 'HEAD',
        )

        if response.status_code not in (200, 206):
            abort(response.status_code if response.status_code in (404, 403, 416) else 502)

        accept_ranges = response.headers.get('Accept-Ranges')
        file_size = infer_remote_file_size(response.headers)
        headers = {
            'Content-Type': response.headers.get('Content-Type', 'application/octet-stream'),
            'Content-Disposition': f'attachment; filename="{slug}.gba"',
        }
        if accept_ranges:
            headers['Accept-Ranges'] = accept_ranges
        if response.headers.get('Content-Range'):
            headers['Content-Range'] = response.headers.get('Content-Range')
        if file_size:
            headers['X-File-Size'] = file_size
        if response.status_code == 206 and response.headers.get('Content-Length'):
            headers['Content-Length'] = response.headers.get('Content-Length')
        elif method == 'HEAD' and file_size:
            headers['Content-Length'] = file_size

        if method == 'HEAD':
            response.close()
            return Response(status=response.status_code, headers=headers)

        def generate():
            try:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        yield chunk
            finally:
                response.close()

        return Response(
            stream_with_context(generate()),
            status=response.status_code,
            headers=headers,
        )

    @app.route('/api/gba/saves/<save_key>', methods=['GET'])
    def gba_save_get(save_key):
        save_path = get_save_file_path(save_key)
        if not os.path.exists(save_path) or not os.path.isfile(save_path):
            return Response(status=204)
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

    @app.route('/api/gba/saves/<save_key>', methods=['DELETE'])
    def gba_save_delete(save_key):
        save_path = get_save_file_path(save_key)
        if os.path.exists(save_path) and os.path.isfile(save_path):
            os.remove(save_path)
        return json_ok({
            'path': save_path,
            'deleted': True,
        })

    @app.route('/api/gba/states/<save_key>', methods=['GET'])
    def gba_state_list(save_key):
        normalize_state_key(save_key)
        slots = []
        for slot in range(1, MAX_GBA_STATE_SLOTS + 1):
            state_path = get_state_file_path(save_key, slot)
            exists = os.path.exists(state_path) and os.path.isfile(state_path)
            slots.append({
                'slot': slot,
                'exists': exists,
                'size': os.path.getsize(state_path) if exists else 0,
                'updatedAt': int(os.path.getmtime(state_path) * 1000) if exists else None,
            })
        return json_ok({
            'slots': slots,
            'maxSlots': MAX_GBA_STATE_SLOTS,
        })

    @app.route('/api/gba/states/<save_key>/<int:slot>', methods=['GET'])
    def gba_state_get(save_key, slot):
        state_path = get_state_file_path(save_key, slot)
        if not os.path.exists(state_path) or not os.path.isfile(state_path):
            return Response(status=204)
        return send_file(
            state_path,
            mimetype='application/octet-stream',
            download_name=os.path.basename(state_path),
        )

    @app.route('/api/gba/states/<save_key>/<int:slot>', methods=['PUT'])
    def gba_state_put(save_key, slot):
        state_path = get_state_file_path(save_key, slot)
        data = request.get_data()
        if not data:
            abort(400)
        with open(state_path, 'wb') as wf:
            wf.write(data)
        return json_ok({
            'path': state_path,
            'slot': slot,
            'size': len(data),
        })

    @app.route('/api/gba/states/<save_key>/<int:slot>', methods=['DELETE'])
    def gba_state_delete(save_key, slot):
        state_path = get_state_file_path(save_key, slot)
        if os.path.exists(state_path) and os.path.isfile(state_path):
            os.remove(state_path)
        return json_ok({
            'slot': slot,
            'deleted': True,
        })
