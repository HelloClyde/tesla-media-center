"""Bounded decoder for the APK's nearby-vehicle push payload.

This is an offline research adapter, not a warning source. Android ACCS transport,
warning lifetime, route/link matching, and native priority rules are not supplied
by this module. Never display or announce its output as a live driving warning.
The recovered envelope and field consumers are documented in
VEHICLE_WARNING_RESEARCH.md.
"""

from dataclasses import dataclass
import json


MAX_PUSH_BYTES = 256 * 1024
MAX_RECORDS = 100
MAX_BIZ_BYTES = 64 * 1024
MAX_SCENE_BYTES = 32 * 1024
SCENES = frozenset({"curveMeet", "nodeMeet", "rearFastCar", "rearFastTruckRemind"})


@dataclass(frozen=True)
class VehicleWarningPayload:
    push_id: str
    push_type: int | None
    push_time: str | None
    scene_type: str
    warning_level: int | None
    scene_data: str | None


def _object(value, limit):
    if not isinstance(value, str):
        raise ValueError("invalid warning JSON size")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError("invalid warning JSON text") from error
    if not 0 < size <= limit:
        raise ValueError("invalid warning JSON size")
    try:
        result = json.loads(value)
    except (ValueError, RecursionError) as error:
        raise ValueError("invalid warning JSON") from error
    if not isinstance(result, dict):
        raise ValueError("invalid warning object")
    return result


def _text(value, limit, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value.encode("utf-8")) > limit:
        raise ValueError("invalid warning text")
    return value


def _integer(value):
    if value is None:
        return None
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError("invalid warning integer")
    return value


def decode_warning_interaction(value):
    """Inspect a decoded kPushInteraction argument, without inventing events.

    Input is the JSON string passed to Horus action 12, after the AJX page has
    filtered moduleType=horus. The native reflected record has numeric bizType
    and string bizData. Warning metadata uses pushId/pushType/pushTime, **not**
    the separate commonParameter pathId/traceId structure.
    """
    root = _object(value, MAX_PUSH_BYTES)
    records = root.get("interactionHorus")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ValueError("invalid warning interaction")
    output = []
    for record in records:
        if not isinstance(record, dict) or type(record.get("bizType")) is not int:
            continue
        try:
            body = _object(record.get("bizData"), MAX_BIZ_BYTES)
            meta, data = body.get("metaInfo"), body.get("data")
            if not isinstance(meta, dict) or not isinstance(data, dict):
                continue
            v2x = data.get("v2xSafe")
            show = v2x.get("show") if isinstance(v2x, dict) else None
            if not isinstance(show, dict) or show.get("sceneType") not in SCENES:
                continue
            push_id = _text(meta.get("pushId"), 256)
            if not push_id:
                continue
            output.append(VehicleWarningPayload(
                push_id=push_id,
                push_type=_integer(meta.get("pushType")),
                # Keep the original string. Its clock/unit has not been proved.
                push_time=_text(meta.get("pushTime"), 64, optional=True),
                scene_type=show["sceneType"],
                warning_level=_integer(show.get("warningLevel")),
                # No geometry, coordinates or voice may be inferred from this
                # opaque native field until its consumer is recovered.
                scene_data=_text(show.get("sceneData"), MAX_SCENE_BYTES, optional=True),
            ))
        except (ValueError, UnicodeError, TypeError):
            continue
    return output
