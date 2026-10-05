"""AMap App ETA traffic-light request and bounded live-signal decoder.

The wire layout was recovered from a real, mock-GPS-driven navigation session.
The Android app is not needed at runtime: a fresh 5.1 route and the current
vehicle position supply every session-dependent value.
"""

from __future__ import annotations

import json
import math
import time
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
import zlib

from aos_request_sign import sign
from eta_response import parse_eta_response
from native_body_codec import encode


ETA_URL = "https://m5.amap.com/ws/transfer/navigation/etatrafficupdate/"
SDK_VERSION = "17.00.0.1007.1.1.20241127"
ROOT_FIELDS = {
    "SdkVer": SDK_VERSION, "Vers": "2.0", "Type": "32", "Flag": "8786104",
    "Zip": "1", "ContentOptions": "8590721024", "EtaOptions": "1019",
    "Uuid": "", "PathSwitch": "0", "ReqType": "0", "SceneFlag": "0",
    "VPStatus": "1", "Source": "amap", "Invoker": "navi", "privacy": "1",
    "BizScene": "0", "DisFlag": "1",
}
COLOR_BY_TYPE = {1: "red", 11: "green", 30: "yellow"}


def _point(parent, name, point, **attrs):
    node = ET.SubElement(parent, name, attrs)
    ET.SubElement(node, "x").text = f"{point[0]:.6f}"
    ET.SubElement(node, "y").text = f"{point[1]:.6f}"
    return node


def _remaining_links(context, position, progress_hint=None):
    starts = context["route_links_start_point_candidate"]
    polylines = context["route_links_points_candidate"]
    lengths = context["route_links_length_candidate"]
    encoded = context["route_links_candidate"]
    if not starts or len(starts) != len(lengths) or len(starts) != len(encoded) or len(starts) != len(polylines):
        raise ValueError("ETA route links are inconsistent")
    latitude_scale = math.cos(math.radians(position[1]))
    candidates = []
    geometry_progress = 0.0
    for index, points in enumerate(polylines):
        if len(points) < 2 or tuple(points[0]) != tuple(starts[index]):
            raise ValueError("ETA link geometry is inconsistent")
        # Follow every native link vertex. A curve can be hundreds of metres
        # away from its start/end chord, even while the vehicle is on-road.
        projected = [((lon - position[0]) * latitude_scale * 111195,
                      (lat - position[1]) * 111195) for lon, lat in points]
        segment_lengths = [math.hypot(b[0] - a[0], b[1] - a[1])
                           for a, b in zip(projected, projected[1:])]
        total = sum(segment_lengths)
        if total <= 0:
            continue
        along = 0.0
        for (ax, ay), (bx, by), segment_length in zip(projected, projected[1:], segment_lengths):
            if segment_length <= 0:
                continue
            dx, dy = bx - ax, by - ay
            ratio = min(1.0, max(0.0, -(ax * dx + ay * dy) / (segment_length ** 2)))
            distance = math.hypot(ax + ratio * dx, ay + ratio * dy)
            position_along = along + ratio * segment_length
            candidates.append((distance, index, position_along / total,
                               geometry_progress + position_along))
            along += segment_length
        geometry_progress += total
    if not candidates:
        raise ValueError("ETA route links have no usable geometry")
    nearest_distance = min(candidate[0] for candidate in candidates)
    if progress_hint is None:
        distance, index, ratio, _ = min(candidates, key=lambda candidate: candidate[0])
    else:
        # GPS cannot distinguish close parallel or repeated links by distance
        # alone. The frontend's route progress disambiguates only near-equal
        # candidates; it cannot pull the match onto a distant road.
        close = [candidate for candidate in candidates
                 if candidate[0] <= nearest_distance + 12]
        distance, index, ratio, _ = min(
            close, key=lambda candidate: (abs(candidate[3] - progress_hint), candidate[0]))
    if distance > 100:
        raise ValueError("ETA position is away from the route")
    absolute = int(encoded[0])
    for delta in encoded[1:index + 1]:
        absolute += int(delta)
    roadlinks = [str(absolute), *encoded[index + 1:]]
    startlen = round(lengths[index] * ratio)
    drive_dist = sum(lengths[:index]) + startlen
    return roadlinks, startlen, drive_dist


