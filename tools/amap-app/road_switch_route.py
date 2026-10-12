"""APK-format constrained route request for the browser/Python adapter.

The confirmed startAvoidLink primitive excludes the old link at binding time.
Use native's unclassified switch bytes (0/0), then let TMC confirm the returned
target link. This does not reproduce LocParallelRoadInfo flag/hwFlag or pretend
to derive a bridge/tunnel level from GPS. No Android device is required.
"""
from __future__ import annotations

import math
import time
from urllib.parse import urlencode
import uuid
from xml.etree import ElementTree as ET

from aos_request_sign import sign
from native_body_codec import encode, encode_binary
from road_switch_request import SCALE, avoid_link_pair, encode_start_avoid_link
from route_v51 import fields, one, unpack

URL = 'https://nvg.amap.com/ws/transfer/navigation/auto/'
MAX_RESPONSE = 4 * 1024 * 1024
# Non-personal defaults from the pinned APK's actual plan POST schema.
ROOT_FIELDS = {'Vers': '5.1', 'SdkVer': '17.00.0.679', 'Type': '32',
    'Flag': '5566286434488', 'ContentOptions': '305832785035294',
    'Source': 'amap', 'privacy': '1', 'DisFlag': '1', 'Invoker': 'plan',
    'BizScene': '0', 'Reroute': '0', 'Silence': '0', 'PlayStyle': '7',
    'noviceLevel': '0', 'SoundType': '0', 'RouteMode': '1', 'RequestIndex': '1',
    'RerouteIndex': '0', 'UserType': '0', 'personal_semantics': '0'}


def build_body(origin, destination, link_points, now=None, heading=None):
    now = time.time() if now is None else now
    for point in (origin, destination, *link_points):
        if (not isinstance(point, (tuple, list)) or len(point) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
                or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
            raise ValueError('invalid route coordinate')
    pair = avoid_link_pair([tuple(round(value*SCALE) for value in point) for point in link_points])
    if pair is None: raise ValueError('missing current-link geometry')
    root = ET.Element('route', {**ROOT_FIELDS, 'Uuid': str(int(now*1000))})
    ET.SubElement(root, 'vehicle', {'type': '0', 'etc_flag': '0', 'vehicleFlag': '0'})
    ET.SubElement(root, 'location', {'Type': '0', 'Name': ''})
    ET.SubElement(root, 'destination', {'Name': '', 'Strategy': '1'})
    ET.SubElement(root, 'jump', {'type': '1', 'sa': '0', 'sa_ptype': '-1'})
    if heading is not None:
        if type(heading) not in (int, float) or not math.isfinite(heading) or not 0 <= heading < 360:
            raise ValueError('invalid vehicle heading')
        root.find('jump').set('sa', f'{heading:.6f}')
    for name, point, attributes in (('startpoint', origin, {'Type': '0', 'BuildingFloor': '0'}),
                                     ('endpoint', destination, {'Type': '1'})):
        node = ET.SubElement(root, name, attributes)
        if name == 'startpoint': ET.SubElement(node, 'tm').text = str(int(now))
        for key, value in zip(('x', 'y'), point): ET.SubElement(node, key).text = f'{value:.6f}'
    for name in ('avoid', 'wish'): ET.SubElement(ET.SubElement(root, name, {'Type': '2'}), 'name')
    # Native c65b7c leaves both bytes zero for unclassified MM state. The exact
    # native byte derivation is still unverified, so never reuse LocSwitch 0..3.
    root.append(ET.fromstring(encode_start_avoid_link([pair], 0, 0)))
    return ET.tostring(root, encoding='utf8')


def request_route(origin, destination, link_points, material, assets, *, accuracy=None, speed=None, heading=None):
    import requests
    body = encode_binary(build_body(origin, destination, link_points, heading=heading), assets)
    inner = {'channel': material['getAosChannel'], 'sdk_version': ROOT_FIELDS['SdkVer'],
             'output': 'bin', 'invoker': 'plan', 't': 'carroute'}
    for key, value, maximum in (('sloc_precision', accuracy, 20000), ('sloc_speed', speed, 120)):
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError('invalid vehicle observation')
            inner[key] = str(value)
    inner['sign'] = sign(('channel',), inner, {}, material['getAosKey'])
    params = {'ent': '2', 'in': encode(urlencode(inner), assets), 'csid': str(uuid.uuid4()), 'is_bin': '1'}
    with requests.post(URL, params=params, data=body, headers={'Content-Type': 'application/octet-stream'},
                       timeout=(8, 20), allow_redirects=False, stream=True) as response:
        if response.status_code != 200: raise ValueError('native correction unavailable')
        answer = response.raw.read(MAX_RESPONSE+1, decode_content=True)
    if len(answer) > MAX_RESPONSE: raise ValueError('native correction response too large')
    header = fields(one(fields(unpack(answer)), 1, b''))
    # RouteConstant.RequestState.StartNoRoad: the excluded old link did not
    # leave a bindable start road. Do not disguise this as an ordinary replan.
    if one(header, 1) == 51 and one(header, 3) == 10: return None
    return answer
