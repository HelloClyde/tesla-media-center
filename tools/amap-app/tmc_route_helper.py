"""Isolated consumer App 5.1 route adapter; credential-free navigation DTO.

Legacy summary helpers remain for offline regression only. Live requests must
pass the bounded 5.1 geometry decoder before navigation is enabled.
"""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(os.environ.get("TMC_AMAP_APP_ASSETS", ROOT / ".local-data/amap-app"))
HASHES = {
    "amap-release.apk": "022c844511dce2958fd37c8d0941feb72587a434701debc9b2fda3e69ec07152",
    "libserverkey.so": "92bfe9abf10918954dcef8713a1734a5448e9bcfc413ca1836e853f6dfbddaa8",
}


def check_assets():
    if any(importlib.util.find_spec(name) is None for name in ("unicorn", "cryptography", "requests", "zstandard")):
        raise ValueError("missing-runtime")
    for name, expected in HASHES.items():
        with (ASSETS / name).open("rb") as handle:
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
    params.update(policy2="0", output="bin", route_version="5.1", invoker="plan",
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
    return {"state": "ready", "navigationAvailable": True, "coordinateSystem": "GCJ-02", "routes": routes}


def main():
    try:
        check_assets()
        if sys.argv[1:] == ["--check"]:
            result = {"state": "configured", "navigationAvailable": False}
        else:
            payload = json.loads(sys.stdin.buffer.read(4097))
            if not isinstance(payload, dict):
                raise ValueError("invalid-request")
            result = probe(payload)
    except Exception:
        # Exception messages from requests may contain signed URLs. Never emit them.
        result = {"state": "unavailable", "navigationAvailable": False,
                  "message": "实验适配器不可用，请检查本地研究资源、Python 依赖或网络。"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
