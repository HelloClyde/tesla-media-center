"""Build the App's original V4 junction-image request from a 5.1 route."""

from __future__ import annotations

import json
import uuid
from urllib.parse import urlencode

from aos_request_sign import sign
from dynamic_route_links import decode_v51_link_deltas
from native_body_codec import encode
from route_v51 import fields, one, unpack
from v51_dynamic_route import extract


CROSS_URL = "https://m5.amap.com/ws/transfer/auth/new_vector_cross/"
SDK_VERSION = "17.00.0.1007"
SDK_BUILD = "17.00.0.1007.1.1.20241127"
SIGN_FIELDS = ("channel", "tid", "dic", "dip", "diu", "diu2", "diu3", "div")


def route_link_actions(raw: bytes, route_index: int):
    envelope = fields(unpack(raw))
    message = fields(one(envelope, 2, b""))
    route_blobs = message.get(7, [])
    if not 0 <= route_index < len(route_blobs):
        raise ValueError("invalid route index")
    route = fields(route_blobs[route_index])
    base = int.from_bytes(one(route, 9, b""), "little")
    deltas, main, assist = [], [], []
    for segment_blob in route.get(10, []):
        segment = fields(segment_blob)
        links = segment.get(3, [])
        if not links:
            raise ValueError("route segment without links")
        deltas.extend(one(fields(link_blob), 1) for link_blob in links)
        main.extend([0] * (len(links) - 1) + [one(segment, 1, 0)])
        assist.extend([0] * (len(links) - 1) + [one(segment, 2, 0)])
    ids = decode_v51_link_deltas(base, deltas)
    if len(ids) != len(main) or len(ids) != len(assist):
        raise ValueError("route action count mismatch")
    return ids, main, assist


def build_cross_for_step(raw: bytes, route_index: int, step_index: int) -> tuple[bytes, str]:
    """Use the current and next v5.1 segments around a maneuver.

    The original server accepts this smaller adjacent window and returns the
    same raster picture for the observed elevated-road fork. Other maneuvers
    may legitimately return vector data without a picture.
    """
    envelope = fields(unpack(raw))
    message = fields(one(envelope, 2, b""))
    route_blobs = message.get(7, [])
    if type(route_index) is not int or not 0 <= route_index < len(route_blobs):
        raise ValueError("invalid route index")
    route = fields(route_blobs[route_index])
    segments = route.get(10, [])
    if type(step_index) is not int or not 0 <= step_index < len(segments) - 1:
        raise ValueError("invalid junction step")
    counts = [len(fields(blob).get(3, [])) for blob in segments]
    if any(count <= 0 for count in counts):
        raise ValueError("route segment without links")
    first, second = counts[step_index:step_index + 2]
    context = extract(raw, route_index)
    return (build_cross_body(raw, route_index, sum(counts[:step_index]), first,
                             second, group_index=step_index),
            context["navigation_id_candidate"])


def build_cross_body(raw: bytes, route_index: int, start_link: int,
                     first_count: int, second_count: int, *,
                     group_index: int = 0, width: int = 1056,
                     height: int = 697) -> bytes:
    ids, main, assist = route_link_actions(raw, route_index)
    count = first_count + second_count
    if (any(type(x) is not int for x in (start_link, first_count, second_count,
                                         group_index, width, height))
            or start_link < 0 or first_count <= 0 or second_count <= 0
            or count > 512 or start_link + count > len(ids)
            or group_index < 0 or not 100 <= width <= 4096
            or not 100 <= height <= 4096):
        raise ValueError("invalid junction road window")
    context = extract(raw, route_index)
    window = ids[start_link:start_link + count]
    deltas = [0] + [window[index] - window[index - 1]
                    for index in range(1, len(window))]
    body = {
        "protocolVer": "4.0", "dataVer": str(context["eta_data_vers"]),
        "sdkVer": SDK_BUILD, "naviID": context["navigation_id_candidate"],
        "uuid": "", "isNight": "0", "needGridData": "1",
        "width": str(width), "height": str(height),
        "needStreetImage": "1", "crossType": "3", "interactMode": "",
        "source": "@source@", "needfullscreen": "@fullscreen@",
        "isWorld": "0",
        "pathInfo": {
            "pathID": context["wire_route_field6"],
            "firstSegIndex": group_index,
            "firstLinkID": window[0], "linkids": deltas,
            "segments": [first_count, second_count],
            "scenes": [0, -1],
            "mainActions": main[start_link:start_link + count],
            "assistActions": assist[start_link:start_link + count],
        },
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def cross_query(material: dict[str, str], asset_dir) -> dict[str, str]:
    params = {"channel": material["getAosChannel"], "cross_ver": "4.0",
              "sdk_version": SDK_VERSION, "output": "json"}
    params["sign"] = sign(SIGN_FIELDS, {}, params, material["getAosKey"])
    return {"ent": "2", "in": encode(urlencode(params), asset_dir),
            "csid": str(uuid.uuid4()), "is_bin": "1"}
