"""Public Douyin catalog and authenticated byte forwarding (no transcoding)."""
import re
from urllib.parse import urlsplit, urljoin, quote, parse_qs

import requests
from flask import Response, request
from itsdangerous import URLSafeTimedSerializer, BadSignature
from ffvideo.utils import login_check, json_ok, json_fail
from ffvideo.douyin_browser import read_page, allowed_media, DouyinUnavailable

HEADERS = {'Referer': 'https://www.douyin.com/', 'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'}


def allowed_page(url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.port in (None, 443) and p.username is None
                and p.password is None and p.hostname in ('www.douyin.com', 'douyin.com', 'v.douyin.com', 'www.iesdouyin.com'))
    except ValueError:
        return False


def video_id(value):
    value = str(value or '').strip()
    if len(value) > 4096:
        raise ValueError('分享内容太长，请只粘贴视频链接')
    if re.fullmatch(r'\d{15,22}', value):
        return value
    match = re.search(r'https://[^\s<>"，。]+', value)
    url = match[0].rstrip(')）') if match else ''
    for _ in range(4):
        if not allowed_page(url):
            raise ValueError('请粘贴抖音视频链接或完整分享文案')
        p = urlsplit(url)
        vid = re.fullmatch(r'/(?:share/)?video/(\d{15,22})/?', p.path)
        candidate = vid[1] if vid else parse_qs(p.query).get('modal_id', [''])[0]
        if re.fullmatch(r'\d{15,22}', candidate):
            return candidate
        if p.hostname != 'v.douyin.com':
            break
        with requests.get(url, headers=HEADERS, allow_redirects=False, stream=True, timeout=(5, 10)) as response:
            if response.status_code not in (301, 302, 303, 307, 308):
                break
            url = urljoin(url, response.headers.get('Location', ''))
    raise ValueError('没有识别到单个视频，请复制视频的分享链接（暂不支持直播或图文）')


def relay(urls, requested):
    match = re.fullmatch(r'bytes=(\d+)-(\d+)', requested or '')
    if not match or int(match[2]) < int(match[1]) or int(match[2]) - int(match[1]) >= 32 * 1024 * 1024:
        return Response('无效 Range', status=416)
    for url in urls[:3]:
        upstream = None
        try:
            for _ in range(4):
                if not allowed_media(url):
                    break
                upstream = requests.get(url, headers={**HEADERS, 'Range': requested}, stream=True,
                                        timeout=(5, 20), allow_redirects=False)
                if upstream.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, upstream.headers.get('Location', ''))
                    upstream.close(); upstream = None
                    continue
                break
            if upstream is None:
                continue
            returned = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', upstream.headers.get('Content-Range', ''))
            length = int(upstream.headers.get('Content-Length', 0))
            if (upstream.status_code != 206 or not returned or int(returned[3]) <= int(match[1])
                    or int(returned[1]) != int(match[1])
                    or int(returned[2]) != min(int(match[2]), int(returned[3]) - 1)
                    or length != int(returned[2]) - int(returned[1]) + 1):
                upstream.close(); continue
        except (requests.RequestException, ValueError):
            if upstream is not None: upstream.close()
            continue

        def chunks(remote=upstream, remaining=length):
            try:
                for chunk in remote.iter_content(64 * 1024):
                    if len(chunk) > remaining: raise IOError('upstream exceeded range')
                    remaining -= len(chunk)
                    yield chunk
                if remaining: raise IOError('upstream truncated range')
            finally:
                remote.close()
        response = Response(chunks(), status=206, content_type='video/mp4', headers={
            'Content-Length': str(length), 'Content-Range': upstream.headers['Content-Range'],
            'Accept-Ranges': 'bytes', 'Cache-Control': 'private, no-store', 'X-Accel-Buffering': 'no',
        })
        response.call_on_close(upstream.close)
        return response
    return Response('抖音视频源暂时不可用，请重新打开', status=502)


def add_routes(app):
    from ffvideo.douyin_auth import add_routes as add_auth_routes
    accounts = add_auth_routes(app)
    def signer():
        return URLSafeTimedSerializer(app.secret_key, salt='douyin-public-media-v1')

    @app.route('/api/douyin/home')
    @app.route('/api/douyin/search')
    @login_check
    def douyin_catalog():
        try:
            if request.path.endswith('/search'):
                query = request.args.get('q', '').strip()
                if not query or len(query) > 80: raise ValueError('请输入 1–80 字的搜索词')
                url = 'https://www.douyin.com/search/' + quote(query, safe='') + '?type=video'
            else:
                url = 'https://www.douyin.com/jingxuan'
            response = json_ok(read_page(url, cookies=accounts.credentials()))
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except ValueError as error:
            return json_fail('unavailable', message=str(error)), 503 if isinstance(error, DouyinUnavailable) else 400

    @app.route('/api/douyin/comments')
    @login_check
    def douyin_comments():
        vid = request.args.get('vid', '')
        if not re.fullmatch(r'\d{15,22}', vid):
            return json_fail('invalid_request', message='无效视频编号'), 400
        try:
            result = read_page(f'https://www.douyin.com/video/{vid}', source='comments', cookies=accounts.credentials())
            response = json_ok(result)
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except DouyinUnavailable as error:
            return json_fail('unavailable', message=str(error)), 503

    @app.route('/api/douyin/source', methods=['POST'])
    @login_check
    def douyin_source():
        try:
            vid = video_id((request.get_json(silent=True) or {}).get('url'))
            page_url = f'https://www.douyin.com/video/{vid}'
            result = dict(read_page(page_url, source=True, cookies=accounts.credentials()))
            result.update(vid=vid, pageUrl=page_url, url='/api/douyin/media/' + signer().dumps(result['urls']))
            response = json_ok(result)
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except ValueError as error:
            return json_fail('unavailable', message=str(error)), 503 if isinstance(error, DouyinUnavailable) else 400
        except requests.RequestException:
            return json_fail('upstream_failed', message='抖音分享链接暂时无法访问'), 502

    @app.route('/api/douyin/media/<string:token>')
    @login_check
    def douyin_media(token):
        try:
            urls = signer().loads(token, max_age=21600)
            if not isinstance(urls, list) or not urls or not all(isinstance(u, str) and allowed_media(u) for u in urls):
                raise BadSignature('invalid sources')
        except BadSignature:
            return Response('播放地址已过期，请重新打开', status=410)
        return relay(urls, request.headers.get('Range'))
