import unittest
from unittest.mock import patch, Mock
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.tencent_video import video_id, parse_source, add_routes


def data():
    return {'em': 0, 'fl': {'fi': [{'drm': 0}]}, 'vl': {'vi': [{
        'ti': 'Test video', 'td': '12', 'fn': 'test.mp4', 'fvkey': 'key',
        'cl': {'fc': 0}, 'ul': {'ui': [{'url': 'https://omex.tc.qq.com/'},
                                     {'url': 'http://127.0.0.1/'}]},
    }]}}


class TencentTest(unittest.TestCase):
    def test_link_formats_and_untrusted_hosts(self):
        for value in ('q326831cny0', 'https://v.qq.com/x/page/q326831cny0.html',
                      'https://v.qq.com/x/cover/series/q326831cny0.html',
                      'https://v.qq.com/txp/iframe/player.html?vid=q326831cny0'):
            self.assertEqual(video_id(value), 'q326831cny0')
        for value in ('https://v.qq.com.evil.test/x/page/q326831cny0.html',
                      'https://localhost/', 'https://v.qq.com/x/cover/series.html'):
            with self.assertRaises(ValueError): video_id(value)

    def test_public_source_restrictions(self):
        self.assertEqual(len(parse_source(data(), 'q326831cny0')['urls']), 1)
        for modify in (lambda d: d.update(em=1), lambda d: d['fl']['fi'][0].update(drm=1),
                       lambda d: d['vl']['vi'][0]['cl'].update(fc=3)):
            value = data(); modify(value)
            with self.assertRaises(ValueError): parse_source(value, 'q326831cny0')

    def test_authenticated_source_and_byte_relay(self):
        import json
        app = Flask(__name__); app.secret_key = 'test'; add_routes(app)
        client = app.test_client()
        self.assertEqual(client.post('/api/tencent-video/source', json={'url': 'q326831cny0'}).json['status'], 'need_login')
        self.assertEqual(client.get('/api/tencent-video/media/forged').json['status'], 'need_login')
        with client.session_transaction() as session: session['last_visit'] = 1
        metadata = Mock(content=('QZOutputJson=' + json.dumps(data()) + ';').encode())
        manager = Mock(); manager.__enter__ = Mock(return_value=metadata); manager.__exit__ = Mock(return_value=False)
        with patch('ffvideo.tencent_video.requests.get', return_value=manager):
            result = client.post('/api/tencent-video/source', json={'url': 'q326831cny0'})
        self.assertEqual(result.status_code, 200)
        url = result.json['data']['url']
        self.assertEqual(result.json['data']['urls'], ['https://omex.tc.qq.com/test.mp4?vkey=key'])
        remote = Mock(status_code=206, headers={'Content-Length': '4', 'Content-Range': 'bytes 0-3/100'})
        remote.iter_content.return_value = [b'ab', b'cd']
        with patch('ffvideo.tencent_video.requests.get', return_value=remote) as get:
            response = client.get(url, headers={'Range': 'bytes=0-3'})
            self.assertEqual(response.data, b'abcd')
            self.assertEqual(response.status_code, 206)
            self.assertEqual(get.call_args.kwargs['headers']['Referer'], 'https://v.qq.com/')
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            response.close(); remote.close.assert_called()
            self.assertEqual(client.get(url, headers={'Range': 'bytes=0-'}).status_code, 416)
        self.assertEqual(client.get('/api/tencent-video/media/forged').status_code, 410)