def build_eta_body(routes, contexts, route_index, position, *, speed=0.0,
                   heading=0.0, progress_hint=None, now=None):
    if not 0 <= route_index < len(routes) == len(contexts) <= 10:
        raise ValueError("invalid ETA routes")
    if len(position) != 2 or any(not math.isfinite(x) for x in position):
        raise ValueError("invalid ETA position")
    now = int(time.time() if now is None else now)
    context = contexts[route_index]
    route = routes[route_index]
    if (progress_hint is not None and
            (type(progress_hint) not in (int, float) or not math.isfinite(progress_hint)
             or not 0 <= progress_hint <= route["distance"] + 500)):
        raise ValueError("invalid ETA route progress")
    roadlinks, startlen, drive_dist = _remaining_links(context, position, progress_hint)
    root = ET.Element("etatrafficupdate", {
        "DataVers": str(context["eta_data_vers"]), **ROOT_FIELDS,
        "NaviID": context["navigation_id_candidate"],
    })
    ET.SubElement(root, "vehicle", {"type": "0", "vehicleFlag": "0"})
    curloc = _point(root, "curloc", position, Type="2")
    for name, value in (("in_interval_speed", 0), ("CurSpeed", round(max(0, speed) * 3.6)),
                        ("DriveTime", round(drive_dist / max(speed, 1)) if speed else 0),
                        ("DriveDist", drive_dist), ("DriveHighwayDist", 0)):
        ET.SubElement(curloc, name).text = str(value)
    path = ET.SubElement(root, "path", {"id": str(context["wire_route_field6"]),
                    "routemode": "2", "recommendlevel": "0", "RerouteMethod": "Force"})
    _point(path, "startpoint", position, Type="2")
    _point(path, "endpoint", route["path"][-1], Type="2", min_arrival_percent="0")
    start = _point(path, "routestartpoint", route["path"][0])
    ET.SubElement(start, "firstroad").text = "0"
    lengths = context["route_links_length_candidate"]
    ET.SubElement(path, "linklens", {"startlen": str(startlen), "endlen": str(lengths[-1])})
    ET.SubElement(path, "roadlinks", {"IDType": "3"}).text = ";".join(roadlinks)
    front = {"flag": 2216544374437278, "gpsdata": "", "netLocationData": "",
             "feedback": "", "prePoint": {"lon": position[0], "lat": position[1],
             "dir": round(heading * 10), "time": now}, "socolrunning": 0,
             "retryFlag": 0, "vehicleType": 0, "lightFeedback": 0,
             "slowCar": 0, "extModules": [], "commonBroadcastCount": [],
             "radarLocation": {"linkId": "", "lon": 0, "lat": 0}, "radarFlag": 7}
    data = urlencode({"cpcode": "AN_Amap_ADR_FC", "deviceId": "",
                      "requestType": "3", "sdkVersion": SDK_VERSION,
                      "frontParam": json.dumps(front, separators=(",", ":"))})
    xml = ET.tostring(root, encoding="utf-8")
    fragment = ("<ETAInfo><ETAFlag>2</ETAFlag><TRRequestData><![CDATA[" + data +
                "]]></TRRequestData></ETAInfo>").encode()
    return b"0" + xml.replace(b"</etatrafficupdate>", fragment + b"</etatrafficupdate>")


def eta_query(material, adiu, asset_dir):
    query = {"channel": material["getAosChannel"], "div": "ANDH170000",
             "output": "json", "sdk_version": "17.00.0.1007", "t": "traffic",
             "location": "true", "adiu": adiu}
    query["sign"] = sign(("channel", "diu", "div", "_aosmd5"), query, {}, material["getAosKey"])
    return encode(urlencode(query), asset_dir)


def decode_eta_lights(raw, expected_navi_id, path_id, *, now=None):
    now = time.time() if now is None else now
    frame = parse_eta_response(raw)
    if not frame.accepted or frame.navi_id != expected_navi_id:
        raise ValueError("ETA frame does not match the route")
    if not 0 < frame.data_length <= 1024 * 1024:
        raise ValueError("ETA payload length is invalid")
    decompress = zlib.decompressobj()
    unpacked = decompress.decompress(frame.data, frame.data_length + 1)
    if len(unpacked) != frame.data_length or not decompress.eof:
        raise ValueError("ETA payload is incomplete")
    unpacked += decompress.flush()
    marker = b'{"controlflag"'
    offset = unpacked.find(marker)
    if offset < 0:
        raise ValueError("ETA live section is absent")
    result, _ = json.JSONDecoder().raw_decode(unpacked[offset:].decode("utf-8", "replace"))
    if result.get("status") != 0:
        raise ValueError("ETA live section was rejected")
    timestamp = result.get("timestamp")
    if type(timestamp) not in (int, float) or abs(timestamp / 1000 - now) > 90:
        raise ValueError("ETA live section is stale")
    points = ((result.get("data") or {}).get("onlineNavi") or {}).get("commonPoints")
    if not isinstance(points, list) or len(points) > 100:
        raise ValueError("ETA light list is invalid")
    output = []
    for point in points:
        if point.get("pathId") != path_id:
            continue
        location, info = point.get("location") or {}, point.get("lightInfo") or {}
        lon, lat = location.get("lon"), location.get("lat")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (lon, lat)):
            continue
        phases = []
        for phase in info.get("lightStates") or []:
            if not isinstance(phase, dict):
                continue
            start, end, kind = phase.get("stime"), phase.get("etime"), phase.get("type")
            if (type(start) is int and type(end) is int and 0 < end - start <= 300
                    and kind in COLOR_BY_TYPE and end > now - 3 and start < now + 300):
                phases.append({"start": start, "end": end, "color": COLOR_BY_TYPE[kind]})
        if not phases:
            continue
        output.append({"point": [lon, lat], "direction": info.get("dir"),
                       "phases": phases, "nodeId": info.get("nodeId"),
                       "linkId": location.get("linkId")})
    return {"updatedAt": timestamp, "lights": output}
