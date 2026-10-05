"""APK 17.00 keyword-search request construction, without transport or SG headers.

This mirrors the verified AJX keyword parameter defaults and the FormBody
placement selected by p60.c/AosPostRequest. It does not claim a working online
search: NetworkParam's runtime fields and SecurityGuard headers are separate.
"""

from __future__ import annotations

import hashlib
import uuid

from aos_request_sign import sign


SIGN_FIELDS = ("id", "longitude", "latitude", "keywords", "category", "geoobj")
SEARCH_PATH = "/ws/mapapi/poi/infolite"
NEW_SEARCH_PATH = "/ws/shield/search_poi/search/sp"

# Unconditional put() calls in NetworkParam.getNetworkParamMap for the pinned
# APK. Some values may legitimately be empty, but the keys are still present.
COMMON_KEYS = frozenset({
    "div", "siv", "dip", "dic", "diu", "diu2", "diu3", "dai", "cifa",
    "session", "appstartid", "stepid", "channel", "client_network_class",
    "dibv", "BID_F", "aetraffic", "oaid", "buildABI", "i18n_lang",
    "i18n_tz_offset", "i18n_switch",
})

# AosRequest.securityGuardSign in the pinned APK adds these only when the
# default virtual-V2 signer returns nonempty factors. They are not ordinary
# keyword/common parameters and cannot be derived by this Python module.
VIRTUAL_V2_HEADERS = frozenset({
    "x-sign", "x-mini-wua", "x-pv", "x-t", "x-appkey", "x-umidtoken",
})

# Values assigned by SearchBaseRequestParam for every TQUERY keyword request.
# Location, city, map bounds, keyword and siv are runtime inputs, so they are
# checked for presence below rather than compared with guessed values.
KEYWORD_FIXED_FIELDS = {
    "version": "2.19", "qii": "true", "need_utd": "true",
    "direct_jump": "true", "citysuggestion": "true",
    "addr_poi_merge": "true", "need_codepoint": "true",
    "need_parkinfo": "true", "is_classify": "true",
    "query_mode": "normal", "transfer_filter_flag": "0",
    "cluster_state": "5", "transfer_pdheatmap": "0",
    "need_recommend": "1", "utd_sceneid": "101000", "scenario": "1",
    "query_scene": "search", "search_operate": "1",
    "query_type": "TQUERY", "pagenum": "1", "pagesize": "10",
    "sort_rule": "0",
}
KEYWORD_RUNTIME_FIELDS = frozenset({
    "keywords", "geoobj", "user_loc", "user_city", "siv", "dib",
})

# SearchBaseRequestParam._generateDefaultCommonParam in the pinned APK.
EMPTY_FIELDS = (
    "user_loc", "siv", "scenario", "need_parkinfo", "need_codepoint",
    "cmspoi", "specialpoi", "onlypoi", "busorcar", "query_scene",
    "citysuggestion", "search_operate", "hotelissupper", "need_magicbox",
    "hotelcheckin", "hotelcheckout", "hotelcondition", "aosbusiness",
    "version", "search_sceneid", "hotelstar", "scenefilter", "loc_strict",
    "takeout_flag", "direct_jump", "input_method", "need_utd",
    "utd_sceneid", "cluster_state", "client_network_class", "need_naviinfo",
    "pagesize", "pagenum", "query_type", "geoobj", "dib", "user_city",
    "need_recommend", "superid", "log_center_id", "query_mode",
    "transfer_filter_flag", "transfer_realtimebus_poi", "interior_floor",
    "sc_stype", "schema_source", "transparent_center_around", "transparent",
    "transfer_mode", "transfer_pdheatmap", "transfer_nearby_time_opt",
    "transfer_nearby_keyindex", "transfer_nearby_bucket", "isBrand",
    "tip_rule", "cur_adcode", "ajxVersion",
)


