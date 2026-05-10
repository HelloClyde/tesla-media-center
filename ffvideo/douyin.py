import html
import json
import re
import time
from urllib.parse import unquote, urlparse

import requests
from flask import Response, jsonify, request, stream_with_context
from loguru import logger

from ffvideo.utils import json_fail, json_ok, login_check


DOUYIN_RECOMMEND_URL = 'https://www.douyin.com/?recommend=1'
DOUYIN_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)
DOUYIN_CACHE_TTL_SEC = 20 * 60
douyin_video_cache: dict[str, dict] = {}


def douyin_headers(referer=DOUYIN_RECOMMEND_URL, extra=None):
    headers = {
        'accept': '*/*',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'referer': referer,
        'user-agent': DOUYIN_USER_AGENT,
    }
    headers.update(extra or {})
    return headers


def extract_douyin_video_id(value: str):
    value = (value or '').strip()
    if not value:
        return ''
    for pattern in [
        r'/video/(\d+)',
        r'[?&](?:modal_id|aweme_id|item_id)=(\d+)',
        r'\b(\d{12,})\b',
    ]:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return ''


def normalize_douyin_input(value: str):
    value = (value or '').strip()
    if not value:
        return ''
    if re.fullmatch(r'\d{12,}', value):
        return f'https://www.douyin.com/video/{value}'
    urls = re.findall(r'https?://[^\s]+', value)
    return urls[0].rstrip('，。,.') if urls else value


def resolve_douyin_url(value: str):
    value = normalize_douyin_input(value)
    if not value.startswith(('http://', 'https://')):
        return ''
    parsed = urlparse(value)
    if not (parsed.netloc.endswith('douyin.com') or parsed.netloc.endswith('iesdouyin.com')):
        return ''
    if extract_douyin_video_id(value) and parsed.netloc.endswith('douyin.com'):
        return value
    response = requests.get(
        value,
        headers=douyin_headers(value),
        allow_redirects=True,
        timeout=12,
    )
    response.raise_for_status()
    return response.url


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_json(item)


def parse_json_candidates(page_text: str):
    candidates = []
    for pattern in [
        r'<script[^>]+id="RENDER_DATA"[^>]*>(.*?)</script>',
        r'<script[^>]+id="SIGI_STATE"[^>]*>(.*?)</script>',
    ]:
        for match in re.finditer(pattern, page_text, re.S):
            raw = html.unescape(match.group(1)).strip()
            candidates.extend([raw, unquote(raw)])

    for pattern in [
        r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>',
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;',
    ]:
        for match in re.finditer(pattern, page_text, re.S):
            candidates.append(html.unescape(match.group(1)).strip())

    for raw in candidates:
        try:
            yield json.loads(raw)
        except Exception:
            continue


def pick_url_from_addr(addr):
    if not isinstance(addr, dict):
        return ''
    url_list = addr.get('url_list') or addr.get('urlList') or []
    if isinstance(url_list, list):
        for url in url_list:
            if isinstance(url, str) and url.startswith('http'):
                return url.replace('\\u002F', '/')
    url = addr.get('url') or addr.get('uri')
    return url if isinstance(url, str) and url.startswith('http') else ''


def extract_aweme_payload(video_id: str, page_text: str):
    best = None
    for payload in parse_json_candidates(page_text):
        for node in walk_json(payload):
            node_id = str(node.get('aweme_id') or node.get('awemeId') or node.get('id') or '')
            video = node.get('video') if isinstance(node.get('video'), dict) else None
            if not video:
                continue
            play_url = pick_url_from_addr(video.get('play_addr') or video.get('playAddr'))
            if not play_url:
                continue
            if node_id == video_id:
                return node
            best = best or node
    if best:
        return best

    # Last-resort regex fallback for page layouts that expose play_addr inline.
    match = re.search(r'"play_addr"\s*:\s*\{.*?"url_list"\s*:\s*\[(.*?)\]', page_text, re.S)
    if match:
        url_match = re.search(r'"(https?:\\?/\\?/[^"]+)"', match.group(1))
        if url_match:
            return {
                'aweme_id': video_id,
                'video': {
                    'play_addr': {
                        'url_list': [url_match.group(1).replace('\\/', '/').replace('\\u002F', '/')],
                    },
                },
            }
    return None


