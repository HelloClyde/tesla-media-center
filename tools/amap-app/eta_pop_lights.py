"""Decode the APK's `data.radar.popLights` JSON shape for research.

This accepts an already-decoded successful ETA/TMC JSON body. It does not
decrypt a native frame, fetch live signals, or infer countdowns from geometry.
The field schema follows libamaptbt.so's parsers at 0x6e9874, 0x6e9a48,
0x6e9cd0 and 0x6e9fb8.
"""

from __future__ import annotations

import math


def _integer(value, bits: int, name: str) -> int:
    if type(value) is not int or not -(1 << (bits - 1)) <= value < (1 << (bits - 1)):
        raise ValueError(f"invalid {name}")
    return value


def _position(value, name: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"invalid {name}")
    point = {}
    for key, limit in (("lon", 180), ("lat", 90)):
        coordinate = value.get(key)
        if (type(coordinate) not in (int, float) or
                not math.isfinite(coordinate) or abs(coordinate) > limit):
            raise ValueError(f"invalid {name}.{key}")
        point[key] = float(coordinate)
    return point


def parse_eta_pop_lights(payload: dict) -> list[dict]:
    """Retain typed, direction-specific fields from a successful native JSON body.

    Missing optional fields stay absent; absent `popLights` means no records.
    Native phase/state codes remain numeric until their semantics are confirmed.
    """
    if not isinstance(payload, dict):
        raise ValueError("invalid ETA JSON")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("invalid ETA data")
    radar = data.get("radar", {})
    if not isinstance(radar, dict):
        raise ValueError("invalid ETA radar")
    raw = radar.get("popLights", [])
    if not isinstance(raw, list) or len(raw) > 256:
        raise ValueError("invalid ETA popLights")
    lights = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"invalid ETA popLights[{index}]")
        light = {}
        for key in ("countDown", "state", "location"):
            if key in entry:
                light[key] = _position(entry[key], key)
        for key in ("countDownDistance", "stateDistance", "greenEndOffset"):
            if key in entry:
                light[key] = _integer(entry[key], 32, key)
        for key in ("nodeId", "linkId"):
            if key in entry:
                light[key] = _integer(entry[key], 64, key)
        directions = entry.get("dirs", [])
        if not isinstance(directions, list) or len(directions) > 16:
            raise ValueError("invalid light directions")
        light["dirs"] = []
        for direction in directions:
            if not isinstance(direction, dict):
                raise ValueError("invalid light direction")
            parsed = {}
            for key in ("dir", "showType", "phase", "lightType", "controlLight"):
                if key in direction:
                    parsed[key] = _integer(direction[key], 32, key)
            states = direction.get("lightStates", [])
            if not isinstance(states, list) or len(states) > 64:
                raise ValueError("invalid light states")
            parsed["lightStates"] = []
            for state in states:
                if not isinstance(state, dict):
                    raise ValueError("invalid light state")
                item = {}
                for key in ("type", "signalTag", "signalChange"):
                    if key in state:
                        item[key] = _integer(state[key], 32, key)
                for key in ("stime", "etime"):
                    if key in state:
                        item[key] = _integer(state[key], 64, key)
                parsed["lightStates"].append(item)
            light["dirs"].append(parsed)
        lights.append(light)
    return lights
