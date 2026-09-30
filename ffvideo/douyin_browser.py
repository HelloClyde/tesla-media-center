"""Read public Douyin pages using an ordinary, short-lived browser.

Media requests are aborted before any bytes are loaded or decoded. Only page
metadata and the official player's selected URL leave this browser.
"""
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import urlsplit


class DouyinUnavailable(ValueError):
    pass


_slots = threading.BoundedSemaphore(1)
_comment_slots = threading.BoundedSemaphore(1)
_cache = {}
_cache_lock = threading.Lock()


def catalog_items(data, depth=0):
    """Extract public cards from the JSON responses used by the rendered page."""
    if depth > 10:
        return []
    if isinstance(data, list):
        return [item for value in data[:100] for item in catalog_items(value, depth + 1)]
    if not isinstance(data, dict):
        return []
    vid = str(data.get('aweme_id', ''))
    video = data.get('video')
    if re.fullmatch(r'\d{15,22}', vid) and isinstance(video, dict) and data.get('desc'):
        covers = (video.get('cover') or {}).get('url_list') or []
        return [{'vid': vid, 'title': str(data['desc'])[:300],
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
    slot = _comment_slots if source == 'comments' else _slots
    if not slot.acquire(blocking=False):
        raise DouyinUnavailable('另一个抖音页面正在加载，请稍后重试')
    try:
        result = _read_page(url, source, cookies)
        with _cache_lock:
            if len(_cache) >= 32:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (time.monotonic(), result)
        return result
    finally:
        slot.release()


def _read_page(url, source, cookies):
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError:
        raise DouyinUnavailable('抖音页面解析组件未安装，请更新服务端镜像') from None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.environ.get('TMC_DOUYIN_BROWSER_CHANNEL', 'chromium'), headless=True)
            try:
                context = browser.new_context(viewport={'width': 1280, 'height': 800}, locale='zh-CN', service_workers='block')
                if cookies:
                    context.add_cookies(cookies)
                # Prevent the official player from decoding or downloading video.
                def route_request(route):
                    if route.request.resource_type in ('media', 'image', 'font') or allowed_media(route.request.url):
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*', route_request)
                page = context.new_page()
                cards = {}
                comment_result = None
                def collect_response(response):
                    nonlocal comment_result
                    if source is True or 'application/json' not in response.headers.get('content-type', ''):
                        return
                    if urlsplit(response.url).hostname != 'www.douyin.com':
                        return
                    try:
                        data = response.json()
                        if source == 'comments':
                            if isinstance(data, dict) and isinstance(data.get('comments'), list):
                                comment_result = {'items': [
                                    {'id': str(c.get('cid', '')), 'author': str((c.get('user') or {}).get('nickname', '抖音用户'))[:100],
                                     'text': str(c.get('text', ''))[:4000], 'likes': c.get('digg_count', 0)}
                                    for c in data['comments'][:50] if isinstance(c, dict) and c.get('cid')]}
                            return
                        for item in catalog_items(data):
                            if len(cards) < 24:
                                cards[item['vid']] = item
                    except (ValueError, Error):
                        pass
                page.on('response', collect_response)
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                if source == 'comments':
                    deadline = time.monotonic() + 25
                    while comment_result is None and time.monotonic() < deadline:
                        # Some public comments are server-rendered, without a JSON request.
                        rendered = page.locator('.comment-item-info-wrap').evaluate_all("""nodes => nodes.slice(0, 50).map((node, i) => {
                            const text = el => {
                                if (!el) return '';
                                const copy = el.cloneNode(true);
                                copy.querySelectorAll('img').forEach(img => img.replaceWith(img.alt || ''));
                                return copy.textContent.trim();
                            };
                            return {id: node.querySelector('[id^="tooltip_"]')?.id || String(i),
                                author: text(node.querySelector('a')), text: text(node.nextElementSibling?.firstElementChild), likes: null};
                        }).filter(c => c.author && c.text)""")
                        if rendered:
                            comment_result = {'items': rendered}
                            break
                        if page.locator('iframe[src*="/verifycenter/captcha/"]').count():
                            raise DouyinUnavailable('评论需要抖音官方验证，请在抖音打开查看')
                        page.wait_for_timeout(250)
                    if comment_result is None:
                        raise DouyinUnavailable('抖音暂未返回评论，可重试或在抖音打开查看')
                    return comment_result
                if source:
                    page.wait_for_function(r"""() => [...document.querySelectorAll('video')].some(v => {
                        try { const u = new URL(v.currentSrc || v.src); return u.protocol === 'https:' &&
                            (/\.(zjcdn|douyinvod)\.com$/.test(u.hostname) ||
                            (u.hostname === 'www.douyin.com' && u.pathname === '/aweme/v1/play/'));
                        } catch { return false; }
                    })""", timeout=60000)
                    result = page.evaluate("""() => ({
                        title: document.querySelector('h1')?.textContent?.trim() || document.title,
                        urls: [...document.querySelectorAll('video')].map(v => v.currentSrc || v.src),
                        duration: 0
                    })""")
                    result['urls'] = list(dict.fromkeys(u for u in result['urls'] if allowed_media(u)))
                    if not result['urls']:
                        raise DouyinUnavailable('此视频未提供可转接的公开视频源')
                else:
                    deadline = time.monotonic() + 60
                    while not cards and time.monotonic() < deadline:
                        if ('验证码' in page.title() or page.locator('iframe[src*="/verifycenter/captcha/"]').count()):
                            raise DouyinUnavailable('抖音要求官方验证码，当前无法加载此列表。请使用精选或分享链接播放')
                        page.wait_for_timeout(250)
                    result = {'items': list(cards.values())}
                    if not result['items']:
                        raise DouyinUnavailable('抖音暂未返回公开视频列表，请稍后重试或粘贴分享链接')
                return result
            finally:
                browser.close()
    except Error:
        raise DouyinUnavailable('抖音页面暂时无法加载，可能需要官方验证；请稍后重试') from None
