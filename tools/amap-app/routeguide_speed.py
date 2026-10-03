"""APK routeguide request and bounded decoding of verified speed-sign points.

The type-10 records in the second route response carry a posted number and a
coordinate. They are point alerts; they do not establish a continuous road
speed limit or a camera category.
"""
import base64
import hashlib
import json
import math
import secrets
import struct
import uuid
from urllib.parse import urlencode

import requests
import zstandard

from native_body_codec import encode, encode_binary
from route_v51 import delta_values, distance, fields, one, unpack
from v51_dynamic_route import extract


URL = 'https://nvg.amap.com/ws/transfer/navigation/routeguide'
MAX_RESPONSE = 2 * 1024 * 1024
MAX_UNPACKED = 2 * 1024 * 1024


def _path(route_blob, context):
    route = fields(route_blob)
    segments = [fields(item) for item in route.get(10, [])]
    counts = [len(seg.get(3, [])) for seg in segments]
    lengths = context['route_links_length_candidate']
    if not segments or sum(counts) != len(lengths):
        raise ValueError('routeguide link count mismatch')
    remaining, offset, suffix = sum(lengths), 0, []
    for count in counts:
        remaining -= sum(lengths[offset:offset + count])
        suffix.append(remaining)
        offset += count
    eta, lights = [], []
    for segment in segments:
        for blob in segment.get(3, []):
            link = fields(blob)
            if one(link, 6, 0) & 4:
                lights.append(len(eta))
            eta.append(one(link, 5, 0))
    links = context['route_links_candidate']
    coordinates = fields(one(segments[-1], 4, b''))
    xs, ys = delta_values(one(coordinates, 1, b'')), delta_values(one(coordinates, 2, b''))
    if not links or len(xs) < 2 or len(ys) != len(xs):
        raise ValueError('invalid routeguide geometry')
    start = context['route_links_start_point_candidate'][0]
    return {'pathID': context['wire_route_field6'], 'cur_seg_index': 0,
            'dataVer': str(context['eta_data_vers']), 'segments': counts,
            'mainActions': [one(seg, 1, 0) for seg in segments],
            'assistActions': [one(seg, 2, 0) for seg in segments],
            'mixFork': [], 'mixForkType': [], 'disToPathEnd': suffix,
            'eta': eta, 'trafficLight': lights, 'firstLinkID': links[0],
            'linkids': [0] + [int(delta) for delta in links[1:]],
            'start': {'lon': start[0], 'lat': start[1]},
            'end': {'lon': xs[-1], 'lat': ys[-1], 'dir': 0},
            'param': {'strategy': 0, 'playPointer': {'startSegIndex': 0, 'endSegIndex': len(segments) - 1}},
            'extendInfo': '{"labelInfo":[]}'}


def build_body(raw, assets):
    envelope = fields(unpack(raw))
    message = fields(one(envelope, 2, b''))
    blobs = message.get(7, [])
    if not 1 <= len(blobs) <= 10:
        raise ValueError('invalid routeguide route count')
    contexts = [extract(raw, i) for i in range(len(blobs))]
    paths = [_path(blob, context) for blob, context in zip(blobs, contexts)]
    if len({context['navigation_id_candidate'] for context in contexts}) != 1:
        raise ValueError('inconsistent navigation IDs')
    personal = {'broadcastText': '', 'naviId': '', 'segmentResults': [],
                'isManualDensity': False, 'isAudioTrigger': False, 'audioPlaying': False,
                'triggerSegmentIdx': 0, 'triggerSegmentDensity': 0, 'isAudioPr': 0}
    header = {'privacy': '1', 'noviceLevel': '0', 'switchStatus': '0',
              'modelLibra': '', 'clientVersion': '17.00.0', 'Mute': '0', 'MediaPlay': '0',
              'TbtExParam': json.dumps({'pathFamInfos': [
                  {'pathId': p['pathID'], 'pathFm': 0, 'co_param': ''} for p in paths]}, separators=(',', ':')),
              'agent_personalEvent': json.dumps(personal, separators=(',', ':')),
              'algParamVer': '2', 'end_poiid': '', 'tbt_lang': 'zh-CN',
              'typecode': '', 'via_poiid': '', 'via_typecode': '',
              'yaw_addvoice': '0', 'yaw_count': '0'}
    params = {'dataFlag': 11, 'routeMode': 1, 'Type': 32, 'flag': 5566286434488,
              'playStyle': 7, 'soundType': 123, 'contentOptions': 305832785035294,
              'needSlope': 0, 'threeD': 0, 'hwFlag': 0, 'switchAction': 0,
              'guideOpt': 1949, 'serverOpt': 2}
    root = {'protocolVer': '5.1', 'dataVer': str(contexts[0]['eta_data_vers']),
            'sdkVer': '17.00.0.679', 'uuid': '', 'lndsDataVer': '', 'lanePathOpt': 7,
            'naviHeader': header, 'vehicle': {'type': 0, 'plate': ''},
            'naviID': contexts[0]['navigation_id_candidate'], 'abTestID': '',
            'param': params, 'pathArray': paths}
    plain = json.dumps(root, separators=(',', ':'), ensure_ascii=False).encode()
    compressed = zstandard.ZstdCompressor(level=3).compress(plain)
    body = json.dumps({'requestBody': base64.b64encode(compressed).decode(), 'type': 2},
                      separators=(',', ':')).encode()
    return encode_binary(body, assets)


