"""QQ Music adapter. Credentials never leave the server or enter config responses."""
import asyncio
import base64
import hashlib
import re
import secrets
import threading
import time
from functools import wraps
from pathlib import Path
from urllib.parse import urljoin, urlparse

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, request, session
from qqmusic_api import Client, Credential
from qqmusic_api.models.login import QRLoginType
from qqmusic_api.modules.song import SongFileInfo, SongFileType
from ffvideo.utils import json_ok, json_fail, login_check

STORE = Path(__file__).resolve().parent.parent / '.qqmusic'
LOCK = threading.RLock()
PENDING = {}
QUALITIES = {
    'standard': (SongFileType.MP3_128, 'size_128mp3', '标准 128 kbps'),
    'high': (SongFileType.MP3_320, 'size_320mp3', '高品质 320 kbps'),
    'lossless': (SongFileType.FLAC, 'size_flac', '无损 FLAC'),
}


class InputError(ValueError):
    """Only locally validated, safe messages may be returned to the browser."""


def identity():
    sid = session.get('qqmusic_session', '')
    if not re.fullmatch(r'[a-f0-9]{48}', sid):
        sid = secrets.token_hex(24)
        session['qqmusic_session'] = sid
    STORE.mkdir(mode=0o700, exist_ok=True)
    return sid


def cipher():
    key = hashlib.sha256(str(current_app.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def credential(sid):
    try:
        value = Credential.model_validate_json(cipher().decrypt((STORE / sid).read_bytes()))
        if not value.is_expired():
            return value
    except (FileNotFoundError, InvalidToken, ValueError):
        pass
    return None


def run(sid, operation):
    cred = credential(sid)
    async def invoke():
        async with Client(credential=cred, device_path=str(STORE / (sid + '.device'))) as client:
            return await asyncio.wait_for(operation(client), timeout=25)
    return asyncio.run(invoke())


def endpoint(func):
    @wraps(func)
    @login_check
    def wrapped(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
        except InputError as exc:
            response = json_fail(message=str(exc)), 400
        except Exception:
            # Upstream exception strings can contain login tokens and signed URLs.
            response = json_fail(message='QQ 音乐服务暂时不可用，请稍后重试；登录失效时请重新扫码'), 502
        response = current_app.make_response(response)
        response.headers['Cache-Control'] = 'no-store'
        return response
    return wrapped


def add_qqmusic_route(app):
    @app.get('/api/qqmusic/account')
    @endpoint
    def qq_account():
        cred = credential(identity())
        return json_ok({'loggedIn': bool(cred), 'account': str(cred.musicid) if cred else ''})

    @app.post('/api/qqmusic/logout')
    @endpoint
    def qq_logout():
        sid = identity()
        with LOCK:
            PENDING.pop(sid, None)
            (STORE / sid).unlink(missing_ok=True)
        return json_ok({})

    @app.post('/api/qqmusic/login')
    @endpoint
    def qq_login():
        sid = identity()
        qr = run(sid, lambda c: c.login.get_qrcode(QRLoginType.QQ))
        token = secrets.token_hex(16)
        with LOCK:
            for key in list(PENDING):
                if PENDING[key]['expires'] < time.time():
                    del PENDING[key]
            PENDING[sid] = {'qr': qr, 'expires': time.time() + 180, 'token': token}
        return json_ok({'token': token, 'image': 'data:' + qr.mimetype + ';base64,' + base64.b64encode(qr.data).decode()})

    @app.post('/api/qqmusic/login/status')
    @endpoint
    def qq_login_status():
        sid = identity()
        token = (request.get_json(silent=True) or {}).get('token')
        with LOCK:
            pending = PENDING.get(sid)
            if not pending or pending['token'] != token or pending['expires'] < time.time():
                return json_ok({'state': 'TIMEOUT'})
        result = run(sid, lambda c: c.login.check_qrcode(pending['qr']))
        with LOCK:
            if PENDING.get(sid) is not pending:
                return json_ok({'state': 'TIMEOUT'})
            if result.event.name == 'DONE' and result.credential:
                path = STORE / sid
                temporary = STORE / (sid + '.tmp')
                temporary.write_bytes(cipher().encrypt(result.credential.model_dump_json().encode()))
                temporary.chmod(0o600)
                temporary.replace(path)
            if result.event.name in ('DONE', 'TIMEOUT', 'REFUSE'):
                PENDING.pop(sid, None)
        return json_ok({'state': result.event.name})

    @app.get('/api/qqmusic/search')
    @endpoint
    def qq_search():
        query = request.args.get('q', '').strip()
        page = request.args.get('page', '1')
        if not query or len(query) > 100 or not page.isdigit() or not 1 <= int(page) <= 100:
            raise InputError('请输入 1–100 字的关键词，页码须为 1–100')
        result = run(identity(), lambda c: c.search.search_by_type(query, num=20, page=int(page), highlight=False))
        return json_ok({'songs': [{'mid': s.mid, 'title': s.title or s.name,
                                  'singer': ' / '.join(x.name for x in s.singer),
                                  'album': s.album.title, 'cover': s.album.cover_url(),
                                  'duration': s.interval} for s in result.song],
                        'more': result.nextpage > int(page)})

    @app.get('/api/qqmusic/play')
    @endpoint
    def qq_play():
        mid = request.args.get('mid', '')
        quality = request.args.get('quality', 'standard')
        if quality not in QUALITIES:
            raise InputError('不支持的音质')
        file_type, size_field, label = QUALITIES[quality]
        if not re.fullmatch(r'[a-zA-Z0-9]{1,32}', mid):
            raise InputError('歌曲标识无效')
        async def resolve(client):
            detail = await client.song.get_detail(mid)
            if not getattr(detail.track.file, size_field, 0):
                raise InputError(f'此歌曲没有{label}音源，请选择其他音质')
            urls = await client.song.get_song_urls([SongFileInfo(mid=mid, media_mid=detail.track.file.media_mid or None)], file_type=file_type)
            if not urls.data or not urls.data[0].purl:
                return None
            cdn = await client.song.get_cdn_dispatch()
            roots = sorted(set(x for x in cdn.sip if x.startswith('https://')), key=lambda x: '.stream.qqmusic.qq.com' not in x)
            playable = []
            for root in roots:
                url = urljoin(root, urls.data[0].purl)
                host = urlparse(url).hostname or ''
                if urlparse(url).scheme == 'https' and (host.endswith('.qq.com') or host.endswith('.qqmusic.com')) and url not in playable:
                    playable.append(url)
            return playable
        urls = run(identity(), resolve)
        if not urls:
            return json_fail(message=f'无法获取{label}音源，请登录有相应权益的 QQ 音乐账号，或选择其他音质')
        return json_ok({'url': urls[0], 'urls': urls, 'quality': quality})
