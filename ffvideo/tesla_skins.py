"""Authenticated, per-model vehicle UV skins in TMC's persistent data directory."""

import os
import tempfile
import threading
from pathlib import Path

from flask import Response, request

from ffvideo.utils import json_fail, json_ok, login_check
from storage import data_path


SKIN_VARIANTS = frozenset({
    'model3-high', 'model3-highland', 'modely-high', 'modely-juniper',
    'modely-standard', 'modely-long', 'models-legacy', 'models-palladium',
    'modelx-legacy', 'modelx-palladium', 'cybertruck', 'semi',
})
SKIN_TYPES = {'png': 'image/png', 'jpg': 'image/jpeg', 'webp': 'image/webp'}
MAX_SKIN_BYTES = 10 * 1024 * 1024
_skin_write_lock = threading.Lock()


def skin_root():
    root = data_path('tesla/skins')
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dimensions(data):
    """Read only enough of PNG/JPEG/WebP headers to bound uploaded images."""
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24 and data[12:16] == b'IHDR':
        if not data.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82'):
            return None
        return 'png', int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 0xff:
                break
            while pos < len(data) and data[pos] == 0xff:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in (0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
                continue
            if pos + 2 > len(data):
                break
            length = int.from_bytes(data[pos:pos + 2], 'big')
            if length < 2 or pos + length > len(data):
                break
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf) and length >= 7:
                return 'jpg', int.from_bytes(data[pos + 5:pos + 7], 'big'), int.from_bytes(data[pos + 3:pos + 5], 'big')
            pos += length
    if len(data) >= 30 and data[:4] == b'RIFF' and data[8:12] == b'WEBP' and int.from_bytes(data[4:8], 'little') + 8 == len(data):
        chunk = data[12:16]
        if chunk == b'VP8X':
            return 'webp', 1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little')
        if chunk == b'VP8L' and len(data) >= 25 and data[20] == 0x2f:
            bits = int.from_bytes(data[21:25], 'little')
            return 'webp', 1 + (bits & 0x3fff), 1 + ((bits >> 14) & 0x3fff)
        if chunk == b'VP8 ' and len(data) >= 30 and data[23:26] == b'\x9d\x01\x2a':
            return 'webp', int.from_bytes(data[26:28], 'little') & 0x3fff, int.from_bytes(data[28:30], 'little') & 0x3fff
    return None


def _skin_files(root, variant):
    return [root / f'{variant}.{extension}' for extension in SKIN_TYPES]


def add_tesla_skin_routes(app):
    @app.route('/api/tesla/skins/<variant>', methods=['GET', 'PUT', 'DELETE'])
    @login_check
    def tesla_skin(variant):
        if variant not in SKIN_VARIANTS:
            return json_fail(message='不支持的车型'), 400
        root = skin_root()
        files = _skin_files(root, variant)
        if request.method == 'GET':
            for path in files:
                if path.is_file():
                    try:
                        image = path.read_bytes()
                    except OSError:
                        return json_fail(message='无法读取服务器上的皮肤'), 500
                    response = Response(image, mimetype=SKIN_TYPES[path.suffix[1:]])
                    response.headers['Cache-Control'] = 'no-store'
                    response.headers['X-Content-Type-Options'] = 'nosniff'
                    return response
            return json_fail('not_found', message='该车型尚未上传皮肤'), 404
        if request.method == 'DELETE':
            try:
                with _skin_write_lock:
                    for path in files:
                        path.unlink(missing_ok=True)
            except OSError:
                return json_fail(message='无法删除服务器上的皮肤'), 500
            return json_ok({'variant': variant, 'uploaded': False})
        if request.content_length is not None and not 0 < request.content_length <= MAX_SKIN_BYTES:
            return json_fail(message='皮肤文件不能超过 10 MB'), 413
        data = request.stream.read(MAX_SKIN_BYTES + 1)
        if not data or len(data) > MAX_SKIN_BYTES:
            return json_fail(message='皮肤文件不能超过 10 MB'), 413
        details = _dimensions(data)
        if not details:
            return json_fail(message='仅支持有效的 PNG、JPEG 或 WebP 图片'), 400
        extension, width, height = details
        if width != height or not 512 <= width <= 4096:
            return json_fail(message='皮肤须为 512–4096 像素的正方形 UV 贴图'), 400
        target = root / f'{variant}.{extension}'
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            with _skin_write_lock:
                if request.headers.get('If-None-Match') == '*' and any(path.is_file() for path in files):
                    return json_fail('already_exists', message='该车型已有服务器皮肤'), 412
                os.replace(temporary, target)
                for path in files:
                    if path != target:
                        path.unlink(missing_ok=True)
        except OSError:
            return json_fail(message='皮肤保存失败，请检查服务器磁盘空间和目录权限'), 500
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return json_ok({'variant': variant, 'uploaded': True, 'size': len(data)})
