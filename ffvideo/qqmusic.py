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
from qqmusic_api.core.exceptions import RatelimitedError
from qqmusic_api.models.login import QRLoginType
from qqmusic_api.modules.song import SongFileInfo, SongFileType
from ffvideo.utils import json_ok, json_fail, login_check
from ffvideo.qqmusic_daily import DailyApi

STORE = Path(__file__).resolve().parent.parent / '.qqmusic'
LOCK = threading.RLock()
PENDING = {}
QUALITIES = {
    'standard': (SongFileType.MP3_128, 'size_128mp3', '标准 128 kbps'),
    'high': (SongFileType.MP3_320, 'size_320mp3', '高品质 320 kbps'),
    'lossless': (SongFileType.FLAC, 'size_flac', '无损 FLAC'),
    'premium': (SongFileType.ATMOS_2, 1, '臻品音质'),
    'master': (SongFileType.MASTER, 0, '臻品母带'),
}


def song_max_quality(song):
    """Highest reported source tier; not a guarantee of account playback rights."""
    file = getattr(song, 'file', None)
    if file is None:
        return 'unknown'
    sizes = getattr(file, 'size_new', []) or []
    def modern(index):
        return len(sizes) > index and sizes[index] > 0
    if modern(0):
        return 'master'
    if modern(1):
        return 'premium'
    if getattr(file, 'size_flac', 0) > 0 or modern(5):
        return 'lossless'
    if any(getattr(file, field, 0) > 0 for field in ('size_320mp3', 'size_192ogg', 'size_192aac')) or modern(3):
        return 'high'
    if getattr(file, 'size_128mp3', 0) > 0 or modern(7):
        return 'standard'
    if any(getattr(file, field, 0) > 0 for field in ('size_24aac', 'size_48aac', 'size_96aac', 'size_96ogg')):
        return 'smooth'
    return 'unknown'


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
        except RatelimitedError:
            response = json_fail(message='QQ 音乐请求频率受限，请稍后再试'), 429
        except Exception:
            # Upstream exception strings can contain login tokens and signed URLs.
            response = json_fail(message='QQ 音乐服务暂时不可用，请稍后重试；登录失效时请重新扫码'), 502
        response = current_app.make_response(response)
        response.headers['Cache-Control'] = 'no-store'
        return response
    return wrapped


