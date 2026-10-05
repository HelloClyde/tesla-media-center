"""Isolated consumer App 5.1 route adapter; credential-free navigation DTO.

Legacy summary helpers remain for offline regression only. Live requests must
pass the bounded 5.1 geometry decoder before navigation is enabled.
"""
import hashlib
import base64
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(os.environ.get("TMC_AMAP_APP_ASSETS", ROOT / "docker_build/amap-assets"))
HASHES = {
    "libamapr.so": "91491e00f582f610fe36cdbc4ca03bef942d0da8ce24dc1f672c53be73e88e08",
    "style-day.data": "3e3ebec698a750969c2b4184d38d0aa4a0abf67f37582a7af01f0f38192fb8ba",
    "style-night.data": "586a06dccb22873918c684d2644f39faf00409f8af37a64d1241333d893224c9",
    "style-navigation-day.data": "39c8495d761cc031073e37d48fa7036b8704cdc92242e1242df2bd8d0545daa0",
    "style-navigation-night.data": "3f595fbe0dffefb68fd86c195a023489bdd3394feff8af742526f407f822f066",
    "signing-certificate.rsa": "80a52915ce984adcfb8a7e37660702c50d4e1a5666d223f4f342f386612c6146",
    "libserverkey.so": "92bfe9abf10918954dcef8713a1734a5448e9bcfc413ca1836e853f6dfbddaa8",
}


def check_assets(validate_digest=True):
    if any(importlib.util.find_spec(name) is None for name in ("unicorn", "cryptography", "requests", "zstandard", "msgpack")):
        raise ValueError("missing-runtime")
    for name, expected in HASHES.items():
        path = ASSETS / name
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("asset-missing")
        if validate_digest:
            with path.open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if actual != expected:
                raise ValueError("asset-version-mismatch")


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("invalid-point")
    for coordinate, limit in zip(value, (180, 90)):
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or abs(coordinate) > limit or not math.isfinite(coordinate):
            raise ValueError("invalid-point")
    return [format(coordinate, ".6f") for coordinate in value]


def summarize(raw):
    from inspect_route_blocks import inspect
    from inspect_route_prefix import inspect as inspect_prefix
    try:
        result = inspect(raw)
    except (ValueError, IndexError, OverflowError):
        # A new detail layout need not discard a separately bounded name table.
        # This is only a text summary; it must not imply geometry was parsed.
        try:
            prefix = inspect_prefix(raw)
        except (ValueError, IndexError, OverflowError):
            return {"state": "unsupported-response", "navigationAvailable": False}
        return {"state": "partial", "navigationAvailable": False,
                "routes": [{"id": index, "labels": [], "roads": [item["text"] for item in group]}
                           for index, group in enumerate(prefix["groups"])],
                "checks": {"framing": False, "geometryCandidates": None, "geometryTotal": None,
                           "completeGeometry": False, "distance": False, "duration": False,
                           "coordinateSystem": False}}
    routes = []
    for index, record in enumerate(result["candidate_records"]):
        roads = [span["text"] for span in result["summary_groups"][index]["spans"]]
        routes.append({"id": index, "labels": [item["text"] for item in record["labels"]],
                       "roads": roads})
    return {"state": "partial", "navigationAvailable": False,
            "message": "已读出道路摘要；完整路线、距离、耗时仍待验证，暂不能用于导航。",
            "routes": routes, "checks": {
                "framing": result["framing_consumed_all"],
                "geometryCandidates": result["candidate_geometry_block_count"],
                "geometryTotal": len(result["detail_blocks"]),
                "completeGeometry": False, "distance": False, "duration": False,
                "coordinateSystem": False,
            }}


