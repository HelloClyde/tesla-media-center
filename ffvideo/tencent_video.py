"""Public Tencent Video links, with byte-only authenticated media forwarding."""
import json
import re
from urllib.parse import urlsplit, parse_qs, urlencode

import requests
from flask import Response, request
from itsdangerous import URLSafeTimedSerializer, BadSignature
from ffvideo.utils import login_check, json_ok, json_fail
from ffvideo import tencent_catalog as catalog

HEADERS = {'Referer': 'https://v.qq.com/', 'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'}


def video_id(value):
    value = str(value or '').strip()
    if re.fullmatch(r'[A-Za-z0-9]{11}', value):
        return value
    url = urlsplit(value)
    if url.scheme not in ('http', 'https') or url.hostname not in ('v.qq.com', 'm.v.qq.com') or url.username:
        raise ValueError('请输入腾讯视频单集链接或 11 位 VID')
    candidate = parse_qs(url.query).get('vid', [''])[0]
    if not candidate:
        match = re.fullmatch(r'/x/(?:page|cover/[A-Za-z0-9]+)/([A-Za-z0-9]{11})\.html/?', url.path)
        candidate = match.group(1) if match else ''
    if not re.fullmatch(r'[A-Za-z0-9]{11}', candidate):
        raise ValueError('请复制具体视频的链接，暂不支持专辑或短链接')
    return candidate


def allowed_media(url):
    parsed = urlsplit(url)
    try:
        if parsed.username is not None or parsed.password is not None:
            return False
        # The official dispatch endpoint also supplies HTTP-only MP4 sources.
        # Preserve these for server forwarding; upgrading breaks its certificate.
        if parsed.scheme == 'http':
            return parsed.hostname == 'video.dispatch.tc.qq.com' and parsed.port in (None, 80)
        return (parsed.scheme == 'https' and parsed.port in (None, 443)
                and (parsed.hostname or '').endswith('.tc.qq.com'))
    except ValueError:
        return False


def parse_source(data, vid):
    if data.get('em') not in (None, 0) or not data.get('vl', {}).get('vi'):
        raise ValueError('腾讯视频未提供公开播放源，可能需要登录、会员或受地区限制')
    item = data['vl']['vi'][0]
    formats = data.get('fl', {}).get('fi', [])
    if item.get('drm') or any(f.get('drm') for f in formats):
        raise ValueError('该视频使用加密播放，暂不支持 WASM 播放')
    if item.get('cl', {}).get('fc', 0) or not str(item.get('fn', '')).endswith('.mp4') or not item.get('fvkey'):
        raise ValueError('当前源不是可支持的完整 MP4，请尝试其他公开视频')
    urls = []
    for entry in item.get('ul', {}).get('ui', []):
        base = entry.get('url', '')
        if entry.get('hls'):
            continue
        url = base + item['fn'] + '?' + urlencode({'vkey': item['fvkey']})
        if allowed_media(url) and url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError('没有可转接的公开视频源')
    return {'vid': vid, 'title': item.get('ti') or vid, 'duration': float(item.get('td') or 0),
            'pageUrl': f'https://v.qq.com/x/page/{vid}.html', 'urls': urls}