def _project(path, breaks, point):
    latitude_scale = math.cos(math.radians(point[1]))
    break_set = set(breaks)
    progress, best = 0.0, (math.inf, 0.0)
    for index, (start, end) in enumerate(zip(path, path[1:]), 1):
        if index in break_set:
            continue
        dx, dy = (end[0] - start[0]) * latitude_scale, end[1] - start[1]
        px, py = (point[0] - start[0]) * latitude_scale, point[1] - start[1]
        fraction = max(0.0, min(1.0, (px * dx + py * dy) / (dx * dx + dy * dy or 1)))
        offset = math.hypot(px - fraction * dx, py - fraction * dy) * 111195
        length = distance(start, end)
        if offset < best[0]:
            best = (offset, progress + length * fraction)
        progress += length
    return best


def decode_speed_signs(answer, routes, expected_ids=None):
    if not isinstance(answer, bytes) or not 32 <= len(answer) <= MAX_RESPONSE:
        raise ValueError('routeguide response size')
    version, count, declared = struct.unpack_from('<IHI', answer)
    if version != 31 or declared != len(answer) or not 1 <= count <= 8:
        raise ValueError('routeguide envelope')
    offset, route_record = 32, None
    for _ in range(count):
        if offset + 32 > len(answer):
            raise ValueError('truncated routeguide record')
        compression, kind, packed, unpacked = struct.unpack_from('<HHII', answer, offset)
        offset += 32
        if packed > MAX_RESPONSE or unpacked > MAX_UNPACKED or offset + packed > len(answer):
            raise ValueError('routeguide record limit')
        if kind == 2:
            if compression != 2 or route_record is not None:
                raise ValueError('unsupported routeguide record')
            route_record = zstandard.ZstdDecompressor().decompress(
                answer[offset:offset + packed], max_output_size=MAX_UNPACKED,
                allow_extra_data=False)
            if len(route_record) != unpacked:
                raise ValueError('routeguide record length')
        offset += packed
    if offset != len(answer) or route_record is None:
        raise ValueError('missing routeguide data')
    root = fields(route_record)
    header = fields(one(root, 1, b''))
    if one(header, 1) != 51 or one(header, 3) != 0:
        raise ValueError('routeguide status')
    payload = fields(one(root, 2, b''))
    records = payload.get(1, [])
    if len(records) != len(routes):
        raise ValueError('routeguide route count mismatch')
    if expected_ids is not None and len(expected_ids) != len(records):
        raise ValueError('routeguide identity count mismatch')
    result = []
    for index, (blob, route) in enumerate(zip(records, routes)):
        signs = []
        extension = fields(blob)
        if expected_ids is not None:
            identity = one(extension, 1, b'')
            if not isinstance(identity, bytes) or len(identity) != 4 or int.from_bytes(identity, 'little') != expected_ids[index]:
                raise ValueError('routeguide route identity mismatch')
        for segment_blob in extension.get(2, []):
            segment = fields(segment_blob)
            for link_blob in segment.get(1, []):
                link = fields(link_blob)
                for item_blob in link.get(7, []):
                    item = fields(item_blob)
                    if one(item, 1) != 10:
                        continue
                    speed, coordinate = one(item, 2, 0), fields(one(item, 4, b''))
                    lon, lat = one(coordinate, 1), one(coordinate, 2)
                    if (type(speed) is not int or not 5 <= speed <= 160
                            or type(lon) is not int or type(lat) is not int):
                        continue
                    point = (lon / 7200000, lat / 7200000)
                    if not 70 <= point[0] <= 140 or not 0 <= point[1] <= 55:
                        continue
                    deviation, progress = _project(route['path'], route.get('breaks', []), point)
                    if deviation > 30 or progress > route['distance'] + 1:
                        continue
                    signs.append({'at': round(progress, 1), 'limit': speed})
        signs.sort(key=lambda item: item['at'])
        result.append([sign for index, sign in enumerate(signs)
                       if index == 0 or sign['limit'] != signs[index - 1]['limit']
                       or sign['at'] - signs[index - 1]['at'] > 20])
    return result


def request_routeguide(raw, material, assets):
    body = build_body(raw, assets)
    channel, diu, div = material['getAosChannel'], secrets.token_hex(8), 'ANDH170000'
    signature = hashlib.md5((channel + diu + div + '@' + material['getAosKey']).encode()).hexdigest().upper()
    inner = urlencode({'channel': channel, 'diu': diu, 'div': div,
                       'output': 'bin', 'sign': signature})
    params = {'ent': '2', 'in': encode(inner, assets), 'csid': str(uuid.uuid4()), 'is_bin': '1'}
    with requests.post(URL, params=params, data=body,
                       headers={'Content-Type': 'application/octet-stream'},
                       timeout=(8, 20), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError('routeguide unavailable')
        answer = response.raw.read(MAX_RESPONSE + 1, decode_content=True)
    if len(answer) > MAX_RESPONSE:
        raise ValueError('routeguide response size')
    return answer


def fetch_speed_signs(raw, routes, material, assets):
    answer = request_routeguide(raw, material, assets)
    expected_ids = [extract(raw, index)['wire_route_field6'] for index in range(len(routes))]
    return decode_speed_signs(answer, routes, expected_ids)