def probe(payload):
    import requests
    from native_signer import load_material
    origin, destination = point(payload.get("origin")), point(payload.get("destination"))
    if origin == destination:
        raise ValueError("identical-points")
    material = load_material(ASSETS)
    params = dict(zip(("fromX", "fromY", "toX", "toY"), origin + destination))
    params.update(policy2="0", output="bin", route_version="5.1", invoker="navi",
                  channel=material["getAosChannel"])
    message = material["getAosChannel"] + "".join(origin + destination) + "@" + material["getAosKey"]
    params["sign"] = hashlib.md5(message.encode("utf-8")).hexdigest().upper()
    # A fixed host and no redirects: callers cannot turn the adapter into a proxy.
    with requests.get("https://m5.amap.com/ws/mapapi/navigation/auto/", params=params,
                      timeout=(8, 20), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError("upstream-unavailable")
        raw = bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("response-too-large")
    from route_v51 import decode
    try:
        routes = decode(bytes(raw), list(map(float, origin)), list(map(float, destination)))
    except ValueError:
        return {"state": "unsupported-response", "navigationAvailable": False}
    return {"state": "ready", "navigationAvailable": True, "coordinateSystem": "GCJ-02",
            "routes": routes, "rawRoute": base64.b64encode(raw).decode("ascii")}


def traffic(payload):
    import requests
    from eta_live import ETA_URL, build_eta_body, decode_eta_lights, eta_query
    from native_signer import load_material
    from route_v51 import decode
    from v51_dynamic_route import extract

    encoded = payload.get("rawRoute")
    if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    raw = base64.b64decode(encoded, validate=True)
    if not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    routes = decode(raw)
    index = payload.get("routeIndex")
    if type(index) is not int or not 0 <= index < len(routes):
        raise ValueError("invalid-route-index")
    position = [float(x) for x in point(payload.get("position"))]
    speed, heading = payload.get("speed", 0), payload.get("heading", 0)
    if (type(speed) not in (int, float) or not math.isfinite(speed) or not 0 <= speed <= 100
            or type(heading) not in (int, float) or not math.isfinite(heading) or not 0 <= heading <= 360):
        raise ValueError("invalid-motion")
    contexts = [extract(raw, i) for i in range(len(routes))]
    material = load_material(ASSETS)
    body = build_eta_body(routes, contexts, index, position, speed=speed,
                          heading=heading, progress_hint=payload.get("progress"))
    query = eta_query(material, payload["adiu"], ASSETS)
    with requests.post(ETA_URL, params={"ent": "2", "in": query,
                       "csid": str(uuid.uuid4()), "is_bin": "1"}, data=body,
                       timeout=(8, 20), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError("upstream-unavailable")
        answer = response.raw.read(65537, decode_content=True)
        if len(answer) > 65536:
            raise ValueError("eta-response-too-large")
    live = decode_eta_lights(answer, contexts[index]["navigation_id_candidate"],
                             contexts[index]["wire_route_field6"])
    return {"state": "ready", **live}


def navigation_events(payload):
    from native_signer import load_material
    from route_v51 import decode
    from routeguide_events import fetch_guidance

    encoded = payload.get("rawRoute")
    if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    raw = base64.b64decode(encoded, validate=True)
    if not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    routes = decode(raw)
    index = payload.get("routeIndex")
    if type(index) is not int or not 0 <= index < len(routes):
        raise ValueError("invalid-route-index")
    guidance = fetch_guidance(raw, routes, load_material(ASSETS), ASSETS)
    return {"state": "ready", **guidance[index]}


def route_traffic(payload):
    """Refresh App link TMC only when the planned route still matches exactly."""
    from route_v51 import decode, distance
    from v51_dynamic_route import extract

    encoded, index = payload.get("rawRoute"), payload.get("routeIndex")
    if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    raw = base64.b64decode(encoded, validate=True)
    if not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    routes = decode(raw)
    if type(index) is not int or not 0 <= index < len(routes):
        raise ValueError("invalid-route-index")
    original = routes[index]
    old_links = extract(raw, index)["route_links_candidate"]
    fresh = probe({"origin": original["path"][0], "destination": original["path"][-1]})
    if fresh.get("state") != "ready" or not fresh.get("rawRoute"):
        return {"state": "unavailable"}
    refreshed = base64.b64decode(fresh["rawRoute"], validate=True)
    for new_index, candidate in enumerate(fresh["routes"]):
        if (len(candidate["path"]) != len(original["path"])
                or abs(candidate["distance"] - original["distance"]) > 1
                or extract(refreshed, new_index)["route_links_candidate"] != old_links):
            continue
        if any(distance(a, b) > 3 for a, b in zip(original["path"], candidate["path"])):
            continue
        return {"state": "ready", "distance": original["distance"], "trafficRuns": candidate["trafficRuns"],
                "updatedAt": int(time.time())}
    return {"state": "unavailable"}


def junction(payload):
    import requests
    from cross_v4_request import CROSS_URL, build_cross_for_step, cross_query
    from cross_v4_response import MAX_RESPONSE, decode_cross_picture
    from native_body_codec import encode_binary
    from native_signer import load_material
    from route_v51 import decode

    encoded = payload.get("rawRoute")
    if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    raw = base64.b64decode(encoded, validate=True)
    if not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("invalid-route-session")
    routes = decode(raw)
    index, step = payload.get("routeIndex"), payload.get("stepIndex")
    if type(index) is not int or not 0 <= index < len(routes):
        raise ValueError("invalid-route-index")
    if type(step) is not int or not 0 <= step < len(routes[index]["steps"]) - 1:
        raise ValueError("invalid-junction-step")
    body, navi_id = build_cross_for_step(raw, index, step)
    material = load_material(ASSETS)
    query = cross_query(material, ASSETS)
    encoded_body = encode_binary(body, ASSETS)
    with requests.post(CROSS_URL, params=query, data=encoded_body,
                       timeout=(8, 20), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            return {"state": "unavailable"}
        answer = response.raw.read(MAX_RESPONSE + 1, decode_content=True)
        if len(answer) > MAX_RESPONSE:
            raise ValueError("cross-response-too-large")
    try:
        picture = decode_cross_picture(answer, expected_navigation_id=navi_id)
    except ValueError as error:
        # A complete App response without image layers is a definitive miss;
        # transport failures or malformed responses may succeed on retry.
        if str(error) == "cross response image layers are incomplete":
            return {"state": "absent"}
        return {"state": "unavailable"}
    return {"state": "ready", "width": picture.width, "height": picture.height,
            "roadJpeg": base64.b64encode(picture.road_jpeg).decode("ascii"),
            "arrowPng": base64.b64encode(picture.arrow_png).decode("ascii")}


def main():
    try:
        if sys.argv[1:] == ["--check"]:
            check_assets()
            result = {"state": "configured", "navigationAvailable": False}
        else:
            payload = json.loads(sys.stdin.buffer.read(6 * 1024 * 1024 + 4097))
            if not isinstance(payload, dict):
                raise ValueError("invalid-request")
            # A traffic token can only come from a previously verified route
            # response, so skip rehashing the ~400 MB APK on every poll.
            action = payload.get("action")
            check_assets(validate_digest=action not in ("traffic", "junction", "navigation-events", "route-traffic"))
            result = (traffic(payload) if action == "traffic" else
                      junction(payload) if action == "junction" else
                      navigation_events(payload) if action == "navigation-events" else
                      route_traffic(payload) if action == "route-traffic" else probe(payload))
    except Exception:
        # Exception messages from requests may contain signed URLs. Never emit them.
        result = {"state": "unavailable", "navigationAvailable": False,
                  "message": "实验适配器不可用，请检查本地研究资源、Python 依赖或网络。"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
