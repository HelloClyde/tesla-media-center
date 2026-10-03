"""Read Douyin's public page data and JSON endpoints without a browser."""
import hashlib
import html
import json
import re
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeout
from urllib.parse import urlsplit, parse_qs, unquote, urlencode, quote


class DouyinUnavailable(ValueError):
    pass


_slots = threading.BoundedSemaphore(6)
_cache = {}
_inflight = {}
_cache_lock = threading.Lock()


def catalog_items(data, depth=0):
    """Extract public cards from the JSON responses used by the rendered page."""
    if depth > 10:
        return []
    if isinstance(data, list):
        return [item for value in data[:100] for item in catalog_items(value, depth + 1)]
    if not isinstance(data, dict):
        return []
    vid = str(data.get('aweme_id') or data.get('awemeId') or '')
    video = data.get('video')
    if re.fullmatch(r'\d{15,22}', vid) and isinstance(video, dict) and (data.get('desc') or data.get('itemTitle')):
        cover = video.get('cover') or {}
        covers = (cover.get('url_list') or cover.get('urlList') or video.get('coverUrlList') or []) if isinstance(cover, dict) else []
        return [{'vid': vid, 'title': str(data.get('desc') or data.get('itemTitle'))[:300],
                 'cover': next((u for u in covers if isinstance(u, str) and u.startswith('https://')), ''),
                 'pageUrl': f'https://www.douyin.com/video/{vid}'}]
    return [item for value in data.values() for item in catalog_items(value, depth + 1)]


def allowed_media(url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.port in (None, 443)
                and p.username is None and p.password is None
                and (any((p.hostname or '').endswith(suffix)
                         for suffix in ('.zjcdn.com', '.douyinvod.com'))
                     or (p.hostname == 'www.douyin.com' and p.path == '/aweme/v1/play/')))
    except (TypeError, ValueError):
        return False


def read_page(url, source=False, cookies=None):
    identity = hashlib.sha256(json.dumps(cookies or [], sort_keys=True).encode()).hexdigest()
    key = (url, source, identity)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 120:
            return cached[1]
        pending = _inflight.get(key)
        if pending is None:
            pending = Future()
            _inflight[key] = pending
            owner = True
        else:
            owner = False
    if not owner:
        try:
            return pending.result(timeout=100)
        except FutureTimeout:
            raise DouyinUnavailable('抖音页面加载超时，请重试') from None
    slot = _slots
    try:
        if not slot.acquire(timeout=30):
            raise DouyinUnavailable('抖音页面请求较多，请稍后重试')
        try:
            result = _read_page(url, source, cookies)
        finally:
            slot.release()
        with _cache_lock:
            if len(_cache) >= 32:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (time.monotonic(), result)
        pending.set_result(result)
        return result
    except Exception as error:
        pending.set_exception(error)
        raise
    finally:
        with _cache_lock:
            _inflight.pop(key, None)


_RENDER_DATA = re.compile(r'<script\b[^>]*\bid=["\']RENDER_DATA["\'][^>]*>(.*?)</script>', re.I | re.S)
_BASE = 'https://www.douyin.com'
_COMMON = {
    'device_platform': 'webapp', 'aid': '6383', 'channel': 'channel_pc_web',
    'pc_client_type': '1', 'version_code': '170400', 'version_name': '17.4.0',
    'cookie_enabled': 'true', 'screen_width': '1920', 'screen_height': '1080',
    'browser_language': 'zh-CN', 'browser_platform': 'Win32', 'browser_name': 'Chrome',
    'browser_version': '124.0.0.0', 'browser_online': 'true', 'engine_name': 'Blink',
    'engine_version': '124.0.0.0', 'os_name': 'Windows', 'os_version': '10',
    'cpu_core_num': '8', 'device_memory': '8', 'platform': 'PC',
    'downlink': '10', 'effective_type': '4g', 'round_trip_time': '50',
}


def _visitor(cookies):
    from tools.douyin.visitor_probe import create_visitor_session
    client = create_visitor_session()
    for cookie in cookies or []:
        if not isinstance(cookie, dict) or cookie.get('domain', '').lstrip('.') not in ('douyin.com', 'www.douyin.com'):
            continue
        if cookie.get('name') and cookie.get('value'):
            client.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie.get('path') or '/')
    return client


def _api(client, path, extra):
    from tools.douyin.visitor_probe import USER_AGENT
    from tools.douyin.signing.abogus import ABogus
    params = {**_COMMON, 'uifid': client.cookies.get('UIFID_TEMP') or '', **extra}
    query = urlencode(params)
    bogus = ABogus(USER_AGENT).get_value(query)
    response = client.get(_BASE + path + '?' + query + '&a_bogus=' + quote(bogus, safe=''),
                          headers={'Referer': _BASE + '/', 'Accept': 'application/json, text/plain, */*'}, timeout=20)
    if response.status_code != 200:
        raise DouyinUnavailable('抖音接口暂时不可用，请稍后重试')
    try:
        data = response.json()
    except ValueError:
        raise DouyinUnavailable('抖音接口返回了非预期内容，请稍后重试') from None
    if data.get('status_code') != 0:
        if data.get('status_code') == 2483:
            raise DouyinUnavailable('抖音搜索需要登录，请扫码登录后重试')
        raise DouyinUnavailable('抖音接口拒绝了请求，请稍后重试')
    return data


