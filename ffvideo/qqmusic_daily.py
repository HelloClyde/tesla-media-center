"""Daily playlist discovery from QQ Music's account-specific desktop homepage.

Reference: https://github.com/jsososo/QQMusicApi/blob/master/routes/recommend.js
Keep this separate from the unrelated guess-you-like radio API.
"""
from html.parser import HTMLParser
import re

from qqmusic_api.modules._base import ApiModule


class DailyPlaylistParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        parent = self.stack[-1] if self.stack else {}
        scope = 'mod_for_u' in classes or parent.get('scope', False)
        item = parent.get('item')
        if scope and 'playlist__item' in classes:
            item = {'title': '', 'id': ''}
            self.items.append(item)
        title = 'playlist__name' in classes or parent.get('title', False)
        if item is not None and 'playlist__link' in classes:
            item['id'] = attrs.get('data-rid', '')
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append({'tag': tag, 'scope': scope, 'item': item, 'title': title})

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1]['title'] and self.stack[-1]['item'] is not None:
            self.stack[-1]['item']['title'] += data


def daily_playlist_id(html):
    parser = DailyPlaylistParser()
    parser.feed(html)
    for item in parser.items:
        title = re.sub(r'\s+', '', item['title'])
        if title in ('今日私享', '每日30首', '每日推荐') and re.fullmatch(r'[1-9][0-9]{0,19}', item['id']):
            return int(item['id'])
    return None


class DailyApi(ApiModule):
    async def playlist_id(self):
        response = await self._build_http(
            'GET', 'https://c.y.qq.com/node/musicmac/v6/index.html',
            disable_parse=True, allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError('Daily homepage unavailable')
        # This page declares UTF-8; do not rely on the HTTP text default.
        return daily_playlist_id(response.content.decode('utf-8', errors='replace'))
