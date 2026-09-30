import unittest
from unittest.mock import Mock, patch
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.douyin import add_routes, video_id, relay
    from ffvideo.douyin_browser import allowed_media, DouyinUnavailable, catalog_items

VID = '7674149236469451482'
MEDIA = 'https://v95-test.douyinvod.com/test.mp4'


class DouyinTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__); self.app.secret_key = 'test'; add_routes(self.app)
        self.client = self.app.test_client()

    def login(self):
        with self.client.session_transaction() as session: session['last_visit'] = 1

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