def keyword_params(keyword: str, *, geoobj: str, user_loc: str = "",
                   user_city: str = "", siv: str = "", dibv: int = 2005,
                   global_search: bool = False) -> dict[str, str]:
    """Replicate generateSearchKeywordParam(keyword, global_search)."""
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("keyword required")
    if any(not isinstance(value, str) for value in (geoobj, user_loc, user_city, siv)):
        raise ValueError("search context must be strings")
    params = dict.fromkeys(EMPTY_FIELDS, "")
    params.update({
        "version": "2.19", "qii": "true", "need_utd": "true",
        "direct_jump": "true", "citysuggestion": "true",
        "addr_poi_merge": "true", "need_codepoint": "true",
        "need_parkinfo": "true", "is_classify": "true",
        "query_mode": "normal", "transfer_filter_flag": "0",
        "cluster_state": "5", "transfer_pdheatmap": "0",
        "need_recommend": "1", "utd_sceneid": "101000", "scenario": "1",
        "query_scene": "search", "search_operate": "1", "siv": siv,
        "query_type": "TQUERY", "pagenum": "1", "pagesize": "10",
        "geoobj": "" if global_search else geoobj,
        "user_loc": user_loc, "user_city": user_city,
        "keywords": keyword, "sort_rule": "0",
    })
    if 2000 <= dibv <= 2999:
        params["dib"] = "a"
    return params


def app_form_encode(values: dict[str, str | None]) -> str:
    """Use the APK's zv6.a form escaping and null-value serialization.

    zv6.a appends ``key`` without ``=`` for a null value, but ``key=`` for an
    empty string. This distinction changes the encrypted body and V2 digest.
    """
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.*"

    def escape(value: str) -> str:
        pieces = []
        for byte in value.encode("utf-8"):
            if byte in safe:
                pieces.append(chr(byte))
            elif byte == 32:
                pieces.append("+")
            else:
                pieces.append(f"%{byte:02X}")
        return "".join(pieces)

    if any(not isinstance(k, str) or (v is not None and not isinstance(v, str))
           for k, v in values.items()):
        raise TypeError("form keys must be strings and values strings or None")
    return "&".join(escape(key) if value is None else f"{escape(key)}={escape(value)}"
                    for key, value in values.items())


def java_hashmap_items(values: dict[str, str | None]) -> list[tuple[str, str | None]]:
    """Iterate the ordinary Java HashMap used by AosPostRequest.processParams.

    Java HashMap iterates buckets, preserving insertion order within a bucket.
    This models the final map's ordering for string keys; it does not infer
    JSONObject.keys() order or reconstruct missing runtime values.
    """
    if any(not isinstance(key, str) for key in values):
        raise TypeError("form keys must be strings")
    capacity = 16
    while len(values) > capacity * 3 // 4:
        capacity *= 2

    def bucket(key: str) -> int:
        value = 0
        utf16 = key.encode("utf-16-be")
        for offset in range(0, len(utf16), 2):
            value = (31 * value + int.from_bytes(utf16[offset:offset + 2], "big")) & 0xffffffff
        return (value ^ (value >> 16)) & (capacity - 1)

    return sorted(values.items(), key=lambda item: bucket(item[0]))


