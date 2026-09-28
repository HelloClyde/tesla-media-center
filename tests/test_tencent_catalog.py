import unittest
from unittest.mock import patch
from flask import Flask
with patch('os.mkfifo', create=True):
    from ffvideo.tencent_catalog import home_cards, search_cards, episode_tags
    from ffvideo.tencent_video import add_routes


class CatalogTest(unittest.TestCase):
    def test_official_badges_not_payment_code(self):
        self.assertEqual(episode_tags({'payStatus': '8'}), [])
        self.assertEqual(episode_tags({'payStatus': '8', 'markLabel': '{"2":{"info":{"text":"VIP"}}}'}), ['VIP'])
        self.assertEqual(episode_tags({'markLabel': {'2': {'info': {'text': 'SVIP'}}}}), ['SVIP'])
        for value in ('invalid', '[]', 'null', {'2': None}):
            self.assertEqual(episode_tags({'markLabel': value}), [])

    def test_home_skips_ads_and_labels_preview_without_changing_id(self):
        video = {'type': 'pc_video', 'params': {'vid': 'q326831cny0', 'title': 'Video', 'image_url': 'http://puui.qpic.cn/a.jpg'}}
        preview = {'type': 'pc_shelves', 'params': {'cut_vid': 'o3013za7cse', 'title': 'Preview'}}
        ad = {'type': 'pc_card_ad', 'params': {'vid': 'x1234567890', 'title': 'Ad'}}
        results = home_cards({'CardList': [video, preview, ad, video]})
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['cover'], 'https://puui.qpic.cn/a.jpg')
        self.assertEqual(results[1]['kind'], '预告 / 片段')

    def test_home_prefers_series_over_preview(self):
        result = home_cards({'CardList': [{'params': {'cid': 'mzc00200803dr6b', 'cut_vid': 'o3013za7cse', 'title': 'Series'}}]})
        self.assertEqual(result[0]['id'], 'series:mzc00200803dr6b')
        self.assertEqual(result[0]['vid'], '')
        self.assertEqual(result[0]['kind'], '选集')

    def test_search_nested_cards_and_tencent_episodes_only(self):
        short = {'doc': {'id': 'q326831cny0'}, 'videoInfo': {'videoDoc': {'timeLong': 1}, 'title': '<em>Test</em> &amp; more', 'imgUrl': 'javascript:alert(1)'}}
        series = {'doc': {'id': 'series1'}, 'videoInfo': {'coverDoc': {'timeLong': 0}, 'title': 'Series', 'episodeSites': [
            {'enName': 'other', 'episodeInfoList': [{'id': 'x1234567890'}]},
            {'enName': 'qq', 'episodeInfoList': [{'id': 'o3013za7cse', 'title': 'Episode', 'payStatus': 8}]},
        ]}}
        result = search_cards({'normalList': {'itemList': [short]}, 'areaBoxList': [{'itemList': [series, short]}]})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['title'], 'Test & more')
        self.assertEqual(result[0]['cover'], '')
        self.assertEqual(result[1]['vid'], '')
        self.assertEqual(result[1]['episodes'][0]['subtitle'], '')
        self.assertEqual([e['vid'] for e in result[1]['episodes']], ['o3013za7cse'])

    def test_auth_validation_and_pagination(self):
        app = Flask(__name__); app.secret_key = 'test'; add_routes(app); client = app.test_client()
        self.assertEqual(client.get('/api/tencent-video/home').json['status'], 'need_login')
        with client.session_transaction() as session: session['last_visit'] = 1
        with patch('ffvideo.tencent_catalog.get_home', return_value={'CardList': [], 'has_next_page': True, 'page_context': {'page_index': '1'}}) as home:
            first = client.get('/api/tencent-video/home').json['data']
            client.get('/api/tencent-video/home', query_string={'cursor': first['nextCursor']})
            home.assert_called_with({'page_index': '1'})
            self.assertEqual(client.get('/api/tencent-video/home?cursor=forged').status_code, 400)
        with patch('ffvideo.tencent_catalog.get_search', return_value={'normalList': {'itemList': [{}], 'totalNum': 60}}) as search:
            first = client.get('/api/tencent-video/search?q=test').json['data']
            self.assertEqual(first['nextPage'], 1)
            second = client.get('/api/tencent-video/search?q=test&page=1').json['data']
            self.assertIsNone(second['nextPage'])
            search.assert_called_with('test', 1)
            for query in ('q=', 'q=a&page=-1', 'q=a&page=no'):
                self.assertEqual(client.get('/api/tencent-video/search?' + query).status_code, 400)