def resolve_douyin_video(source: str, force=False):
    resolved_url = resolve_douyin_url(source)
    video_id = extract_douyin_video_id(resolved_url or source)
    if not video_id:
        return None, ('invalid_douyin_url', '请输入抖音视频分享链接或视频 ID')

    cached = douyin_video_cache.get(video_id)
    if not force and cached and time.time() - cached.get('resolved_at', 0) < DOUYIN_CACHE_TTL_SEC:
        return cached, None

    video_page_url = f'https://www.douyin.com/video/{video_id}'
    page = requests.get(video_page_url, headers=douyin_headers(video_page_url), timeout=15)
    page.raise_for_status()
    aweme = extract_aweme_payload(video_id, page.text)
    if not aweme:
        return None, ('douyin_parse_failed', '未能从抖音页面提取播放地址，可能需要登录或页面结构已变化')

    video = aweme.get('video') or {}
    play_url = pick_url_from_addr(video.get('play_addr') or video.get('playAddr'))
    if not play_url:
        return None, ('douyin_parse_failed', '抖音页面没有返回可用播放地址')

    duration_ms = int(video.get('duration') or aweme.get('duration') or 0)
    item = {
        'videoId': video_id,
        'videoUrl': video_page_url,
        'playUrl': play_url,
        'title': aweme.get('desc') or aweme.get('caption') or '抖音视频',
        'authorName': (aweme.get('author') or {}).get('nickname') or '',
        'cover': pick_url_from_addr(video.get('cover') or video.get('origin_cover') or video.get('dynamic_cover')),
        'durationMs': duration_ms,
        'resolved_at': time.time(),
    }
    douyin_video_cache[video_id] = item
    return item, None


def get_cached_or_resolve(video_id: str, force=False):
    return resolve_douyin_video(video_id, force=force)


def add_douyin_route(app):
    @app.route('/api/douyin/resolve', methods=['GET'])
    @login_check
    def douyin_resolve():
        source = request.args.get('url') or request.args.get('videoId') or ''
        item, error = resolve_douyin_video(source, force=request.args.get('force') == '1')
        if error:
            return json_fail(error[0], message=error[1]), 400
        public_item = {key: value for key, value in item.items() if key not in ['playUrl', 'resolved_at']}
        public_item['streamUrl'] = f'/api/douyin/video/{item["videoId"]}'
        return json_ok(public_item)

    @app.route('/api/douyin/video/<string:video_id>/info', methods=['GET'])
    @login_check
    def douyin_video_info(video_id):
        item, error = get_cached_or_resolve(video_id, force=request.args.get('force') == '1')
        if error:
            return json_fail(error[0], message=error[1]), 400

        headers = douyin_headers(item['videoUrl'])
        upstream = requests.get(item['playUrl'], headers={**headers, 'range': 'bytes=0-0'}, stream=True, timeout=15)
        content_range = upstream.headers.get('content-range', '')
        match = re.search(r'/(\d+)$', content_range)
        size = int(match.group(1)) if match else int(upstream.headers.get('content-length') or 0)
        duration = int(item.get('durationMs') or 0)

        response = jsonify({
            'videoId': item['videoId'],
            'title': item.get('title'),
            'authorName': item.get('authorName'),
            'size': size,
            'durationMs': duration,
        })
        response.headers['BV-Content-Length'] = str(size if size > 0 else 1024 * 1024 * 1024)
        response.headers['BV-Duration'] = str(duration)
        return response

    @app.route('/api/douyin/video/<string:video_id>', methods=['GET'])
    @login_check
    def douyin_video_stream(video_id):
        item, error = get_cached_or_resolve(video_id)
        if error:
            return json_fail(error[0], message=error[1]), 400

        range_header = request.headers.get('range') or request.headers.get('Range') or 'bytes=0-'
        upstream = requests.get(
            item['playUrl'],
            headers=douyin_headers(item['videoUrl'], {'Range': range_header}),
            stream=True,
            timeout=30,
        )
        if upstream.status_code >= 400:
            logger.warning(f'douyin upstream failed, video_id={video_id}, status={upstream.status_code}')
            return json_fail('douyin_stream_failed', message=f'抖音视频流请求失败: {upstream.status_code}'), 502

        content_range = upstream.headers.get('content-range', '')
        total_size_match = re.search(r'/(\d+)$', content_range)
        total_size = total_size_match.group(1) if total_size_match else upstream.headers.get('content-length', '')
        response_headers = {
            'Content-Type': upstream.headers.get('content-type', 'video/mp4'),
            'Accept-Ranges': 'bytes',
            'BV-Content-Length': total_size,
        }
        if content_range:
            response_headers['Content-Range'] = content_range
        if upstream.headers.get('content-length'):
            response_headers['Content-Length'] = upstream.headers['content-length']

        return Response(
            stream_with_context(upstream.iter_content(chunk_size=256 * 1024)),
            status=206 if upstream.status_code == 206 else 200,
            headers=response_headers,
        )

    @app.route('/api/douyin/recommend', methods=['GET'])
    @login_check
    def douyin_recommend():
        return json_ok({
            'url': DOUYIN_RECOMMEND_URL,
            'note': '抖音推荐流接口依赖登录态、签名和风控，不在后端硬编码私有推荐接口。',
        })