def audit_apk_context(online_params: dict[str, str],
                      common_params: dict[str, str],
                      headers: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Report structural differences from the APK, without guessing values.

    Passing this check does not establish a valid request: runtime common
    values, SecurityGuard factors, and server acceptance still need comparison
    with a successful App request.
    """
    headers = {key.lower() for key in (headers or {})}
    return {
        "missingCommon": sorted(COMMON_KEYS - common_params.keys()),
        # The registered NetworkClient filter adds User-Agent when absent.
        # Cookie/sessionid are runtime-dependent and are not inferred here.
        "missingHeaders": sorted({"x-gen", "ap-tid", "user-agent"} - headers),
        "overriddenCommon": sorted(key for key in common_params.keys() & online_params.keys()
                                   if common_params[key] != online_params[key]),
    }


def audit_keyword_params(online_params: dict[str, str]) -> dict[str, list[str]]:
    """Check APK-fixed TQUERY fields separately from unknown runtime values.

    This is a structural comparison, not evidence that a server will accept
    the request. Empty location and city fields can be valid in the APK.
    """
    expected = set(EMPTY_FIELDS) | set(KEYWORD_FIXED_FIELDS) | KEYWORD_RUNTIME_FIELDS
    return {
        "missingFields": sorted(expected - online_params.keys()),
        "changedFixedFields": sorted(
            key for key, value in KEYWORD_FIXED_FIELDS.items()
            if key in online_params and online_params[key] != value
        ),
    }


def audit_virtual_v2_headers(headers: dict[str, str]) -> list[str]:
    """List missing headers for the APK's default successful V2 branch.

    A complete list is still not proof of a valid signature or device state.
    Runtime cloud configuration can switch this branch off or use legacy SG.
    """
    return sorted(VIRTUAL_V2_HEADERS - {key.lower() for key in headers})


def virtual_v2_factors_input(encoded_body: str, *, timestamp_seconds: int,
                             appkey: str, path: str = SEARCH_PATH,
                             environment: int = 0,
                             use_wua: bool = False) -> dict:
    """Recreate only the input passed to the APK's SecurityGuard component.

    AosPostRequest passes its *encrypted* FormBody string to the V2 signer.
    uu5.f hashes that string and combines it with the app key and timestamp.
    This function cannot generate the actual SecurityGuard factors or headers.
    """
    if not isinstance(encoded_body, str) or not encoded_body:
        raise ValueError("encoded body required")
    if not isinstance(timestamp_seconds, int) or timestamp_seconds <= 0:
        raise ValueError("positive Unix timestamp required")
    if not isinstance(appkey, str) or not appkey:
        raise ValueError("runtime app key required")
    if path not in (SEARCH_PATH, NEW_SEARCH_PATH):
        raise ValueError("unknown APK search path")
    if not isinstance(environment, int) or environment not in (0, 1, 2):
        raise ValueError("unknown SecurityGuard environment")
    if not isinstance(use_wua, bool):
        raise TypeError("use_wua must be boolean")
    digest = hashlib.md5(encoded_body.encode("utf-8")).hexdigest()
    return {
        "data": f"{appkey}&{digest}&{timestamp_seconds}",
        "api": path,
        "extendParas": {},
        "env": environment,
        "appkey": appkey,
        "useWua": use_wua,
    }


def prepare_post(online_params: dict[str, str], common_params: dict[str, str | None],
                 aos_key: str, *, encode_body, csid: str | None = None,
                 common_headers: dict[str, str] | None = None) -> dict:
    """Prepare a FormBody POST; no network call or SecurityGuard impersonation.

    The APK defaults to isCommonParamInQuery=false. Thus p60.c routes both
    request and common parameters into AosPostRequest's encoded body; the URL
    has ent=2 and a csid, not an encrypted `in=` query.
    """
    if not isinstance(aos_key, str) or not aos_key:
        raise ValueError("AOS signing key required")
    if not isinstance(common_params.get("channel"), str) or not common_params["channel"]:
        raise ValueError("AOS channel required")
    if "sign" in online_params or "sign" in common_params:
        raise ValueError("sign must be generated from the request fields")
    if common_headers and any(key.lower() == "content-type" for key in common_headers):
        raise ValueError("Content-Type comes from the APK RequestFormBody")
    signed_common = dict(common_params)
    signed_common["output"] = "json"
    signed_common["sign"] = sign(SIGN_FIELDS, online_params, signed_common, aos_key)
    # Both sources and the final POST parameter map are HashMaps in the APK.
    # Reordering before encryption matters to the raw bytes signed by SG V2.
    common = dict(java_hashmap_items(signed_common))
    online = dict(java_hashmap_items(online_params))
    form = app_form_encode(dict(java_hashmap_items({**common, **online})))
    body = encode_body(form)
    if not isinstance(body, str):
        raise TypeError("APK string codec must return str")
    return {
        "path": NEW_SEARCH_PATH if online_params.get("isNewPath") == "1" else SEARCH_PATH,
        "query": {"ent": "2", "csid": csid or str(uuid.uuid4())},
        "headers": {"Content-Type": "application/x-www-form-urlencoded",
                    **(common_headers or {})},
        "body": body.encode("utf-8"),
    }
