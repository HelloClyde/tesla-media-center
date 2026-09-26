"""Offline contract tests: auth isolation, QR lifecycle and private credential storage."""
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from flask import Flask
from qqmusic_api import Credential
from qqmusic_api.models.login import QRLoginType
from ffvideo import qqmusic


class QQMusicTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = patch.object(qqmusic, 'STORE', Path(self.directory.name))
        self.store.start()
        qqmusic.PENDING.clear()
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.testing = True
        qqmusic.add_qqmusic_route(self.app)
        self.client = self.app.test_client()
        self.other = self.app.test_client()
        for client in (self.client, self.other):
            with client.session_transaction() as session:
                session['last_visit'] = int(time.time())
            client.get('/api/qqmusic/account')

    def tearDown(self):
        self.store.stop()
        self.directory.cleanup()

    def test_requires_app_login(self):
        client = self.app.test_client()
        for method, path in [('get', 'singer-profile?id=test'), ('get', 'browse?kind=tops'), ('get', 'suggestions?q=x'), ('get', 'comments?mid=x'), ('get', 'mv?id=x'), ('get', 'word-lyrics?mid=x'), ('post', 'collection'), ('get', 'lyrics?mid=test'), ('get', 'account'), ('get', 'daily'), ('get', 'library'), ('get', 'recommend'), ('get', 'search?q=test'), ('get', 'play?mid=test'),
                             ('post', 'login'), ('post', 'login/status'), ('post', 'logout')]:
            self.assertEqual(getattr(client, method)('/api/qqmusic/' + path).json['status'], 'need_login')

    def test_invalid_input_does_not_call_upstream(self):
        with patch.object(qqmusic, 'run') as run:
            for path in ['lyrics?mid=../bad', 'search?q=&page=1', 'search?q=test&page=0', 'play?mid=../../config.json', 'play?mid=test&quality=invalid']:
                self.assertEqual(self.client.get('/api/qqmusic/' + path).status_code, 400)
            run.assert_not_called()

    def test_collection_login_validation_and_ownership(self):
        with patch.object(qqmusic, 'run') as run:
            self.assertEqual(self.client.post('/api/qqmusic/collection', json={'action': 'like', 'mid': 'test'}).status_code, 400)
            run.assert_not_called()
        cred = SimpleNamespace(musicid=123)
        songlist = SimpleNamespace(like_song=AsyncMock(return_value=True), add_songs=AsyncMock())
        upstream = SimpleNamespace(song=SimpleNamespace(get_detail=AsyncMock(return_value=SimpleNamespace(track=SimpleNamespace(id=42, type=1)))), songlist=songlist,
            user=SimpleNamespace(get_created_songlist=AsyncMock(return_value=SimpleNamespace(playlists=[]))))
        with patch.object(qqmusic, 'credential', return_value=cred), patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(upstream))):
            response = self.client.post('/api/qqmusic/collection', json={'action': 'like', 'mid': 'test'})
            self.assertEqual(response.json['status'], 'ok')
            songlist.like_song.assert_awaited_once_with([(42, 1)], credential=cred)
            self.assertEqual(self.client.post('/api/qqmusic/collection', json={'action': 'add', 'mid': 'test', 'playlist': '999'}).status_code, 400)
            songlist.add_songs.assert_not_called()
            self.assertEqual(self.client.post('/api/qqmusic/collection', json={'action': 'delete'}).status_code, 400)

    def test_create_playlist_model_and_failed_mutation(self):
        from qqmusic_api.models.songlist import CreateDeleteSonglistResp
        cred = SimpleNamespace(musicid=123)
        created = CreateDeleteSonglistResp.model_validate({'retCode': 0, 'result': {'tid': 77, 'dirId': 2, 'dirName': 'test'}})
        upstream = SimpleNamespace(songlist=SimpleNamespace(create=AsyncMock(return_value=created)))
        with patch.object(qqmusic, 'credential', return_value=cred), patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(upstream))):
            response = self.client.post('/api/qqmusic/collection', json={'action': 'create', 'name': 'test'})
            self.assertEqual(response.json['data'], {'created': True})
            self.assertEqual(self.client.post('/api/qqmusic/collection', json={'action': 'create', 'name': ' '}).status_code, 400)

    def test_singer_profile_and_album_tab(self):
        person = SimpleNamespace(basic_info=SimpleNamespace(name='歌手', cover_url=lambda: 'https://example.com/cover'), pic=SimpleNamespace(pic=''), ex_info=SimpleNamespace(desc='简介', area='地区', genre='流行'))
        album = SimpleNamespace(mid='album1', name='专辑', cover_url=lambda: '', time_public='2026-01-01')
        singer = SimpleNamespace(get_desc=AsyncMock(return_value=SimpleNamespace(singer_list=[person])), get_album_list=AsyncMock(return_value=SimpleNamespace(album_list=[album], total=21)))
        with patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(SimpleNamespace(singer=singer)))):
            response = self.client.get('/api/qqmusic/singer-profile?id=singer1')
            self.assertEqual(response.json['data']['description'], '简介')
            result = self.client.get('/api/qqmusic/browse?kind=singer-albums&id=singer1').json['data']
            self.assertEqual(result['items'][0]['kind'], 'album')
            self.assertTrue(result['more'])
            self.assertEqual(self.client.get('/api/qqmusic/singer-profile?id=../bad').status_code, 400)

    def test_top_details_keep_update_metadata(self):
        info = SimpleNamespace(name='热歌榜', front_pic_url='', intro='介绍', update_time='2026-09-26', period='2026_39', total_num=40)
        top = SimpleNamespace(get_detail=AsyncMock(return_value=SimpleNamespace(info=info, songs=[])))
        with patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(SimpleNamespace(top=top)))):
            data = self.client.get('/api/qqmusic/browse?kind=top&id=26').json['data']
            self.assertEqual(data['info']['updated'], '2026-09-26')
            self.assertTrue(data['more'])

    def test_browse_album_and_pagination(self):
        upstream = SimpleNamespace(album=SimpleNamespace(get_song=AsyncMock(return_value=SimpleNamespace(song_list=[], total_num=80))))
        with patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(upstream))):
            response = self.client.get('/api/qqmusic/browse?kind=album&id=test&page=2')
            self.assertTrue(response.json['data']['more'])
            upstream.album.get_song.assert_awaited_once_with('test', num=30, page=2)
            self.assertEqual(self.client.get('/api/qqmusic/browse?kind=album&id=../bad').status_code, 400)

    def test_highest_source_quality(self):
        from qqmusic_api.models.base import File
        for payload, expected in [({}, 'unknown'), ({'size_try': 100}, 'unknown'),
                                  ({'size_128mp3': 100}, 'standard'),
                                  ({'size_320mp3': 100, 'size_128mp3': 100}, 'high'),
                                  ({'size_flac': 100, 'size_320mp3': 100}, 'lossless'),
                                  ({'size_new': [0, 0, 0, 0, 0, 100]}, 'lossless'),
                                  ({'size_new': [0, 100], 'size_flac': 100}, 'premium'),
                                  ({'size_new': [100, 100], 'size_flac': 100}, 'master')]:
            with self.subTest(payload=payload):
                self.assertEqual(qqmusic.song_max_quality(SimpleNamespace(file=File.model_validate(payload))), expected)
        self.assertEqual(qqmusic.song_max_quality(SimpleNamespace()), 'unknown')

    def test_lyrics_returns_decoded_text(self):
        with patch.object(qqmusic, 'run', return_value=SimpleNamespace(lyric='[00:01.00]hello', trans='[00:01.00]你好')):
            result = self.client.get('/api/qqmusic/lyrics?mid=abc123')
            self.assertEqual(result.json['data'], {'lyric': '[00:01.00]hello', 'translation': '[00:01.00]你好'})

    def test_recommend_requires_music_account(self):
        with patch.object(qqmusic, 'run') as run:
            result = self.client.get('/api/qqmusic/recommend')
            self.assertEqual(result.json['data'], {'songs': [], 'loginRequired': True})
            run.assert_not_called()

    def test_daily_playlist_discovery(self):
        from ffvideo.qqmusic_daily import daily_playlist_id
        card = '<li class="playlist__item"><a class="playlist__link" data-rid="123"><img src="x"></a><h3 class="playlist__name"><a> 今日私享 </a></h3></li>'
        self.assertIsNone(daily_playlist_id(card))
        self.assertEqual(daily_playlist_id('<div class="mod_for_u"><ul>' + card + '</ul></div>'), 123)
        self.assertIsNone(daily_playlist_id('<div class="mod_for_u">' + card.replace('今日私享', '热门歌单') + '</div>'))
        self.assertIsNone(daily_playlist_id('<div class="mod_for_u">' + card.replace('123', '../abc') + '</div>'))

    def test_membership_levels_and_unknown(self):
        from qqmusic_api.models.user import UserVipInfoResponse
        for payload, label, level in [({'svip': 1, 'identity': {'level': 6}}, '超级会员', 6),
                                      ({'identity': {'HugeVip': 1, 'level': 3}}, '豪华绿钻', 3),
                                      ({'identity': {'vip': 0, 'HugeVip': 0}}, '普通用户', None),
                                      ({}, '会员状态未知', None)]:
            with self.subTest(payload=payload), patch.object(qqmusic, 'credential', return_value=object()), patch.object(
                qqmusic, 'run', return_value=UserVipInfoResponse.model_validate(payload)
            ):
                data = self.client.get('/api/qqmusic/membership').json['data']
                self.assertEqual((data['label'], data['level']), (label, level))

    def test_song_playback_rights_not_download_rights(self):
        from qqmusic_api.models.base import Pay
        for payload, access in [({'pay_month': 1}, 'vip'),
                                 ({'pay_play': 1, 'price_album': 100}, 'purchase'),
                                 ({'pay_play': 1}, 'paid'),
                                 ({'pay_play': 0, 'pay_month': 0, 'pay_down': 1}, 'standard'),
                                 ({}, 'unknown')]:
            song = SimpleNamespace(mid='s', title='歌曲', name='歌曲', singer=[], interval=100,
                album=SimpleNamespace(title='', cover_url=lambda: ''), pay=Pay.model_validate(payload))
            with self.subTest(payload=payload), patch.object(qqmusic, 'credential', return_value=object()), patch.object(
                qqmusic, 'run', return_value=SimpleNamespace(songs=[song])
            ):
                self.assertEqual(self.client.get('/api/qqmusic/recommend').json['data']['songs'][0]['access'], access)

    def test_daily_uses_discovered_playlist_not_guess_radio(self):
        with patch.object(qqmusic, 'run') as run:
            self.assertTrue(self.client.get('/api/qqmusic/daily').json['data']['loginRequired'])
            run.assert_not_called()
        detail = SimpleNamespace(code=0, subcode=0, songs=[])
        songlist = SimpleNamespace(get_detail=AsyncMock(return_value=detail))
        with patch.object(qqmusic, 'credential', return_value=object()), patch.object(
            qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(SimpleNamespace(songlist=songlist, _session=None)))
        ), patch.object(qqmusic.DailyApi, 'playlist_id', new_callable=AsyncMock, return_value=123) as discover:
            response = self.client.get('/api/qqmusic/daily')
            self.assertEqual(response.json['data'], {'songs': [], 'loginRequired': False})
            songlist.get_detail.assert_awaited_once_with(123, num=100)
            discover.return_value = None
            self.assertEqual(self.client.get('/api/qqmusic/daily').status_code, 400)
            self.assertEqual(songlist.get_detail.await_count, 1)

    def test_library_validation_and_login(self):
        with patch.object(qqmusic, 'run') as run:
            for query in ['kind=invalid', 'page=0', 'page=abc', 'kind=playlist&id=../foo']:
                self.assertEqual(self.client.get('/api/qqmusic/library?' + query).status_code, 400)
            self.assertTrue(self.client.get('/api/qqmusic/library').json['data']['loginRequired'])
            run.assert_not_called()

    def test_library_account_pagination_and_playlist_id(self):
        cred = SimpleNamespace(encrypt_uin='private-encrypted-user', musicid=123)
        detail = SimpleNamespace(songs=[], code=0, subcode=0, hasmore=1)
        playlist = SimpleNamespace(id=999, dirid=7, title='歌单', picurl='', songnum=3)
        user = SimpleNamespace(get_fav_song=AsyncMock(return_value=detail),
            get_fav_songlist=AsyncMock(return_value=SimpleNamespace(playlists=[playlist], hasmore=1)),
            get_created_songlist=AsyncMock(return_value=SimpleNamespace(playlists=[playlist], finished=True)))
        songlist = SimpleNamespace(get_detail=AsyncMock(return_value=detail))
        upstream = SimpleNamespace(user=user, songlist=songlist)
        with patch.object(qqmusic, 'credential', return_value=cred), patch.object(
            qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(upstream))
        ):
            response = self.client.get('/api/qqmusic/library?kind=songs&page=2&uin=other')
            self.assertTrue(response.json['data']['more'])
            user.get_fav_song.assert_awaited_once_with(cred.encrypt_uin, page=2, num=30, credential=cred)
            response = self.client.get('/api/qqmusic/library?kind=playlists&page=2')
            self.assertEqual(response.json['data']['playlists'][0]['id'], '999')
            user.get_fav_songlist.assert_awaited_once_with(cred.encrypt_uin, page=2, num=30, credential=cred)
            response = self.client.get('/api/qqmusic/library?kind=created')
            self.assertFalse(response.json['data']['more'])
            user.get_created_songlist.assert_awaited_once_with(123, credential=cred)
            self.client.get('/api/qqmusic/library?kind=playlist&id=999&page=3')
            songlist.get_detail.assert_awaited_once_with(999, page=3, num=30)

    def test_recommend_maps_real_song_model(self):
        from qqmusic_api.models.recommend import GuessRecommendResponse
        result = GuessRecommendResponse.model_validate({'tracks': [{
            'id': 1, 'type': 0, 'mv': {}, 'file': {}, 'pay': {},
            'isonly': 0, 'language': 0, 'genre': 0, 'index_cd': 0, 'index_album': 0,
            'status': 0, 'label': '', 'bpm': 0, 'ov': 0, 'sa': 0, 'es': '',
            'vs': [], 'vi': [], 'vf': [],
            'mid': 'testmid', 'name': '歌曲', 'title': '推荐歌曲', 'interval': 123,
            'singer': [{'name': '歌手'}], 'album': {'title': '专辑', 'mid': 'albumid'}
        }]})
        recommend = SimpleNamespace(get_guess_recommend=AsyncMock(return_value=result))
        with patch.object(qqmusic, 'credential', return_value=object()), patch.object(
            qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(SimpleNamespace(recommend=recommend)))
        ):
            response = self.client.get('/api/qqmusic/recommend')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['data']['loginRequired'])
        song = response.json['data']['songs'][0]
        self.assertEqual((song['mid'], song['title'], song['singer'], song['duration']),
                         ('testmid', '推荐歌曲', '歌手', 123))
        self.assertTrue(song['cover'].startswith('https://'))
        recommend.get_guess_recommend.assert_awaited_once()

    def test_quality_and_unavailable_source(self):
        file = SimpleNamespace(media_mid='media', size_128mp3=100, size_320mp3=200, size_flac=300, size_new=[400, 350])
        song = SimpleNamespace(
            get_detail=AsyncMock(return_value=SimpleNamespace(track=SimpleNamespace(file=file))),
            get_song_urls=AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(purl='song.mp3')])) ,
            get_cdn_dispatch=AsyncMock(return_value=SimpleNamespace(sip=['https://sjy6.stream.qqmusic.qq.com/'])))
        client = SimpleNamespace(song=song)
        with patch.object(qqmusic, 'run', side_effect=lambda sid, operation: asyncio.run(operation(client))):
            for quality, (file_type, _, _) in qqmusic.QUALITIES.items():
                result = self.client.get('/api/qqmusic/play?mid=test&quality=' + quality)
                self.assertEqual(result.json['data']['quality'], quality)
                self.assertEqual(song.get_song_urls.call_args.kwargs['file_type'], file_type)
            song.get_song_urls.reset_mock()
            file.size_flac = 0
            self.assertEqual(self.client.get('/api/qqmusic/play?mid=test&quality=lossless').status_code, 400)
            song.get_song_urls.assert_not_called()

    def test_login_provider_selection_and_replacement(self):
        login = SimpleNamespace(get_qrcode=AsyncMock(side_effect=lambda kind: SimpleNamespace(
            data=b'qr', mimetype='image/png', qr_type=kind)))
        upstream = SimpleNamespace(login=login)
        with patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(upstream))):
            old = self.client.post('/api/qqmusic/login', json={}).json['data']['token']
            login.get_qrcode.assert_awaited_with(QRLoginType.QQ)
            new = self.client.post('/api/qqmusic/login', json={'provider': 'wx'}).json['data']['token']
            login.get_qrcode.assert_awaited_with(QRLoginType.WX)
        with patch.object(qqmusic, 'run') as run:
            self.assertEqual(self.client.post('/api/qqmusic/login/status', json={'token': old}).json['data']['state'], 'TIMEOUT')
            run.assert_not_called()
        login.check_qrcode = AsyncMock(return_value=SimpleNamespace(event=SimpleNamespace(name='CONF')))
        with patch.object(qqmusic, 'run', side_effect=lambda sid, op: asyncio.run(op(upstream))):
            self.assertEqual(self.client.post('/api/qqmusic/login/status', json={'token': new}).json['data']['state'], 'CONF')
        self.assertEqual(login.check_qrcode.call_args.args[0].qr_type, QRLoginType.WX)

    def test_invalid_login_provider(self):
        with patch.object(qqmusic, 'run') as run:
            for body in [{'provider': 'invalid'}, {'provider': []}, {'provider': None}, ['wx']]:
                with self.subTest(body=body):
                    self.assertEqual(self.client.post('/api/qqmusic/login', json=body).status_code, 400)
            run.assert_not_called()

    def test_failed_provider_switch_invalidates_old_qr(self):
        qr = SimpleNamespace(data=b'qr', mimetype='image/png')
        with patch.object(qqmusic, 'run', return_value=qr):
            token = self.client.post('/api/qqmusic/login', json={}).json['data']['token']
        with patch.object(qqmusic, 'run', side_effect=RuntimeError('upstream unavailable')):
            self.assertEqual(self.client.post('/api/qqmusic/login', json={'provider': 'wx'}).status_code, 502)
        with patch.object(qqmusic, 'run') as run:
            self.assertEqual(self.client.post('/api/qqmusic/login/status', json={'token': token}).json['data']['state'], 'TIMEOUT')
            run.assert_not_called()

    def test_login_isolation_encryption_and_logout(self):
        qr = SimpleNamespace(data=b'qr', mimetype='image/png')
        with patch.object(qqmusic, 'run', return_value=qr):
            response = self.client.post('/api/qqmusic/login', json={'provider': 'wx'})
            token = response.json['data']['token']
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.other.post('/api/qqmusic/login/status', json={'token': token}).json['data']['state'], 'TIMEOUT')
        cred = Credential(musicid=123, musickey='private-music-key', musickeyCreateTime=int(time.time()), keyExpiresIn=3600)
        result = SimpleNamespace(event=SimpleNamespace(name='DONE'), credential=cred)
        with patch.object(qqmusic, 'run', return_value=result):
            self.assertEqual(self.client.post('/api/qqmusic/login/status', json={'token': token}).json['data']['state'], 'DONE')
        data = self.client.get('/api/qqmusic/account').json['data']
        self.assertEqual(data, {'loggedIn': True, 'account': '123'})
        self.assertFalse(self.other.get('/api/qqmusic/account').json['data']['loggedIn'])
        self.assertNotIn(b'private-music-key', next(Path(self.directory.name).iterdir()).read_bytes())
        self.client.post('/api/qqmusic/logout', json={})
        self.assertFalse(self.client.get('/api/qqmusic/account').json['data']['loggedIn'])

    def test_upstream_errors_do_not_leak_credentials(self):
        with patch.object(qqmusic, 'run', side_effect=RuntimeError('secret-token')):
            result = self.client.post('/api/qqmusic/login', json={})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('secret-token', result.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