def _source_from_render(page, vid):
    match = _RENDER_DATA.search(page)
    if not match:
        raise DouyinUnavailable('抖音没有返回视频详情，请稍后重试')
    try:
        detail = json.loads(unquote(html.unescape(match.group(1))))['app']['videoDetail']
    except (ValueError, KeyError, TypeError):
        raise DouyinUnavailable('抖音视频详情格式已变化，请稍后重试') from None
    if not isinstance(detail, dict) or str(detail.get('awemeId')) != vid:
        raise DouyinUnavailable('抖音没有返回对应视频，请稍后重试')
    video = detail.get('video') or {}
    # The default playAddr can be a 1080p file hundreds of MB long. The canvas
    # player software-decodes it, so prefer an AVC/MP4 rendition near 540p.
    variants = [item for item in video.get('bitRateList', []) if isinstance(item, dict)
                and item.get('videoFormat') == 'mp4' and not item.get('isH265')
                and isinstance(item.get('playAddr'), list)]
    preferred = [item for item in variants if 480 <= int(item.get('height') or 0) <= 1024]
    if preferred:
        chosen = min(preferred, key=lambda item: int(item.get('bitRate') or 10**10))
    elif variants:
        chosen = min(variants, key=lambda item: (abs(int(item.get('height') or 0) - 960), int(item.get('bitRate') or 10**10)))
    else:
        chosen = None
    addresses = chosen['playAddr'] if chosen else video.get('playAddr', [])
    urls = [entry.get('src') for entry in addresses if isinstance(entry, dict)]
    urls = list(dict.fromkeys(u for u in urls if allowed_media(u)))
    if not urls:
        raise DouyinUnavailable('此视频未提供可播放的视频地址')
    return {'title': str(detail.get('desc') or detail.get('itemTitle') or '抖音视频')[:300],
            'urls': urls, 'duration': max(0, int(video.get('duration') or 0) / 1000)}


def _read_page(url, source, cookies):
    from curl_cffi import requests as curl_requests
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'www.douyin.com':
        raise DouyinUnavailable('无效的抖音页面地址')
    try:
        client = _visitor(cookies)
        try:
            if source is True:
                match = re.fullmatch(r'/video/(\d{15,22})', parsed.path)
                if not match:
                    raise DouyinUnavailable('无效的视频编号')
                vid = match[1]
                response = client.get(_BASE + '/jingxuan?modal_id=' + vid, timeout=25)
                if response.status_code != 200:
                    raise DouyinUnavailable('抖音视频详情暂时无法访问')
                return _source_from_render(response.text, vid)
            if source == 'comments':
                match = re.fullmatch(r'/video/(\d{15,22})', parsed.path)
                if not match:
                    raise DouyinUnavailable('无效的视频编号')
                data = _api(client, '/aweme/v1/web/comment/list/', {'aweme_id': match[1], 'cursor': '0', 'count': '50'})
                return {'items': [{'id': str(c.get('cid')), 'author': str((c.get('user') or {}).get('nickname') or '抖音用户')[:100],
                                   'text': str(c.get('text') or '')[:4000], 'likes': c.get('digg_count', 0)}
                                  for c in data.get('comments', [])[:50] if isinstance(c, dict) and c.get('cid')]}
            if parsed.path.startswith('/search/'):
                keyword = unquote(parsed.path[len('/search/'):])
                data = _api(client, '/aweme/v1/web/search/item/',
                            {'keyword': keyword, 'offset': '0', 'count': '20', 'search_source': 'normal_search'})
            elif parsed.path == '/jingxuan':
                data = _api(client, '/aweme/v1/web/tab/feed/',
                            {'count': '20', 'publish_video_strategy_type': '2'})
            else:
                raise DouyinUnavailable('无效的抖音列表地址')
            cards = {item['vid']: item for item in catalog_items(data)}
            if parsed.path == '/jingxuan' and cards:
                try:
                    related = _api(client, '/aweme/v1/web/aweme/related/',
                                   {'aweme_id': next(iter(cards)), 'count': '20'})
                    cards.update({item['vid']: item for item in catalog_items(related)})
                except DouyinUnavailable:
                    pass
            if not cards:
                raise DouyinUnavailable('抖音暂未返回公开视频列表，请稍后重试')
            return {'items': list(cards.values())[:24]}
        finally:
            client.close()
    except curl_requests.RequestsError:
        raise DouyinUnavailable('抖音网络请求超时，请稍后重试') from None
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, DouyinUnavailable):
            raise
        raise DouyinUnavailable('抖音返回了非预期内容，请稍后重试') from None
