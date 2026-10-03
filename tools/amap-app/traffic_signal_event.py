"""Normalize the traffic-signal event shape used inside the AMap Android App.

This module only parses an event supplied by an Android navigation process. It
does not infer a signal phase from route geometry or from elapsed time.
"""

import json


_PHASES = {2: "red", 3: "red", 4: "green", 5: "green", 8: "yellow"}
# These three action codes are accepted by both App formatters. Their precise
# turn labels depend on the navigation action enum, so retain the native code.
_ACTIONS = {1, 2, 8}


def parse_native_signal_event(value):
    """Return visible signal states from the App's `statusInfos` event, if any.

    The App's Java formatters accept a `dataType=1` envelope whose `data` is a
    JSON array. The native navigation event (`eventType=26403`) instead uses
    `commonInfos`; Android live-activity models may wrap that event in
    `trafficLightInfo`. Other event types, hidden signals and invalid values
    do not become traffic guidance.
    """
    if not isinstance(value, dict):
        raise ValueError("invalid signal event")
    if "dataType" in value:
        if type(value["dataType"]) is not int or value["dataType"] != 1:
            return []
        raw = value.get("data")
        if not isinstance(raw, str) or len(raw) > 32768:
            raise ValueError("invalid signal data")
        try:
            entries = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid signal data") from error
    elif "trafficLightInfo" in value or "commonInfos" in value or "eventType" in value:
        event = value.get("trafficLightInfo", value)
        if not isinstance(event, dict) or event.get("eventType") != 26403:
            return []
        entries = event.get("commonInfos")
    else:
        entries = [value]
    if not isinstance(entries, list) or len(entries) > 16:
        raise ValueError("invalid signal entries")
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid signal entry")
        distance = entry.get("remainDis")
        if distance is not None and (type(distance) not in (int, float) or not 0 <= distance < 100000):
            continue
        infos = entry.get("statusInfos", [])
        if not isinstance(infos, list) or len(infos) > 16:
            raise ValueError("invalid signal states")
        states = []
        for item in infos:
            if not isinstance(item, dict):
                raise ValueError("invalid signal state")
            if item.get("showType") != 2:
                continue
            phase = _PHASES.get(item.get("status")) if type(item.get("status")) is int else None
            action = item.get("mainAction")
            seconds = item.get("remainTime")
            if phase is None or type(action) is not int or action not in _ACTIONS or type(seconds) is not int or not 0 < seconds <= 180:
                continue
            states.append({"phase": phase, "action": action, "seconds": seconds})
        if states:
            result.append({"states": states, **({"distanceMeters": distance} if distance is not None else {})})
    return result