def add_qqmusic_route(app):
    def song_summary(s):
        pay = getattr(s, 'pay', None)
        access = 'unknown'
        if pay is not None:
            if pay.pay_month:
                access = 'vip'
            elif pay.pay_play:
                access = 'purchase' if pay.price_track or pay.price_album else 'paid'
            elif {'pay_play', 'pay_month'} <= pay.model_fields_set:
                access = 'standard'
        return {'mid': s.mid, 'title': s.title or s.name,
                'singer': ' / '.join(x.name for x in s.singer),
                'album': s.album.title, 'cover': s.album.cover_url(),
                'id': getattr(s, 'id', 0), 'songType': getattr(s, 'type', 0),
                'singers': [{'mid': x.mid, 'name': x.name} for x in s.singer],
                'albumMid': getattr(s.album, 'mid', ''),
                'duration': s.interval, 'access': access, 'maxQuality': song_max_quality(s)}

    @app.get('/api/qqmusic/membership')
    @endpoint
    def qq_membership():
        sid = identity()
        if not credential(sid):
            return json_ok({'label': '未登录', 'level': None, 'isVip': None})
        result = run(sid, lambda c: c.user.get_vip_info())
        identity_info = result.identity
        known = 'svip' in result.model_fields_set or bool(identity_info.model_fields_set & {
            'vip', 'huge_vip', 'exp_vip', 'group_vip_flag', 'cp_lover_flag', 'ad_vip_flag', 'child_vip', 'twelve', 'eight'})
        labels = [(result.svip, '超级会员'), (identity_info.huge_vip, '豪华绿钻'),
                  (identity_info.vip, '绿钻会员'), (identity_info.exp_vip, '体验会员'),
                  (identity_info.group_vip_flag, '家庭会员'), (identity_info.cp_lover_flag, '情侣会员'),
                  (identity_info.child_vip, '儿童会员'), (identity_info.ad_vip_flag, '广告会员'),
                  (identity_info.twelve or identity_info.eight, '联合会员')]
        label = next((label for flag, label in labels if flag), '普通用户' if known else '会员状态未知')
        is_vip = any(flag for flag, _ in labels) if known else None
        return json_ok({'label': label, 'isVip': is_vip,
                        'level': identity_info.level if is_vip and identity_info.level > 0 else None})

    @app.get('/api/qqmusic/recommend')
    @endpoint
    def qq_recommend():
        sid = identity()
        if not credential(sid):
            return json_ok({'songs': [], 'loginRequired': True})
        result = run(sid, lambda c: c.recommend.get_guess_recommend())
        return json_ok({'songs': [song_summary(s) for s in result.songs if s.mid],
                        'loginRequired': False})

    @app.get('/api/qqmusic/daily')
    @endpoint
    def qq_daily():
        sid = identity()
        if not credential(sid):
            return json_ok({'songs': [], 'loginRequired': True})
        async def load(client):
            playlist_id = await DailyApi(client).playlist_id()
            if not playlist_id:
                raise InputError('暂未获取到每日推荐歌单，请稍后重试或重新登录 QQ 音乐')
            result = await client.songlist.get_detail(playlist_id, num=100)
            if result.code or result.subcode:
                raise InputError('每日推荐歌单暂时无法读取，请稍后重试')
            return {'songs': [song_summary(s) for s in result.songs if s.mid],
                    'loginRequired': False}
        return json_ok(run(sid, load))

    @app.get('/api/qqmusic/account')
    @endpoint
    def qq_account():
        cred = credential(identity())
        return json_ok({'loggedIn': bool(cred), 'account': str(cred.musicid) if cred else ''})

    @app.get('/api/qqmusic/library')
    @endpoint
    def qq_library():
        kind = request.args.get('kind', 'songs')
        page = request.args.get('page', '1')
        playlist = request.args.get('id', '')
        if kind not in ('songs', 'playlists', 'created', 'playlist') or not page.isascii() or not page.isdigit() or not 1 <= int(page) <= 10000:
            raise InputError('音乐库参数无效')
        if kind == 'playlist' and not re.fullmatch(r'[1-9][0-9]{0,19}', playlist):
            raise InputError('歌单标识无效')
        sid = identity()
        cred = credential(sid)
        if not cred:
            return json_ok({'songs': [], 'playlists': [], 'more': False, 'loginRequired': True})
        async def load(client):
            if kind == 'songs':
                result = await client.user.get_fav_song(cred.encrypt_uin, page=int(page), num=30, credential=cred)
            elif kind == 'playlist':
                result = await client.songlist.get_detail(int(playlist), page=int(page), num=30)
            elif kind == 'playlists':
                result = await client.user.get_fav_songlist(cred.encrypt_uin, page=int(page), num=30, credential=cred)
            else:
                result = await client.user.get_created_songlist(cred.musicid, credential=cred)
            if kind in ('songs', 'playlist'):
                if result.code or result.subcode:
                    raise InputError('无法读取歌曲列表，请确认歌单可访问并重新登录')
                return {'songs': [song_summary(s) for s in result.songs if s.mid],
                        'playlists': [], 'more': bool(result.hasmore), 'loginRequired': False}
            return {'songs': [], 'playlists': [
                {'id': str(p.id), 'dirid': getattr(p, 'dirid', 0), 'title': p.title, 'cover': p.picurl, 'count': p.songnum}
                for p in result.playlists if p.id and not getattr(p, 'invalid', False)],
                'more': bool(result.hasmore) if kind == 'playlists' else False,
                'loginRequired': False}
        return json_ok(run(sid, load))

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
        data = request.get_json(silent=True)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise InputError('登录参数无效')
        provider = data.get('provider', 'qq')
        if provider not in ('qq', 'wx'):
            raise InputError('请选择 QQ 或微信登录')
        sid = identity()
        qr_type = QRLoginType.WX if provider == 'wx' else QRLoginType.QQ
        with LOCK:
            PENDING.pop(sid, None)
        qr = run(sid, lambda c: c.login.get_qrcode(qr_type))
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
        return json_ok({'songs': [song_summary(s) for s in result.song],
                        'more': result.nextpage > int(page)})

    def valid_id(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9]{1,32}', value):
            raise InputError('内容标识无效')
        return value

    @app.get('/api/qqmusic/suggestions')
    @endpoint
    def qq_suggestions():
        query = request.args.get('q', '').strip()
        if not 1 <= len(query) <= 100:
            raise InputError('关键词长度无效')
        result = run(identity(), lambda c: c.search.complete(query))
        return json_ok({'words': list(dict.fromkeys(x.hint for x in result.items if x.hint))[:8]})

    @app.get('/api/qqmusic/browse')
    @endpoint
    def qq_browse():
        kind = request.args.get('kind', '')
        value = request.args.get('id', '')
        page = request.args.get('page', '1')
        if not page.isascii() or not page.isdigit() or not 1 <= int(page) <= 100:
            raise InputError('页码无效')
        page = int(page)
        async def load(client):
            if kind == 'tops':
                result = await client.top.get_category()
                return {'items': [{'id': str(t.id), 'kind': 'top', 'title': t.name, 'cover': t.front_pic_url, 'group': g.name, 'subtitle': t.update_time, 'count': t.total_num} for g in result.group for t in g.toplist], 'songs': [], 'more': False}
            if kind == 'singers':
                result = await client.singer.get_singer_list()
                return {'items': [{'id': x.mid, 'kind': 'singer', 'title': x.name, 'cover': x.singer_pic or x.cover_url(), 'subtitle': x.country} for x in result.singerlist if x.mid], 'songs': [], 'more': False}
            if kind in ('singer-albums', 'singer-mvs'):
                valid_id(value)
                if kind == 'singer-albums':
                    result = await client.singer.get_album_list(value, num=20, page=page)
                    items = [{'id': x.mid, 'kind': 'album', 'title': x.name, 'cover': x.cover_url(), 'subtitle': x.time_public} for x in result.album_list]
                else:
                    result = await client.singer.get_mv_list(value, num=20, page=page)
                    items = [{'id': x.vid, 'kind': 'mv', 'title': x.title, 'cover': x.picurl} for x in result.mv_list if x.vid]
                return {'items': items, 'songs': [], 'more': page * 20 < result.total}
            if kind in ('singer', 'album', 'playlist', 'top'):
                valid_id(value)
                if kind in ('playlist', 'top') and not value.isdecimal():
                    raise InputError('内容标识无效')
                if kind == 'singer':
                    result = await client.singer.get_songs_list(value, num=30, page=page)
                    tracks, more = result.song_list, page * 30 < result.total_num
                elif kind == 'album':
                    result = await client.album.get_song(value, num=30, page=page)
                    tracks, more = result.song_list, page * 30 < result.total_num
                elif kind == 'playlist':
                    result = await client.songlist.get_detail(int(value), num=30, page=page)
                    tracks, more = result.songs, bool(result.hasmore)
                else:
                    result = await client.top.get_detail(int(value), num=30, page=page)
                    tracks, more = result.songs, page * 30 < result.info.total_num
                return {'items': [], 'songs': [song_summary(s) for s in tracks if s.mid], 'more': more,
                        'info': {'title': result.info.name, 'cover': result.info.front_pic_url, 'description': result.info.intro, 'updated': result.info.update_time, 'period': result.info.period, 'count': result.info.total_num} if kind == 'top' else None}
            types = {'singer-search': (1, 'singer'), 'album-search': (2, 'album'), 'playlist-search': (3, 'songlist'), 'mv-search': (4, 'mv'), 'audio-search': (18, 'song')}
            if kind not in types:
                raise InputError('不支持的浏览类型')
            query = request.args.get('q', '').strip()
            if not 1 <= len(query) <= 100:
                raise InputError('请输入关键词')
            code, field = types[kind]
            result = await client.search.search_by_type(query, search_type=code, num=20, page=page, highlight=False)
            entries = getattr(result, field)
            if field == 'song':
                return {'items': [], 'songs': [song_summary(x) for x in entries], 'more': result.nextpage > page}
            items = []
            for x in entries:
                if field == 'singer':
                    items.append({'id': x.mid, 'title': x.name, 'cover': x.pic, 'kind': 'singer'})
                elif field == 'album':
                    items.append({'id': x.mid, 'title': x.title or x.name, 'cover': x.pic, 'kind': 'album'})
                elif field == 'songlist':
                    items.append({'id': str(x.id), 'title': x.title, 'cover': x.picurl, 'kind': 'playlist'})
                else:
                    items.append({'id': x.vid, 'title': x.title or x.name, 'cover': x.pic, 'kind': 'mv'})
            return {'items': items, 'songs': [], 'more': result.nextpage > page}
        return json_ok(run(identity(), load))

    @app.get('/api/qqmusic/singer-profile')
    @endpoint
    def qq_singer_profile():
        mid = valid_id(request.args.get('id'))
        result = run(identity(), lambda c: c.singer.get_desc([mid], wiki_singer=False, photos=False))
        if not result.singer_list:
            raise InputError('暂未找到歌手资料')
        singer = result.singer_list[0]
        return json_ok({'title': singer.basic_info.name, 'cover': singer.pic.pic or singer.basic_info.cover_url(),
                        'description': singer.ex_info.desc, 'area': singer.ex_info.area, 'genre': singer.ex_info.genre})

    @app.post('/api/qqmusic/collection')
    @endpoint
    def qq_collection():
        sid = identity()
        cred = credential(sid)
        if not cred:
            raise InputError('请先登录 QQ 音乐')
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise InputError('操作参数无效')
        action = data.get('action')
        if action not in ('like', 'unlike', 'create', 'add', 'remove'):
            raise InputError('不支持的歌单操作')
        async def change(client):
            if action == 'create':
                name = data.get('name', '')
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
                    raise InputError('歌单名称须为 1–40 字')
                result = await client.songlist.create(name.strip(), credential=cred)
                if result.retCode or not result.dirid:
                    raise InputError('创建歌单失败，请稍后重试')
                return {'created': True}
            mid = valid_id(data.get('mid'))
            detail = await client.song.get_detail(mid)
            info = [(detail.track.id, detail.track.type)]
            if action in ('like', 'unlike'):
                operation = client.songlist.like_song if action == 'like' else client.songlist.unlike_song
                success = await operation(info, credential=cred)
            else:
                # Only allow changes to a playlist belonging to this account.
                created = await client.user.get_created_songlist(cred.musicid, credential=cred)
                playlist = next((p for p in created.playlists if str(p.id) == str(data.get('playlist')) and p.dirid != 201), None)
                if playlist is None or playlist.dirid <= 0:
                    raise InputError('请选择自己的歌单')
                operation = client.songlist.add_songs if action == 'add' else client.songlist.del_songs
                success = await operation(playlist.dirid, info, tid=playlist.id, credential=cred)
            if not success:
                raise InputError('操作未成功，请刷新后重试')
            return {'updated': True}
        return json_ok(run(sid, change))

    @app.get('/api/qqmusic/comments')
    @endpoint
    def qq_comments():
        mid = valid_id(request.args.get('mid'))
        page = request.args.get('page', '1')
        cursor = request.args.get('cursor', '')
        if not page.isascii() or not page.isdigit() or not 1 <= int(page) <= 100 or len(cursor) > 100:
            raise InputError('评论参数无效')
        async def load(client):
            detail = await client.song.get_detail(mid)
            result = await client.comment.get_hot_comments(detail.track.id, page_num=int(page), last_comment_seq_no=cursor)
            return {'comments': [{'id': x.cmid, 'name': x.nick, 'text': x.content, 'likes': x.praise_num} for x in result.comments], 'more': bool(result.has_more), 'cursor': result.comments[-1].seq_no if result.comments else ''}
        return json_ok(run(identity(), load))

    @app.get('/api/qqmusic/mv')
    @endpoint
    def qq_mv():
        vid = valid_id(request.args.get('id'))
        result = run(identity(), lambda c: c.mv.get_mv_urls([vid]))
        variants = result.data.get(vid)
        urls = [u for item in (variants.mp4 if variants else []) if not item.code for u in item.url if urlparse(u).scheme == 'https' and ((urlparse(u).hostname or '').endswith('.qq.com') or (urlparse(u).hostname or '').endswith('.qqmusic.com'))]
        if not urls:
            raise InputError('暂无可播放的 MV 音源')
        return json_ok({'urls': list(dict.fromkeys(urls))})

    @app.get('/api/qqmusic/word-lyrics')
    @endpoint
    def qq_word_lyrics():
        mid = valid_id(request.args.get('mid'))
        result = run(identity(), lambda c: c.lyric.get_lyric(mid, qrc=True))
        return json_ok({'lyric': result.lyric})

    @app.get('/api/qqmusic/lyrics')
    @endpoint
    def qq_lyrics():
        mid = request.args.get('mid', '')
        if not re.fullmatch(r'[a-zA-Z0-9]{1,32}', mid):
            raise InputError('歌曲标识无效')
        result = run(identity(), lambda c: c.lyric.get_lyric(mid, trans=True))
        return json_ok({'lyric': result.lyric, 'translation': result.trans})

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
            sizes = getattr(detail.track.file, 'size_new', [])
            available = (sizes[size_field] if len(sizes) > size_field else 0) if isinstance(size_field, int) else getattr(detail.track.file, size_field, 0)
            if not available:
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
