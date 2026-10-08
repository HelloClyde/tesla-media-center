import unittest
import threading
import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.douyin import add_routes, video_id, relay
    from ffvideo.douyin_browser import allowed_media, DouyinUnavailable, catalog_items, _source_from_render

VID = '7674149236469451482'
MEDIA = 'https://v95-test.douyinvod.com/test.mp4'


class DouyinTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__); self.app.secret_key = 'test'; add_routes(self.app)
        self.client = self.app.test_client()

    def login(self):
        with self.client.session_transaction() as session: session['last_visit'] = 1

    def test_server_waf_challenge_is_solved_without_executing_page_scripts(self):
        from tools.douyin.visitor_probe import waf_challenge_cookie
        prefix = b'p' * 32
        expected = hashlib.sha256(prefix + b'5').digest()
        challenge = {'v': {'a': base64.b64encode(prefix).decode().rstrip('='),
                           'c': base64.b64encode(expected).decode().rstrip('=')}}
        encoded = base64.b64encode(json.dumps(challenge).encode()).decode().rstrip('=')
        page = f'<script>var wci="_wafchallengeid",cs="{encoded}"; s256(prefix,""+i)</script>'
        cookie = json.loads(base64.b64decode(waf_challenge_cookie(page)))
        self.assertEqual(base64.b64decode(cookie['d']), b'5')
        with self.assertRaises(ValueError):
            waf_challenge_cookie(page.replace('s256(prefix,""+i)', 'unknown()'))

    def test_links(self):
        for url in (VID, f'https://www.douyin.com/video/{VID}', f'https://www.iesdouyin.com/share/video/{VID}/',
                    f'分享内容 https://www.douyin.com/video/{VID} 复制后打开', f'https://www.douyin.com/?modal_id={VID}'):
            self.assertEqual(video_id(url), VID)
        for url in ('http://localhost/', f'https://www.douyin.com.evil.test/video/{VID}',
                    f'https://user@www.douyin.com/video/{VID}', 'https://www.douyin.com/live/123'):
            with self.assertRaises(ValueError): video_id(url)

    def test_catalog_reads_official_feed_and_search_shapes(self):
        item = {'aweme_id': VID, 'desc': 'test', 'video': {'cover': {'url_list': ['https://test.byteimg.com/cover.jpg']}}}
        for response in ({'aweme_list': [item]}, {'data': [{'aweme_info': item}]}):
            cards = catalog_items(response)
            self.assertEqual(len(cards), 1); self.assertEqual(cards[0]['vid'], VID)
        self.assertEqual(catalog_items({'aweme_id': VID, 'desc': 'image post'}), [])
        camel = {'awemeId': VID, 'desc': 'server-rendered', 'video': {
            'cover': {'urlList': ['https://test.byteimg.com/cover.jpg']}}}
        self.assertEqual(catalog_items({'app': {'videoDetail': camel}})[0]['vid'], VID)

    def test_server_rendered_video_source_checks_identity_and_media(self):
        import json
        from urllib.parse import quote
        detail = {'awemeId': VID, 'desc': 'test clip', 'video': {
            'duration': 123000, 'playAddr': [{'src': 'https://evil.test/video'}, {'src': MEDIA}]}}
        page = '<script id="RENDER_DATA" type="application/json">' + quote(json.dumps({'app': {'videoDetail': detail}})) + '</script>'
        self.assertEqual(_source_from_render(page, VID), {'title': 'test clip', 'duration': 123.0, 'urls': [MEDIA]})
        with self.assertRaises(DouyinUnavailable):
            _source_from_render(page, '7690564262636408115')

    def test_selects_smaller_avc_mp4_for_canvas_player(self):
        import json
        from urllib.parse import quote
        small = 'https://v96-test.douyinvod.com/small.mp4'
        detail = {'awemeId': VID, 'desc': 'clip', 'video': {'duration': 30000,
            'playAddr': [{'src': MEDIA}], 'bitRateList': [
                {'height': 1920, 'bitRate': 1500000, 'videoFormat': 'mp4', 'isH265': 0,
                 'playAddr': [{'src': MEDIA}]},
                {'height': 1024, 'bitRate': 700000, 'videoFormat': 'mp4', 'isH265': 0,
                 'playAddr': [{'src': small}]},
                {'height': 1280, 'bitRate': 300000, 'videoFormat': 'mp4', 'isH265': 1,
                 'playAddr': [{'src': 'https://v97-test.douyinvod.com/hevc.mp4'}]}]}}
        page = '<script id="RENDER_DATA">' + quote(json.dumps({'app': {'videoDetail': detail}})) + '</script>'
        self.assertEqual(_source_from_render(page, VID)['urls'], [small])

    def test_selects_lowest_bitrate_when_only_large_renditions_exist(self):
        import json
        from urllib.parse import quote
        smaller = 'https://v96-test.douyinvod.com/low-bitrate.mp4'
        detail = {'awemeId': VID, 'video': {'duration': 30000, 'bitRateList': [
            {'height': 1280, 'bitRate': 4000000, 'videoFormat': 'mp4', 'isH265': 0,
             'playAddr': [{'src': MEDIA}]},
            {'height': 1920, 'bitRate': 900000, 'videoFormat': 'mp4', 'isH265': 0,
             'playAddr': [{'src': smaller}]}]}}
        page = '<script id="RENDER_DATA">' + quote(json.dumps({'app': {'videoDetail': detail}})) + '</script>'
        self.assertEqual(_source_from_render(page, VID)['urls'], [smaller])

    def test_short_link_rejects_external_redirect(self):
        remote = Mock(status_code=302, headers={'Location': 'http://127.0.0.1/private'})
        remote.__enter__ = Mock(return_value=remote); remote.__exit__ = Mock(return_value=False)
        with patch('ffvideo.douyin.requests.get', return_value=remote) as get:
            with self.assertRaises(ValueError): video_id('https://v.douyin.com/abc/')
            get.assert_called_once()
            self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_media_allowlist(self):
        self.assertTrue(allowed_media(MEDIA))
        self.assertTrue(allowed_media('https://v5.zjcdn.com/video'))
        for url in ('http://v5.zjcdn.com/video', 'https://127.0.0.1/video', 'https://v5.zjcdn.com.evil.test/',
                    'https://user@v5.zjcdn.com/', 'https://v5.zjcdn.com:8080/', 'https://www.douyin.com/other'):
            self.assertFalse(allowed_media(url))

    def test_auth_and_source_relay(self):
        self.assertEqual(self.client.get('/api/douyin/home').json['status'], 'need_login')
        self.assertEqual(self.client.post('/api/douyin/source', json={'url': VID}).json['status'], 'need_login')
        self.assertEqual(self.client.get('/api/douyin/media/forged').json['status'], 'need_login')
        self.login()
        source = {'title': 'test', 'duration': 0, 'urls': [MEDIA]}
        with patch('ffvideo.douyin.read_page', return_value=source):
            response = self.client.post('/api/douyin/source', json={'url': VID})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('url', source)  # Do not mutate cached metadata.
        remote = Mock(status_code=206, headers={'Content-Length': '4', 'Content-Range': 'bytes 0-3/100'})
        remote.iter_content.return_value = [b'abcd']
        with patch('ffvideo.douyin.requests.get', return_value=remote):
            result = self.client.get(response.json['data']['url'], headers={'Range': 'bytes=0-3'})
            self.assertEqual(result.status_code, 206); self.assertEqual(result.data, b'abcd')
            result.close(); remote.close.assert_called()
        self.assertEqual(self.client.get('/api/douyin/media/forged').status_code, 410)

    def test_redirect_and_ranges_are_bounded(self):
        redirect = Mock(status_code=302, headers={'Location': 'http://127.0.0.1/private'})
        with patch('ffvideo.douyin.requests.get', return_value=redirect) as get:
            self.assertEqual(relay([MEDIA], 'bytes=0-3').status_code, 502)
            get.assert_called_once(); redirect.close.assert_called()
        for requested in (None, 'bytes=0-', 'bytes=5-1', 'bytes=0-33554432'):
            self.assertEqual(relay([MEDIA], requested).status_code, 416)

    def test_source_restriction_is_explicit(self):
        self.login()
        with patch('ffvideo.douyin.read_page', side_effect=DouyinUnavailable('需要官方验证')):
            response = self.client.post('/api/douyin/source', json={'url': VID})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['message'], '需要官方验证')

    def test_search_encodes_query(self):
        self.login()
        with patch('ffvideo.douyin.read_page', return_value={'items': []}) as read:
            self.assertEqual(self.client.get('/api/douyin/search', query_string={'q': 'a/b?c'}).status_code, 200)
            self.assertEqual(read.call_args.args[0], 'https://www.douyin.com/search/a%2Fb%3Fc?type=video')
        self.assertEqual(self.client.get('/api/douyin/search?q=').status_code, 400)

    def test_catalog_cursor_is_validated_and_forwarded(self):
        self.login()
        with patch('ffvideo.douyin.read_page', return_value={'items': [], 'hasMore': True, 'nextCursor': 3}) as read:
            response = self.client.get('/api/douyin/home?cursor=2')
            self.assertEqual(response.json['data']['nextCursor'], 3)
            self.assertEqual(read.call_args.args[0], 'https://www.douyin.com/jingxuan?cursor=2')
            self.client.get('/api/douyin/search?q=test&cursor=2')
            self.assertEqual(read.call_args.args[0], 'https://www.douyin.com/search/test?type=video&cursor=2')
        self.assertEqual(self.client.get('/api/douyin/home?cursor=999').status_code, 400)

    def test_catalog_uses_later_feed_pages(self):
        from ffvideo import douyin_browser as browser
        item = {'aweme_id': VID, 'desc': 'next page', 'video': {'cover': {}}}
        last_vid = '7674149236469451483'
        last = {'aweme_id': last_vid, 'desc': 'newer seed', 'video': {'cover': {}}}
        client = Mock()
        with patch.object(browser, '_visitor', return_value=client), patch.object(browser, '_api', side_effect=[
                {'aweme_list': [item], 'has_more': 1},
                {'aweme_list': [item, last], 'has_more': 1},
                {'aweme_list': [], 'has_more': 1},
                {'aweme_list': [], 'has_more': 1}]) as api:
            result = browser._read_page('https://www.douyin.com/jingxuan?cursor=2', False, [])
        self.assertEqual([card['vid'] for card in result['items']], [VID, last_vid])
        self.assertEqual(result['nextCursor'], 6)
        self.assertTrue(result['hasMore'])
        self.assertEqual(api.call_args_list[0].args[2]['max_cursor'], '40')
        self.assertEqual(api.call_args_list[0].args[2]['refresh_index'], '2')
        self.assertEqual(api.call_args_list[-1].args[2]['refresh_index'], '5')
        self.assertTrue(all(call.args[1] == '/aweme/v1/web/tab/feed/' for call in api.call_args_list))

    def test_simultaneous_devices_share_one_page_load(self):
        from ffvideo import douyin_browser as browser
        started, release = threading.Event(), threading.Event()
        def load(*_args):
            started.set()
            self.assertTrue(release.wait(3))
            return {'items': ['shared']}
        with patch.object(browser, '_read_page', side_effect=load) as read:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(browser.read_page, 'https://example.test/shared')
                self.assertTrue(started.wait(2))
                second = pool.submit(browser.read_page, 'https://example.test/shared')
                try:
                    self.assertEqual(second.result(timeout=.05), {'items': ['shared']})
                except TimeoutError:
                    pass
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=3), {'items': ['shared']})
                self.assertEqual(second.result(timeout=3), {'items': ['shared']})
            read.assert_called_once()

    def test_distinct_devices_can_load_in_parallel(self):
        from ffvideo import douyin_browser as browser
        both_active, release = threading.Event(), threading.Event()
        lock = threading.Lock()
        active = 0
        def load(url, *_args):
            nonlocal active
            with lock:
                active += 1
                if active == 2: both_active.set()
            self.assertTrue(release.wait(3))
            return {'items': [url]}
        with patch.object(browser, '_read_page', side_effect=load):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(browser.read_page, 'https://example.test/one')
                second = pool.submit(browser.read_page, 'https://example.test/two')
                try:
                    self.assertTrue(both_active.wait(2))
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=3)['items'], ['https://example.test/one'])
                self.assertEqual(second.result(timeout=3)['items'], ['https://example.test/two'])