def add_routes(app):
    from ffvideo.tencent_auth import add_routes as add_auth_routes
    accounts = add_auth_routes(app)
    def signer():
        return URLSafeTimedSerializer(app.secret_key, salt='tencent-public-media-v1')

    @app.route('/api/tencent-video/home', methods=['GET'])
    @app.route('/api/tencent-video/search', methods=['GET'])
    @login_check
    def browse():
        try:
            if request.path.endswith('/search'):
                query = request.args.get('q', '').strip()
                page = int(request.args.get('page', '0'))
                if not query or len(query) > 100 or not 0 <= page <= 50:
                    raise ValueError('请输入 1–100 字的关键词，页码须在 0–50 之间')
                data = catalog.get_search(query, page)
                normal = data.get('normalList') or {}
                if normal.get('errcode', 0) != 0:
                    raise ValueError('腾讯视频搜索暂时不可用，请重试')
                items = catalog.search_cards(data)
                more = bool(normal.get('itemList')) and (page + 1) * 30 < int(normal.get('totalNum') or 0) and page < 50
                result = {'items': items, 'nextPage': page + 1 if more else None}
            else:
                cursor = request.args.get('cursor')
                if cursor and len(cursor) > 16000:
                    raise ValueError('首页分页信息无效，请刷新')
                pager = URLSafeTimedSerializer(app.secret_key, salt='tencent-home-page-v1')
                context = pager.loads(cursor, max_age=1800) if cursor else None
                data = catalog.get_home(context)
                next_context = data.get('page_context')
                result = {'items': catalog.home_cards(data), 'nextCursor': pager.dumps(next_context)
                          if data.get('has_next_page') and next_context and next_context != context else None}
            response = json_ok(result)
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except BadSignature:
            return json_fail('invalid_cursor', message='首页已更新，请刷新推荐'), 400
        except (ValueError, TypeError) as error:
            return json_fail('catalog_unavailable', message=str(error)), 400
        except requests.RequestException:
            return json_fail('upstream_failed', message='腾讯视频目录请求失败，请重试'), 502

    @app.route('/api/tencent-video/source', methods=['POST'])
    @login_check
    def source():
        try:
            vid = video_id((request.get_json(silent=True) or {}).get('url'))
            with requests.get('https://h5vv.video.qq.com/getinfo', params={
                'vids': vid, 'platform': '11001', 'charge': 0, 'otype': 'json', 'defn': 'hd',
            }, headers=HEADERS, cookies=accounts.cookies(), timeout=(5, 15)) as upstream:
                upstream.raise_for_status()
                payload = upstream.content.decode('utf-8').strip()
            match = re.fullmatch(r'QZOutputJson=(\{.*\});?', payload, re.S)
            if not match:
                raise ValueError('腾讯视频播放接口返回格式已变化')
            result = parse_source(json.loads(match.group(1)), vid)
            result['url'] = '/api/tencent-video/media/' + signer().dumps(result['urls'])
            # HTTPS pages cannot fetch HTTP sources directly (mixed content).
            result['urls'] = [url for url in result['urls'] if urlsplit(url).scheme == 'https']
            response = json_ok(result)
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except (ValueError, KeyError, TypeError) as error:
            return json_fail('unavailable', message=str(error)), 400
        except requests.RequestException:
            return json_fail('upstream_failed', message='腾讯视频请求失败，请稍后重试'), 502

    @app.route('/api/tencent-video/media/<string:token>', methods=['GET'])
    @login_check
    def media(token):
        try:
            urls = signer().loads(token, max_age=21600)
        except BadSignature:
            return Response('播放地址已过期，请重新打开', status=410)
        requested = request.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d+)-(\d+)', requested)
            if not match or int(match[2]) < int(match[1]) or int(match[2]) - int(match[1]) >= 32 * 1024 * 1024:
                return Response('无效 Range', status=416)
        for url in urls:
            if not allowed_media(url):
                continue
            upstream = None
            try:
                headers = dict(HEADERS)
                if requested:
                    headers['Range'] = requested
                upstream = requests.get(url, headers=headers, stream=True, timeout=(5, 20), allow_redirects=False)
                if upstream.status_code != (206 if requested else 200):
                    upstream.close()
                    continue
                length = int(upstream.headers.get('Content-Length', 0))
                if length <= 0:
                    upstream.close()
                    continue
                content_range = upstream.headers.get('Content-Range', '')
                if requested:
                    returned = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', content_range)
                    if (not returned or int(returned[1]) != int(match[1])
                            or int(returned[2]) != min(int(match[2]), int(returned[3]) - 1)
                            or length != int(returned[2]) - int(returned[1]) + 1):
                        upstream.close()
                        continue
            except (requests.RequestException, ValueError):
                if upstream is not None:
                    upstream.close()
                continue

            def chunks(remote=upstream, remaining=length):
                try:
                    for chunk in remote.iter_content(64 * 1024):
                        if len(chunk) > remaining:
                            raise IOError('upstream exceeded Content-Length')
                        remaining -= len(chunk)
                        yield chunk
                    if remaining:
                        raise IOError('upstream truncated response')
                finally:
                    remote.close()

            response = Response(chunks(), status=upstream.status_code, content_type='video/mp4', headers={
                'Content-Length': str(length), 'Accept-Ranges': 'bytes',
                'Cache-Control': 'private, no-store', 'X-Accel-Buffering': 'no',
            })
            if requested:
                response.headers['Content-Range'] = content_range
            response.call_on_close(upstream.close)
            return response
        return Response('腾讯视频源暂时不可用，请重新打开', status=502)
