"""Decode APK routeguide NCP speed-section and speed-camera events.

The native event conditions use remaining distance along the App's link lengths.
Map that distance into the separately verified geometry, segment by segment.
Only speed-section records and camera records with explicit speed arrays are
exposed; unrelated NCP scripts never become driving warnings.
"""
import bisect
import json
import math
import re
import struct

import msgpack
import zstandard

from route_v51 import fields, one, unpack
from routeguide_speed import MAX_RESPONSE, MAX_UNPACKED, _project, decode_speed_signs, request_routeguide
from v51_dynamic_route import extract


SECTION_CONDITION = re.compile(r'\(\(distance>0\) && \(distance<=([0-9]{1,8})\)\)\Z')
CAMERA_TYPES = {7, 25, 26, 27}


def _kind_three(answer):
    if not isinstance(answer, bytes) or not 32 <= len(answer) <= MAX_RESPONSE:
        raise ValueError('routeguide response size')
    version, count, declared = struct.unpack_from('<IHI', answer)
    if version != 31 or declared != len(answer) or not 1 <= count <= 8:
        raise ValueError('routeguide envelope')
    offset, result = 32, None
    for _ in range(count):
        if offset + 32 > len(answer):
            raise ValueError('truncated routeguide record')
        compression, kind, packed, unpacked = struct.unpack_from('<HHII', answer, offset)
        offset += 32
        if packed > MAX_RESPONSE or unpacked > MAX_UNPACKED or offset + packed > len(answer):
            raise ValueError('routeguide record limit')
        if kind == 3:
            if compression != 2 or result is not None:
                raise ValueError('unsupported NCP record')
            result = zstandard.ZstdDecompressor().decompress(
                answer[offset:offset + packed], max_output_size=MAX_UNPACKED,
                allow_extra_data=False)
            if len(result) != unpacked:
                raise ValueError('NCP record length')
        offset += packed
    if offset != len(answer) or result is None:
        raise ValueError('missing NCP data')
    return result


def _ncp_events(blob):
    if (not isinstance(blob, bytes) or len(blob) < 36 or len(blob) > MAX_UNPACKED
            or blob[:4] != b'ncp0' or struct.unpack_from('<I', blob, 4)[0] != len(blob) - 12
            or struct.unpack_from('<I', blob, 8)[0] != 1):
        raise ValueError('unsupported NCP container')
    event_size = struct.unpack_from('<I', blob, 20)[0]
    offset, end = 28, 28 + event_size
    if not 0 < event_size <= MAX_UNPACKED or end > len(blob):
        raise ValueError('invalid NCP event size')
    events = []
    while offset < end:
        if len(events) >= 20000 or offset + 8 > end:
            raise ValueError('NCP event count')
        size = struct.unpack_from('<I', blob, offset)[0]
        if not 0 < size <= 65536 or offset + 8 + size > end:
            raise ValueError('NCP event length')
        try:
            event = msgpack.unpackb(blob[offset + 4:offset + 4 + size], raw=False,
                                    strict_map_key=True, max_str_len=65536,
                                    max_array_len=4096, max_map_len=256)
        except (ValueError, TypeError, msgpack.exceptions.UnpackException) as error:
            raise ValueError('invalid NCP event') from error
        if not isinstance(event, dict):
            raise ValueError('invalid NCP event')
        events.append(event)
        offset += 4 + size
        trailer = blob[offset:offset + 4]
        if offset + 4 == end:
            if trailer != b'\x04ida':
                raise ValueError('NCP event trailer')
        elif trailer not in (b'\0\0\0\0', b'\x01\0\0\0'):
            raise ValueError('NCP event separator')
        offset += 4
    return events


def _native_segments(raw):
    envelope = fields(unpack(raw))
    message = fields(one(envelope, 2, b''))
    result = []
    for route_blob in message.get(7, []):
        route = fields(route_blob)
        native = []
        for segment_blob in route.get(10, []):
            segment = fields(segment_blob)
            links = [one(fields(link), 2, 0) / 100 for link in segment.get(3, [])]
            if not links or any(not 0 < length <= 20000000 for length in links):
                raise ValueError('invalid native segment length')
            native.append(links)
        reported = one(route, 1, 0) / 100
        if not native or abs(sum(map(sum, native)) - reported) > 0.01:
            raise ValueError('native route length mismatch')
        result.append(native)
    return result


def _distance_map(route, native):
    steps = route['steps']
    if len(steps) != len(native):
        raise ValueError('NCP segment count mismatch')
    native_ends, measured_ends = [], []
    a = b = 0.0
    for step, length in zip(steps, native):
        a += length
        b += step['distance']
        native_ends.append(a)
        measured_ends.append(b)
    def map_distance(at):
        if not 0 <= at <= native_ends[-1] + 0.01:
            raise ValueError('NCP distance outside route')
        index = min(bisect.bisect_right(native_ends, at), len(native) - 1)
        native_start = native_ends[index] - native[index]
        measured_start = measured_ends[index] - steps[index]['distance']
        return measured_start + max(0, min(1, (at - native_start) / native[index])) * steps[index]['distance']
    return map_distance, native_ends


