"""Playback metadata only: never fetch, cache or relay media bytes here."""

import re
from urllib.parse import urlsplit


def _track(track):
    segment = track.get('SegmentBase') or track.get('segment_base') or {}
    initialization = segment.get('Initialization') or segment.get('initialization')
    index_range = segment.get('indexRange') or segment.get('index_range')
    for value in (initialization, index_range):
        if not isinstance(value, str) or not re.fullmatch(r'\d+-\d+', value):
            raise ValueError('源流缺少有效的 DASH 分段索引')
        start, end = map(int, value.split('-'))
        if end < start or end - start >= 4 * 1024 * 1024:
            raise ValueError('源流的 DASH 分段索引过大')

    urls = []
    candidates = [track.get('baseUrl') or track.get('base_url')]
    candidates += track.get('backupUrl') or track.get('backup_url') or []
    for url in candidates:
        if not isinstance(url, str):
            continue
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        parsed = urlsplit(url)
        if parsed.scheme == 'https' and parsed.hostname and not parsed.username and url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError('源流缺少可用的 HTTPS 地址')
    return {
        'urls': urls,
        'codec': track.get('codecs', ''),
        'initialization': initialization,
        'indexRange': index_range,
    }


def build_direct_source(data, max_quality):
    data = data.get('video_info') or data
    dash = data.get('dash') or {}
    videos = [t for t in dash.get('video', [])
              if str(t.get('codecs', '')).startswith('avc1.')
              and int(t.get('id', 0)) <= max_quality]
    audios = [t for t in dash.get('audio', [])
              if str(t.get('codecs', '')).startswith('mp4a.40.')]
    if not videos or not audios:
        raise ValueError('当前视频没有可直连的 H264/AAC DASH 源流，请使用兼容播放')
    selected_video = max(videos, key=lambda t: (int(t['id']), int(t.get('bandwidth', 0))))
    selected_audio = max(audios, key=lambda t: int(t.get('bandwidth', 0)))
    duration = int(data.get('timelength') or float(dash.get('duration', 0)) * 1000)
    if duration <= 0:
        raise ValueError('源流缺少有效时长')
    return {
        'mode': 'dash-direct',
        'duration': duration,
        'quality': selected_video['id'],
        'video': _track(selected_video),
        'audio': _track(selected_audio),
    }
