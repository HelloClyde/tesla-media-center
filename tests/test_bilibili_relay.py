import unittest
from unittest.mock import Mock, patch
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.bili_relay import media_range, relay_source, signer


class RelayTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-relay'
        self.urls = ['https://a.bilivideo.com/video', 'https://b.bilivideo.cn/video']

    def test_manifest_uses_signed_same_origin_tracks(self):
        data = {kind: {'urls': self.urls} for kind in ('video', 'audio')}
        result = relay_source(self.app, data)
        token = result['video']['urls'][0].split('/')[-1]
        self.assertEqual(signer(self.app).loads(token), self.urls)

    def test_streams_exact_bytes_and_closes_upstream_with_fallback(self):
        bad = Mock(status_code=403)
        good = Mock(status_code=206, headers={'Content-Range': 'bytes 0-3/100'})
        good.iter_content.return_value = [b'ab', b'cd']
        with self.app.test_request_context(headers={'Range': 'bytes=0-3'}), \
                patch('ffvideo.bili_relay.requests.get', side_effect=[bad, good]) as get:
            response = media_range(self.app, signer(self.app).dumps(self.urls))
            self.assertEqual(response.status_code, 206)
            self.assertEqual(b''.join(response.response), b'abcd')
            self.assertEqual(get.call_args.kwargs['headers']['Referer'], 'https://www.bilibili.com/')
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            good.close.assert_called()
            bad.close.assert_called_once()

    def test_rejects_unsigned_urls_bad_ranges_and_non_cdn(self):
        with patch('ffvideo.bili_relay.requests.get') as get:
            with self.app.test_request_context(headers={'Range': 'bytes=0-3'}):
                self.assertEqual(media_range(self.app, 'forged').status_code, 410)
                self.assertEqual(media_range(self.app, signer(self.app).dumps(['https://localhost/'])).status_code, 502)
            for value in ('', 'bytes=0-', 'bytes=0-33554432', 'bytes=4-1', 'bytes=0-1,3-4'):
                with self.app.test_request_context(headers={'Range': value}):
                    self.assertEqual(media_range(self.app, signer(self.app).dumps(self.urls)).status_code, 416)
            get.assert_not_called()

    def test_disconnect_closes_upstream(self):
        upstream = Mock(status_code=206, headers={'Content-Range': 'bytes 0-3/100'})
        upstream.iter_content.return_value = [b'ab', b'cd']
        with self.app.test_request_context(headers={'Range': 'bytes=0-3'}), \
                patch('ffvideo.bili_relay.requests.get', return_value=upstream):
            response = media_range(self.app, signer(self.app).dumps(self.urls))
            self.assertEqual(next(response.response), b'ab')
            response.close()
            upstream.close.assert_called()
