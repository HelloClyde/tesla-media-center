import copy
import unittest
from unittest.mock import patch

from flask import Flask
from bilibili_api import video

with patch('os.path.exists', return_value=False), patch('os.mkfifo', create=True):
    from ffvideo.bili_source import build_direct_source
    from ffvideo.bv import add_bv_route


def track(codec, quality, **extra):
    return dict(id=quality, codecs=codec, bandwidth=128000,
                baseUrl='https://video.example.test/main.m4s',
                backupUrl=['https://video.example.test/backup.m4s'],
                SegmentBase={'Initialization': '0-999', 'indexRange': '1000-1999'}, **extra)


def source_data():
    return {'timelength': 90000, 'dash': {
        'video': [track('hev1.1', 64), track('avc1.64001f', 80), track('avc1.64001f', 64)],
        'audio': [track('mp4a.40.2', 30280)],
    }}


class DirectSourceTest(unittest.TestCase):
    def test_limits_quality_and_preserves_backups_and_index(self):
        result = build_direct_source(source_data(), 64)
        self.assertEqual(result['quality'], 64)
        self.assertEqual(result['duration'], 90000)
        self.assertEqual(len(result['video']['urls']), 2)
        self.assertEqual(result['audio']['indexRange'], '1000-1999')

    def test_bangumi_and_snake_case_fields(self):
        data = source_data()
        for item in data['dash']['video'] + data['dash']['audio']:
            item['base_url'] = item.pop('baseUrl').replace('https:', 'http:')
            item['backup_url'] = item.pop('backupUrl')
            item.pop('SegmentBase')
            item['segment_base'] = {'initialization': '0-100', 'index_range': '101-200'}
        result = build_direct_source({'video_info': data}, 64)
        self.assertTrue(result['video']['urls'][0].startswith('https://'))
        self.assertEqual(result['audio']['initialization'], '0-100')

    def test_rejects_unsupported_streams_and_bad_ranges(self):
        for modify in [lambda d: d['dash'].update(video=[]),
                       lambda d: d['dash'].update(audio=[]),
                       lambda d: d['dash']['audio'][0]['SegmentBase'].update(indexRange='200-100'),
                       lambda d: d.update(timelength=0)]:
            data = copy.deepcopy(source_data())
            modify(data)
            with self.assertRaises(ValueError):
                build_direct_source(data, 64)

    def test_source_routes_are_authenticated_and_never_start_media_jobs(self):
        app = Flask(__name__)
        app.secret_key = 'unit-test-only'
        add_bv_route(app)
        client = app.test_client()
        self.assertEqual(client.get('/api/bilibili/media-range/forged').json['status'], 'need_login')
        routes = ['/api/bilibili/bv/BV1xx411c7mD/62131/source',
                  '/api/bilibili/bangumi_ep/123/456/source']
        for path in routes:
            self.assertEqual(client.get(path).json['status'], 'need_login')
        with client.session_transaction() as session:
            session['last_visit'] = 1
        with patch('ffvideo.bv.get_bilibili_credential', return_value=None), \
             patch('ffvideo.bv.get_bilibili_max_quality', return_value=video.VideoQuality._720P), \
             patch('ffvideo.bv.video.Video') as bv, patch('ffvideo.bv.bangumi.Episode') as ep, \
             patch('ffvideo.bv.sync', return_value=source_data()), \
             patch('ffvideo.bv.subprocess.Popen') as process, \
             patch('ffvideo.bv.requests.get') as media_download, \
             patch('ffvideo.bv.get_output_video_path') as cache:
            for path in routes:
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['data']['mode'], 'dash-direct')
                self.assertIn('no-store', response.headers['Cache-Control'])
            bv.return_value.get_download_url.assert_called_once_with(cid=62131)
            ep.return_value.get_download_url.assert_called_once_with()
            proxied = client.get(routes[0] + '?transport=relay').json['data']
            self.assertTrue(proxied['video']['urls'][0].startswith('/api/bilibili/media-range/'))
            self.assertTrue(proxied['audio']['urls'][0].startswith('/api/bilibili/media-range/'))
            process.assert_not_called()
            media_download.assert_not_called()
            cache.assert_not_called()


if __name__ == '__main__':
    unittest.main()
