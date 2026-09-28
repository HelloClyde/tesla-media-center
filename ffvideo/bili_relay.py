"""Authenticated, bounded byte-range relay; no media processing or disk cache."""
import re
from urllib.parse import urlsplit

import requests
from flask import Response, request
from itsdangerous import URLSafeTimedSerializer, BadSignature


def signer(app):
    return URLSafeTimedSerializer(app.secret_key, salt='bilibili-media-range-v1')


def relay_source(app, source):
    for kind in ('video', 'audio'):
        token = signer(app).dumps(source[kind]['urls'])
        source[kind]['urls'] = ['/api/bilibili/media-range/' + token]
    return source


def media_range(app, token):
    try:
        urls = signer(app).loads(token, max_age=21600)
    except BadSignature:
        return Response('播放地址已过期，请重试', status=410)
    match = re.fullmatch(r'bytes=(\d+)-(\d+)', request.headers.get('Range', ''))
    if not match:
        return Response('需要明确的单段 Range', status=416)
    start, end = map(int, match.groups())
    if end < start or end - start >= 32 * 1024 * 1024:
        return Response('Range 超出限制', status=416)
    for url in urls:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.port not in (None, 443)
                or parsed.username or not any(host.endswith('.' + domain)
                    for domain in ('bilivideo.com', 'bilivideo.cn', 'akamaized.net'))):
            continue
        upstream = None
        try:
            upstream = requests.get(url, headers={
                'Range': f'bytes={start}-{end}', 'Referer': 'https://www.bilibili.com/',
                'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity',
            }, stream=True, timeout=(5, 20), allow_redirects=False)
            content_range = upstream.headers.get('Content-Range', '')
            if upstream.status_code != 206 or not re.fullmatch(
                    rf'bytes {start}-{end}/\d+', content_range):
                upstream.close()
                continue
        except requests.RequestException:
            if upstream is not None:
                upstream.close()
            continue

        def chunks(response=upstream):
            remaining = end - start + 1
            try:
                for chunk in response.iter_content(64 * 1024):
                    if len(chunk) > remaining:
                        raise IOError('upstream exceeded requested range')
                    remaining -= len(chunk)
                    yield chunk
                if remaining:
                    raise IOError('upstream truncated requested range')
            finally:
                response.close()

        response = Response(chunks(), status=206, content_type='application/octet-stream', headers={
            'Content-Range': content_range, 'Content-Length': str(end - start + 1),
            'Accept-Ranges': 'bytes', 'Cache-Control': 'private, no-store',
            'X-Accel-Buffering': 'no',
        })
        response.call_on_close(upstream.close)
        return response
    return Response('所有源站均拒绝分段读取，请刷新播放地址', status=502)
