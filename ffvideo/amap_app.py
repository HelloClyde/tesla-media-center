"""Authenticated App-route integration; unsupported geometry fails closed."""
import json
import math
from pathlib import Path
import subprocess
import sys
import threading

from flask import request
from ffvideo.utils import login_check, json_ok, json_fail

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/amap-app/tmc_route_helper.py"
PROBE_LOCK = threading.Lock()


def validate_point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("坐标须为经度、纬度两个数字")
    for coordinate, limit in zip(value, (180, 90)):
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or abs(coordinate) > limit or not math.isfinite(coordinate):
            raise ValueError("请输入有效的经纬度")
    return value


def invoke_helper(payload=None):
    command = [sys.executable, str(HELPER)]
    if payload is None:
        command.append("--check")
    completed = subprocess.run(command, input=json.dumps(payload).encode(),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               cwd=ROOT, timeout=40, check=True)
    if len(completed.stdout) > 8 * 1024 * 1024:
        raise ValueError("adapter output limit")
    result = json.loads(completed.stdout)
    if not isinstance(result, dict) or result.get("state") not in {
        "configured", "partial", "unsupported-response", "unavailable", "ready"
    }:
        raise ValueError("adapter output contract")
    # Explicit allowlist: raw protocol fields and signing material never reach UI.
    clean = {"state": result["state"], "navigationAvailable": False}
    if result["state"] == "ready":
        routes = result.get("routes")
        if not isinstance(routes, list) or not 1 <= len(routes) <= 10:
            raise ValueError("invalid routes")
        clean.update(navigationAvailable=True, coordinateSystem="GCJ-02", routes=[])
        for index, route in enumerate(routes):
            if not isinstance(route, dict):
                raise ValueError("invalid route")
            path, steps = route.get("path"), route.get("steps")
            if not isinstance(path, list) or not 2 <= len(path) <= 100000 or not isinstance(steps, list) or not 1 <= len(steps) <= 10000:
                raise ValueError("invalid route geometry")
            path = [validate_point(point) for point in path]
            length = route.get("distance")
            if type(length) not in (int, float) or not math.isfinite(length) or not 0 < length <= 20000000:
                raise ValueError("invalid route length")
            breaks = route.get("breaks", [])
            if not isinstance(breaks, list) or any(type(v) is not int or not 1 <= v < len(path) for v in breaks):
                raise ValueError("invalid route breaks")
            safe_steps = []
            for step in steps:
                if not isinstance(step, dict):
                    raise ValueError("invalid route step")
                start, end, road = step.get("start"), step.get("end"), step.get("road")
                if type(start) is not int or type(end) is not int or not 0 <= start < end < len(path) or not isinstance(road, str) or len(road) > 1024:
                    raise ValueError("invalid route step")
                safe_steps.append({"start": start, "end": end, "road": road})
            labels = route.get("labels", [])
            if not isinstance(labels, list) or any(not isinstance(v, str) or len(v) > 100 for v in labels):
                raise ValueError("invalid route labels")
            summary = {}
            for key, maximum in (("duration", 30 * 86400), ("tolls", 1000000)):
                value = route.get(key)
                summary[key] = value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum else None
            if summary['duration'] == 0:
                summary['duration'] = None
            summary['tollCurrency'] = 'CNY' if route.get('tollCurrency') == 'CNY' else None
            if summary['tollCurrency'] is None:
                summary['tolls'] = None
            clean["routes"].append({**summary, "id": index, "path": path, "steps": safe_steps, "breaks": breaks,
                                    "distance": length, "labels": labels[:10]})
    if result["state"] == "partial":
        routes = result.get("routes", [])
        if not isinstance(routes, list) or len(routes) > 255:
            raise ValueError("invalid summaries")
        clean["routes"] = []
        for index, route in enumerate(routes):
            if not isinstance(route, dict):
                raise ValueError("invalid summary")
            safe = {"id": index}
            for name in ("labels", "roads"):
                values = route.get(name, [])
                if not isinstance(values, list) or len(values) > 255 or any(not isinstance(v, str) or len(v) > 1024 for v in values):
                    raise ValueError("invalid summary strings")
                safe[name] = values
            clean["routes"].append(safe)
        checks = result.get("checks", {})
        if not isinstance(checks, dict):
            raise ValueError("invalid checks")
        total, count = checks.get("geometryTotal"), checks.get("geometryCandidates")
        if not (total is None and count is None) and (type(total) is not int or type(count) is not int or not 0 <= count <= total <= 65535):
            raise ValueError("invalid check counts")
        clean["checks"] = {"framing": checks.get("framing") is True,
                           "geometryTotal": total, "geometryCandidates": count,
                           "completeGeometry": False, "distance": False,
                           "duration": False, "coordinateSystem": False}
    return clean


def add_amap_app_route(app):
    @app.get("/api/amap-app/status")
    @login_check
    def amap_app_status():
        try:
            return json_ok(invoke_helper())
        except (OSError, ValueError, subprocess.SubprocessError):
            return json_ok({"state": "unavailable", "navigationAvailable": False})

    @app.post("/api/amap-app/route")
    @app.post("/api/amap-app/probe")
    @login_check
    def amap_app_probe():
        if request.content_length and request.content_length > 4096:
            return json_fail(message="请求内容过大"), 413
        payload = request.get_json(silent=True)
        try:
            if not isinstance(payload, dict):
                raise ValueError("请求格式不正确")
            origin, destination = validate_point(payload.get("origin")), validate_point(payload.get("destination"))
            if all(round(a, 6) == round(b, 6) for a, b in zip(origin, destination)):
                raise ValueError("起点和终点不能相同")
        except ValueError as error:
            return json_fail(message=str(error)), 400
        if not PROBE_LOCK.acquire(blocking=False):
            return json_fail(message="正在校验路线，请稍后重试"), 429
        try:
            return json_ok(invoke_helper({"origin": origin, "destination": destination}))
        except subprocess.TimeoutExpired:
            return json_fail(message="路线请求超时，请稍后重试"), 504
        except (OSError, ValueError, subprocess.SubprocessError):
            return json_fail(message="实验适配器暂不可用"), 502
        finally:
            PROBE_LOCK.release()