def decode_ncp(answer, raw, routes, expected_ids=None):
    root = fields(_kind_three(answer))
    header = fields(one(root, 1, b''))
    context = extract(raw, 0)
    if (one(header, 1) != 5100 or one(header, 3) != 0
            or one(header, 5, b'').decode('ascii') != context['navigation_id_candidate']):
        raise ValueError('NCP navigation mismatch')
    records = root.get(2, [])
    native_segments = _native_segments(raw)
    if len(records) != len(routes) or len(native_segments) != len(routes):
        raise ValueError('NCP route count mismatch')
    if expected_ids is None:
        expected_ids = [extract(raw, i)['wire_route_field6'] for i in range(len(routes))]
    result = []
    for index, (record, route, native_links) in enumerate(zip(records, routes, native_segments)):
        data = fields(record)
        identity = one(data, 1, b'')
        if (not isinstance(identity, bytes) or len(identity) != 4
                or int.from_bytes(identity, 'little') != expected_ids[index]):
            raise ValueError('NCP route identity mismatch')
        native = [sum(links) for links in native_links]
        map_distance, native_ends = _distance_map(route, native)
        total = native_ends[-1]
        sections, cameras = [], []
        def add_camera(kind, speeds, remaining, coordinate):
            if (type(kind) is not int or kind not in CAMERA_TYPES
                    or not isinstance(speeds, list) or not 1 <= len(speeds) <= 8
                    or any(type(value) is not int or value != 255 and not 5 <= value <= 160 for value in speeds)
                    or all(value == 255 for value in speeds)
                    or type(remaining) is not int or not 0 <= remaining <= total
                    or not isinstance(coordinate, dict)):
                return
            lon, lat = coordinate.get('lon'), coordinate.get('lat')
            if (type(lon) not in (int, float) or type(lat) not in (int, float)
                    or not math.isfinite(lon) or not math.isfinite(lat)
                    or not 70 <= lon <= 140 or not 0 <= lat <= 55):
                return
            at = map_distance(total - remaining)
            deviation, projected = _project(route['path'], route.get('breaks', []), (lon, lat))
            if deviation > 30 or abs(projected - at) > 50:
                return
            cameras.append({'at': round(at, 1), 'type': kind, 'speed': speeds})
        for event in _ncp_events(one(data, 4, b'')):
            script, encoded = event.get('NCPEvent'), event.get('_ds')
            if not isinstance(script, dict) or not isinstance(encoded, str) or len(encoded) > 8192:
                continue
            try:
                payload = json.loads(encoded)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            if list(payload) == ['speed']:
                speed, remaining = payload['speed'], script.get('_rd')
                segment, end_segment = script.get('_ss'), script.get('_es')
                condition = script.get('_c', '')
                match = SECTION_CONDITION.fullmatch(condition) if isinstance(condition, str) else None
                if (type(speed) is not int or not 5 <= speed <= 160 or type(remaining) is not int
                        or type(segment) is not int or segment != end_segment
                        or not 0 <= segment < len(native) or match is None):
                    continue
                length = int(match.group(1))
                start, end = total - remaining - length, total - remaining
                native_start = native_ends[segment] - native[segment]
                if not (0 <= start < end <= total + 0.01
                        and native_start - 0.01 <= start < end <= native_ends[segment] + 0.01):
                    continue
                sections.append({'start': round(map_distance(start), 1),
                                 'end': round(map_distance(end), 1), 'limit': speed})
            elif payload.get('type') in CAMERA_TYPES:
                remaining = payload.get('distance')
                if remaining == script.get('_rd'):
                    add_camera(payload['type'], payload.get('speed'), remaining, payload.get('coord2D'))
            elif isinstance(payload.get('subCamera'), list):
                segment, link, to_link = payload.get('segment'), payload.get('link'), payload.get('distToLink')
                remaining = script.get('_rd')
                if (type(segment) is not int or not 0 <= segment < len(native_links)
                        or type(link) is not int or not 0 <= link < len(native_links[segment])
                        or type(to_link) not in (int, float) or not math.isfinite(to_link)
                        or not 0 <= to_link <= native_links[segment][link]
                        or type(remaining) is not int):
                    continue
                native_at = (native_ends[segment] - native[segment]
                             + sum(native_links[segment][:link + 1]) - to_link)
                if abs(native_at - (total - remaining)) > 0.01:
                    continue
                for sub in payload['subCamera'][:16]:
                    if isinstance(sub, dict):
                        add_camera(sub.get('subType'), sub.get('speed'), remaining, payload.get('coord2D'))
        sections.sort(key=lambda item: item['start'])
        if any(a['end'] > b['start'] + 0.2 for a, b in zip(sections, sections[1:])):
            raise ValueError('overlapping NCP speed sections')
        cameras.sort(key=lambda item: item['at'])
        unique_cameras = []
        seen = set()
        for camera in cameras:
            key = (camera['at'], camera['type'], tuple(camera['speed']))
            if key not in seen:
                seen.add(key)
                unique_cameras.append(camera)
        result.append({'speedLimits': sections, 'speedCameras': unique_cameras})
    return result


def fetch_guidance(raw, routes, material, assets):
    answer = request_routeguide(raw, material, assets)
    expected_ids = [extract(raw, i)['wire_route_field6'] for i in range(len(routes))]
    signs = decode_speed_signs(answer, routes, expected_ids)
    ncp = decode_ncp(answer, raw, routes, expected_ids)
    return [{**guidance, 'speedSigns': points} for guidance, points in zip(ncp, signs)]
