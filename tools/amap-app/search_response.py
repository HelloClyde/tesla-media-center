"""Bounded adapter for the APK's infolite ``poi_list`` search results.

The pinned APK's ``InfoliteResponse``/``PoilistPoiInfo`` fields and ``cd3.n``
parser establish the candidate shape. A live successful response is still
needed before this may be enabled as TMC's production search provider.
"""

from __future__ import annotations

import json
import math


MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ITEMS = 100


class SearchResponseError(ValueError):
    pass


def _coordinate(value, limit: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and abs(number) <= limit else None


def _first_entrance(value) -> list[float] | None:
    if not isinstance(value, list):
        return None
    for passage in value[:16]:
        if not isinstance(passage, dict):
            continue
        longitude = _coordinate(passage.get("longitude"), 180)
        latitude = _coordinate(passage.get("latitude"), 90)
        if longitude is not None and latitude is not None:
            return [longitude, latitude]
    return None


def parse_infolite(raw: bytes) -> list[dict]:
    """Return navigable POIs; reject transport errors and malformed successes.

    Coordinates are returned as supplied by the App service. A caller must
    verify the coordinate system with a real response before using them in TMC.
    """
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_RESPONSE_BYTES:
        raise SearchResponseError("search response size invalid")
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise SearchResponseError("search response is not JSON") from error
    if not isinstance(result, dict):
        raise SearchResponseError("search response root invalid")
    code = result.get("code")
    if code != 1 and code != "1":
        raise SearchResponseError("search service did not report success")
    source = result.get("poi_list")
    if not isinstance(source, list) or len(source) > MAX_ITEMS:
        raise SearchResponseError("search POI list invalid")
    places, seen = [], set()
    for entry in source:
        if not isinstance(entry, dict) or entry.get("item_type", "poi") != "poi":
            continue
        identifier, name = entry.get("id"), entry.get("name")
        if not isinstance(identifier, str) or not identifier.strip() or not isinstance(name, str) or not name.strip():
            continue
        identifier, name = identifier.strip(), name.strip()
        longitude = _coordinate(entry.get("longitude"), 180)
        latitude = _coordinate(entry.get("latitude"), 90)
        if longitude is None or latitude is None or identifier in seen:
            continue
        seen.add(identifier)
        address = entry.get("address", "")
        place = {"id": identifier, "name": name,
                 "address": address.strip() if isinstance(address, str) else "",
                 "location": [longitude, latitude]}
        entrance = _first_entrance(entry.get("entrances"))
        if entrance is not None:
            place["entrance"] = entrance
        places.append(place)
    if source and not places:
        raise SearchResponseError("search contained no navigable POI")
    return places
