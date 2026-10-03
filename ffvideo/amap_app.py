"""Authenticated App-route integration; unsupported geometry fails closed."""
import base64
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time

from flask import request
from ffvideo.utils import login_check, json_ok, json_fail

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/amap-app/tmc_route_helper.py"
PROBE_LOCK = threading.Lock()
JUNCTION_SLOTS = threading.BoundedSemaphore(2)
SESSION_LOCK = threading.Lock()
SESSION_DIR = Path(tempfile.gettempdir()) / "tmc-amap-route-sessions"
SESSION_TTL = 2 * 60 * 60
TRAFFIC_ADIU = secrets.token_hex(15)
TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
MANEUVERS = {1: 'left', 2: 'right', 3: 'bear-left', 4: 'bear-right'}
FORK_ACTIONS = {6: 'fork-middle', 7: 'fork-right', 8: 'fork-left'}


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
    if len(completed.stdout) > 16 * 1024 * 1024:
        raise ValueError("adapter output limit")
    result = json.loads(completed.stdout)
    if not isinstance(result, dict) or result.get("state") not in {
        "configured", "partial", "unsupported-response", "unavailable", "ready"
    }:
        raise ValueError("adapter output contract")
    # Explicit allowlist: raw protocol fields and signing material never reach UI.
    clean = {"state": result["state"], "navigationAvailable": False}
    if payload and payload.get("action") == "navigation-events":
        if result["state"] != "ready":
            return {"state": "unavailable", "speedSigns": [], "speedLimits": [], "speedCameras": []}
        signs = result.get("speedSigns")
        if not isinstance(signs, list) or len(signs) > 10000:
            raise ValueError("invalid speed signs")
        safe, previous = [], -1
        for sign in signs:
            if not isinstance(sign, dict):
                raise ValueError("invalid speed sign")
            at, limit = sign.get("at"), sign.get("limit")
            if (type(at) not in (int, float) or not math.isfinite(at)
                    or not previous <= at <= 20000000
                    or type(limit) is not int or not 5 <= limit <= 160):
                raise ValueError("invalid speed sign")
            safe.append({"at": at, "limit": limit})
            previous = at
        sections = result.get("speedLimits")
        if not isinstance(sections, list) or len(sections) > 10000:
            raise ValueError("invalid speed limit sections")
        safe_sections, previous_end = [], 0
        for section in sections:
            if not isinstance(section, dict):
                raise ValueError("invalid speed limit section")
            start, end, limit = section.get("start"), section.get("end"), section.get("limit")
            if (type(start) not in (int, float) or type(end) not in (int, float)
                    or not math.isfinite(start) or not math.isfinite(end)
                    or not previous_end <= start < end <= 20000000
                    or type(limit) is not int or not 5 <= limit <= 160):
                raise ValueError("invalid speed limit section")
            safe_sections.append({"start": start, "end": end, "limit": limit})
            previous_end = end
        cameras = result.get("speedCameras")
        if not isinstance(cameras, list) or len(cameras) > 10000:
            raise ValueError("invalid speed cameras")
        safe_cameras, previous_at = [], -1
        for camera in cameras:
            if not isinstance(camera, dict):
                raise ValueError("invalid speed camera")
            at, kind, speeds = camera.get("at"), camera.get("type"), camera.get("speed")
            if (type(at) not in (int, float) or not math.isfinite(at) or not previous_at <= at <= 20000000
                    or type(kind) is not int or kind not in (7, 25, 26, 27)
                    or not isinstance(speeds, list) or not 1 <= len(speeds) <= 8
                    or any(type(value) is not int or value != 255 and not 5 <= value <= 160 for value in speeds)
                    or all(value == 255 for value in speeds)):
                raise ValueError("invalid speed camera")
            safe_cameras.append({"at": at, "type": kind, "speed": speeds})
            previous_at = at
        return {"state": "ready", "speedSigns": safe,
                "speedLimits": safe_sections, "speedCameras": safe_cameras}
    if payload and payload.get("action") == "traffic":
        if result["state"] != "ready":
            return {"state": "unavailable", "lights": []}
        lights = result.get("lights")
        updated = result.get("updatedAt")
        if (not isinstance(lights, list) or len(lights) > 100
                or type(updated) not in (int, float) or abs(updated / 1000 - time.time()) > 90):
            raise ValueError("invalid live signals")
        safe = []
        for light in lights:
            coordinate = validate_point(light.get("point"))
            phases = light.get("phases")
            if not isinstance(phases, list) or len(phases) > 20:
                raise ValueError("invalid live phases")
            valid_phases = []
            for phase in phases:
                start, end = phase.get("start"), phase.get("end")
                if (type(start) is not int or type(end) is not int or not 0 < end-start <= 300
                        or phase.get("color") not in ("red", "green", "yellow")):
                    raise ValueError("invalid live phase")
                valid_phases.append({"start": start, "end": end, "color": phase["color"]})
            safe.append({"point": coordinate, "phases": valid_phases})
        return {"state": "ready", "updatedAt": updated, "lights": safe}
    if payload and payload.get("action") == "junction":
        if result["state"] != "ready":
            return {"state": "unavailable"}
        width, height = result.get("width"), result.get("height")
        if (type(width) is not int or type(height) is not int
                or not 0 < width <= 4096 or not 0 < height <= 4096):
            raise ValueError("invalid junction dimensions")
        picture = {"state": "ready", "width": width, "height": height}
        for field, signature, limit in (("roadJpeg", b"\xff\xd8\xff", 2 * 1024 * 1024),
                                         ("arrowPng", b"\x89PNG\r\n\x1a\n", 2 * 1024 * 1024)):
            encoded = result.get(field)
            if not isinstance(encoded, str) or len(encoded) > 3 * 1024 * 1024:
                raise ValueError("invalid junction layer")
            decoded = base64.b64decode(encoded, validate=True)
            if not decoded.startswith(signature) or len(decoded) > limit:
                raise ValueError("invalid junction layer")
            picture[field] = encoded
        return picture
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
            traffic_lights = route.get("trafficLights", [])
            traffic_light_count = route.get("trafficLightCount", 0)
            if (not isinstance(traffic_lights, list) or len(traffic_lights) > 10000
                    or type(traffic_light_count) is not int or traffic_light_count != len(traffic_lights)):
                raise ValueError("invalid traffic lights")
            traffic_lights = [validate_point(point) for point in traffic_lights]
            speed_limits = route.get("speedLimits", [])
            if not isinstance(speed_limits, list) or len(speed_limits) > 10000:
                raise ValueError("invalid speed limit sections")
            safe_speed_limits = []
            previous_end = 0
            for section in speed_limits:
                if not isinstance(section, dict):
                    raise ValueError("invalid speed limit section")
                start, end, limit = section.get("start"), section.get("end"), section.get("limit")
                if (type(start) not in (int, float) or type(end) not in (int, float)
                        or not math.isfinite(start) or not math.isfinite(end)
                        or not previous_end <= start < end <= length + 1
                        or type(limit) is not int or not 5 <= limit <= 160):
                    raise ValueError("invalid speed limit section")
                safe_speed_limits.append({"start": start, "end": end, "limit": limit})
                previous_end = end
            speed_cameras = route.get("speedCameras", [])
            if not isinstance(speed_cameras, list) or len(speed_cameras) > 10000:
                raise ValueError("invalid speed cameras")
            safe_speed_cameras = []
            for camera in speed_cameras:
                if not isinstance(camera, dict):
                    raise ValueError("invalid speed camera")
                at, kind, speeds = camera.get("at"), camera.get("type"), camera.get("speed")
                if (type(at) not in (int, float) or not math.isfinite(at) or not 0 <= at <= length + 1
                        or type(kind) is not int or kind not in (7, 25, 26, 27)
                        or not isinstance(speeds, list) or not 1 <= len(speeds) <= 8
                        or any(type(value) is not int or value != 255 and not 5 <= value <= 160 for value in speeds)
                        or all(value == 255 for value in speeds)):
                    raise ValueError("invalid speed camera")
                safe_speed_cameras.append({"at": at, "type": kind, "speed": speeds})
            safe_steps = []
            for step in steps:
                if not isinstance(step, dict):
                    raise ValueError("invalid route step")
                start, end, road = step.get("start"), step.get("end"), step.get("road")
                if type(start) is not int or type(end) is not int or not 0 <= start < end < len(path) or not isinstance(road, str) or len(road) > 1024:
                    raise ValueError("invalid route step")
                safe_step = {"start": start, "end": end, "road": road}
                # v5.1 segment.1 is the maneuver at this segment's exit.
                # Only codes verified against live route geometry are exposed.
                action = step.get('actionCode')
                assistant_action = step.get('assistantActionCode')
                # A fork instruction is more specific than its primary straight/turn action.
                if type(assistant_action) is int and assistant_action in FORK_ACTIONS:
                    safe_step['maneuver'] = FORK_ACTIONS[assistant_action]
                elif type(action) is int and action in MANEUVERS:
                    safe_step['maneuver'] = MANEUVERS[action]
                service_area = step.get('serviceArea')
                if service_area is not None:
                    if not isinstance(service_area, str) or not 2 <= len(service_area) <= 100 or \
                            not service_area.endswith(('服务区', '停车区')) or any(ord(c) < 32 for c in service_area):
                        raise ValueError('invalid service area')
                    safe_step['serviceArea'] = service_area
                safe_steps.append(safe_step)
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
                                    "trafficLights": traffic_lights, "trafficLightCount": traffic_light_count,
                                    "speedLimits": safe_speed_limits,
                                    "speedCameras": safe_speed_cameras,
                                    "distance": length, "labels": labels[:10]})
        raw_route = result.get("rawRoute")
        if raw_route is not None:
            clean["routeToken"] = save_route_session(raw_route)
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


