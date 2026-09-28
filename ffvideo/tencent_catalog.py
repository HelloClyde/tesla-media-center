"""Normalize the public Tencent web catalog without forwarding tracking payloads."""
import html
import json
import re
from urllib.parse import urlsplit

import requests

API = 'https://pbaccess.video.qq.com/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
    'Referer': 'https://v.qq.com/', 'Origin': 'https://v.qq.com',
}


def text(value):
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()[:300]


def image_url(value):
    value = str(value or '')
    if value.startswith('//'):
        value = 'https:' + value
    value = value.replace('http://', 'https://', 1)
    parsed = urlsplit(value)
    if parsed.scheme == 'https' and not parsed.username and (parsed.hostname or '').endswith(('.qpic.cn', '.gtimg.cn')):
        return value
    return ''


def vid(value):
    return str(value) if re.fullmatch(r'[A-Za-z0-9]{11}', str(value or '')) else ''


def card(video_id, title, cover='', subtitle='', kind='视频'):
    return {'id': video_id, 'vid': video_id, 'title': text(title) or video_id,
            'cover': image_url(cover), 'subtitle': text(subtitle), 'kind': kind, 'episodes': []}


def home_cards(payload):
    items, seen = [], set()

    def walk(node):
        if not isinstance(node, dict) or 'ad' in node.get('type', '').split('_'):
            return
        params = node.get('params') or {}
        direct = vid(params.get('vid'))
        preview = vid(params.get('cut_vid')) or vid(params.get('window_vid'))
        cid = str(params.get('cid') or '')
        series_id = 'series:' + cid if re.fullmatch(r'[A-Za-z0-9]{15}', cid) else ''
        identifier = series_id or direct or preview
        if identifier and params.get('title') and identifier not in seen:
            seen.add(identifier)
            item = card('' if series_id else identifier, params['title'], params.get('image_url') or params.get('pic_hz'),
                        params.get('sub_title') or params.get('subtitle'), '选集' if series_id else '视频' if direct else '预告 / 片段')
            if series_id:
                item.update(id=series_id, cid=cid)
            items.append(item)
        for name, group in (node.get('children_list') or {}).items():
            if 'ad' not in name.split('_'):
                for child in group.get('cards') or []:
                    walk(child)

    for node in payload.get('CardList') or []:
        walk(node)
    return items


def episode_tags(episode):
    # Use Tencent's display labels: payStatus alone does not determine the badge.
    labels = episode.get('markLabel') or {}
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except (ValueError, TypeError):
            return []
    if not isinstance(labels, dict):
        return []
    tags = []
    for label in labels.values():
        info = label.get('info') if isinstance(label, dict) else None
        if not isinstance(info, dict):
            continue
        value = text(info.get('text'))[:24]
        if value and not value.isdigit() and value not in tags:
            tags.append(value)
    return tags[:4]


def search_cards(payload):
    items, seen = [], set()

    def walk(node):
        if isinstance(node, dict):
            info = node.get('videoInfo') or {}
            doc = node.get('doc') or {}
            identifier = vid(doc.get('id'))
            if info and identifier and info.get('videoDoc'):
                if identifier not in seen:
                    seen.add(identifier)
                    items.append(card(identifier, info.get('title'), info.get('imgUrl'),
                                      info.get('subTitle') or info.get('views')))
            elif info and info.get('coverDoc'):
                episodes = []
                episode_ids = set()
                for site in info.get('episodeSites') or []:
                    if site.get('enName') != 'qq':
                        continue
                    for episode in site.get('episodeInfoList') or []:
                        ep_id = vid(episode.get('id'))
                        if ep_id and ep_id not in episode_ids:
                            episode_ids.add(ep_id)
                            episode_card = card(ep_id, episode.get('title'), episode.get('imgUrl'))
                            episode_card['tags'] = episode_tags(episode)
                            episodes.append(episode_card)
                key = str(doc.get('id') or '')
                if episodes and key not in seen:
                    seen.add(key)
                    item = card('', info.get('title'), info.get('imgUrl'), info.get('subTitle'), '选集')
                    item.update(id='series:' + key, episodes=episodes)
                    items.append(item)
            for key, value in node.items():
                if key not in ('videoInfo', 'reportData', 'adBanner', 'adPoster'):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload.get('normalList') or {})
    walk(payload.get('areaBoxList') or [])
    return items


def call(path, body):
    with requests.post(API + path, json=body, headers=HEADERS, timeout=(5, 15)) as response:
        response.raise_for_status()
        result = response.json()
    data = result.get('data')
    if not isinstance(data, dict) or data.get('errcode', 0) != 0 or result.get('ret', 0) != 0:
        raise ValueError('腾讯视频目录暂时不可用，请稍后重试')
    return data


def get_home(context=None):
    params = {'page_type': 'channel', 'page_id': '100101', 'scene': 'channel', 'new_mark_label_enabled': '1'}
    return call('trpc.vector_layout.page_view.PageService/getPage?video_appid=3000010&vversion_platform=2', {
        'page_params': params, 'page_context': context,
        'page_bypass_params': {'params': dict(params, platform_id='2', caller_id='3000010',
                                             data_mode='default', user_mode='default', specified_strategy=''),
                               'scene': 'channel', 'app_version': '', 'abtest_bypass_id': ''},
    })


def get_search(query, page):
    return call('trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch?vversion_platform=2', {
        'query': query, 'pagenum': page, 'pagesize': 30, 'queryFrom': 3 if page else 0,
        'isneedQc': True, 'clientType': 1, 'filterValue': '',
        'featureList': ['DEFAULT_FEFEATURE', 'PC_SHORT_VIDEOS_WATERFALL'],
        'extraInfo': {'multi_terminal_pc': '1'},
    })