def save_route_session(encoded):
    if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
        raise ValueError("invalid route session")
    raw = base64.b64decode(encoded, validate=True)
    if not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("invalid route session")
    with SESSION_LOCK:
        SESSION_DIR.mkdir(mode=0o700, exist_ok=True)
        now = time.time()
        for path in SESSION_DIR.glob("*.bin"):
            if now - path.stat().st_mtime > SESSION_TTL:
                path.unlink(missing_ok=True)
        token = secrets.token_hex(16)
        descriptor = os.open(SESSION_DIR / f"{token}.bin", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
    return token


def load_route_session(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("invalid route token")
    path = SESSION_DIR / f"{token}.bin"
    if time.time() - path.stat().st_mtime > SESSION_TTL:
        raise ValueError("expired route token")
    raw = path.read_bytes()
    if not 0 < len(raw) <= 4 * 1024 * 1024:
        raise ValueError("invalid route session")
    os.utime(path, None)
    return base64.b64encode(raw).decode("ascii")


def add_amap_app_route(app):
    @app.post("/api/amap-app/navigation-events")
    @app.post("/api/amap-app/speed-signs")
    @login_check
    def amap_app_navigation_events():
        if request.content_length and request.content_length > 4096:
            return json_fail(message="请求内容过大"), 413
        payload = request.get_json(silent=True)
        try:
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
            raw_route = load_route_session(payload.get("routeToken"))
            index = payload.get("routeIndex")
            if type(index) is not int or not 0 <= index <= 9:
                raise ValueError("invalid route index")
        except (ValueError, OSError):
            return json_fail(message="路线会话已过期，请重新规划路线"), 400
        try:
            return json_ok(invoke_helper({"action": "navigation-events", "rawRoute": raw_route,
                                          "routeIndex": index}))
        except subprocess.TimeoutExpired:
            return json_ok({"state": "unavailable", "speedSigns": [], "speedLimits": [], "speedCameras": []})
        except (OSError, ValueError, subprocess.SubprocessError):
            return json_ok({"state": "unavailable", "speedSigns": [], "speedLimits": [], "speedCameras": []})

    @app.post("/api/amap-app/junction-image")
    @login_check
    def amap_app_junction_image():
        if request.content_length and request.content_length > 4096:
            return json_fail(message="请求内容过大"), 413
        payload = request.get_json(silent=True)
        try:
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
            raw_route = load_route_session(payload.get("routeToken"))
            index, step = payload.get("routeIndex"), payload.get("stepIndex")
            if (type(index) is not int or not 0 <= index <= 9
                    or type(step) is not int or not 0 <= step <= 9999):
                raise ValueError("invalid junction index")
        except (ValueError, OSError):
            return json_fail(message="路线会话已过期，请重新规划路线"), 400
        if not JUNCTION_SLOTS.acquire(blocking=False):
            return json_ok({"state": "unavailable"})
        try:
            return json_ok(invoke_helper({"action": "junction", "rawRoute": raw_route,
                                          "routeIndex": index, "stepIndex": step}))
        except (OSError, ValueError, subprocess.SubprocessError):
            return json_ok({"state": "unavailable"})
        finally:
            JUNCTION_SLOTS.release()

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

    @app.post("/api/amap-app/traffic-signals")
    @login_check
    def amap_app_traffic_signals():
        if request.content_length and request.content_length > 4096:
            return json_fail(message="请求内容过大"), 413
        payload = request.get_json(silent=True)
        try:
            if not isinstance(payload, dict):
                raise ValueError("请求格式不正确")
            token = payload.get("routeToken")
            raw_route = load_route_session(token)
            position = validate_point(payload.get("position"))
            index = payload.get("routeIndex")
            speed, heading = payload.get("speed", 0), payload.get("heading", 0)
            if (type(index) is not int or not 0 <= index <= 9
                    or type(speed) not in (int, float) or not math.isfinite(speed) or not 0 <= speed <= 100
                    or type(heading) not in (int, float) or not math.isfinite(heading) or not 0 <= heading <= 360):
                raise ValueError("导航状态无效")
        except (ValueError, OSError):
            return json_fail(message="路线会话已过期，请重新规划路线"), 400
        try:
            return json_ok(invoke_helper({"action": "traffic", "rawRoute": raw_route,
                                          "routeIndex": index, "position": position,
                                          "speed": speed, "heading": heading,
                                          "adiu": TRAFFIC_ADIU}))
        except subprocess.TimeoutExpired:
            return json_fail(message="红绿灯数据请求超时"), 504
        except (OSError, ValueError, subprocess.SubprocessError):
            return json_fail(message="暂时无法获取实时红绿灯"), 502
