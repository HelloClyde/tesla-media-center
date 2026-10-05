import hashlib

import pytest

from search_request import (COMMON_KEYS, VIRTUAL_V2_HEADERS, app_form_encode,
                            audit_apk_context, audit_keyword_params,
                            audit_virtual_v2_headers,
                            java_hashmap_items, keyword_params, prepare_post,
                            virtual_v2_factors_input)


def test_keyword_defaults_match_apk_tquery_branch():
    params = keyword_params("杭州西湖", geoobj="120|30|121|31",
                            user_loc="120.1,30.2", user_city="330100",
                            siv="ANDH170000")
    assert params["keywords"] == "杭州西湖"
    assert params["query_type"] == "TQUERY"
    assert params["geoobj"] == "120|30|121|31"
    assert params["user_loc"] == "120.1,30.2"
    assert params["user_city"] == "330100"
    assert params["siv"] == "ANDH170000"
    assert params["dib"] == "a"
    assert params["search_operate"] == "1"
    assert params["pagesize"] == "10"
    assert params["pagenum"] == "1"
    assert keyword_params("杭州西湖", geoobj="120|30|121|31",
                          global_search=True)["geoobj"] == ""
    assert keyword_params("杭州西湖", geoobj="", dibv=1000)["dib"] == ""


def test_apk_form_escaping():
    assert app_form_encode({"words": "杭州 西湖~*"}) == "words=%E6%9D%AD%E5%B7%9E+%E8%A5%BF%E6%B9%96%7E*"


def test_apk_form_distinguishes_null_from_empty_common_value():
    # zv6.a emits an equals sign only when ed4.b is non-null.
    assert app_form_encode({"missing": None, "empty": ""}) == "missing&empty="

    request = prepare_post(keyword_params("杭州", geoobj=""),
                           {"channel": "chn", "diu": None, "diu2": ""},
                           "secret", encode_body=lambda form: form)
    parts = request["body"].decode().split("&")
    assert "diu" in parts
    assert "diu=" not in parts
    assert "diu2=" in parts


def test_post_map_order_matches_java_hashmap_reference():
    # Independently checked with Java 11 HashMap.put/keySet for this sequence.
    keys = ("q", "a", "b", "siv", "client_network_class", "geoobj", "keywords", "channel")
    values = dict.fromkeys(keys, "")
    assert [key for key, _ in java_hashmap_items(values)] == [
        "geoobj", "q", "a", "siv", "b", "keywords", "channel", "client_network_class"]

    # Independently checked with a Java 11 HashMap for the 84-key search map.
    online = keyword_params("杭州", geoobj="120|30|121|31")
    full_keys = dict.fromkeys([*sorted(COMMON_KEYS), "output", "sign", *online], "")
    sequence = ",".join(key for key, _ in java_hashmap_items(full_keys))
    assert hashlib.sha256(sequence.encode()).hexdigest() == (
        "45217afd1078c5bf1f6603dd65880154c3a65201a24a703008ea545d734d5544")


def test_form_post_places_common_and_sign_inside_encoded_body():
    online = keyword_params("杭州西湖", geoobj="120|30|121|31")
    result = prepare_post(online, {"channel": "chn", "div": "v1"},
                          "secret", encode_body=lambda value: "ENC(" + value + ")",
                          csid="fixed-id")
    assert result["path"] == "/ws/mapapi/poi/infolite"
    assert result["query"] == {"ent": "2", "csid": "fixed-id"}
    body = result["body"].decode()
    digest = hashlib.md5("chn杭州西湖120|30|121|31@secret".encode()).hexdigest().upper()
    assert "channel=chn" in body
    assert f"sign={digest}" in body
    assert "keywords=%E6%9D%AD%E5%B7%9E%E8%A5%BF%E6%B9%96" in body
    assert "sign" not in result["query"] and "in" not in result["query"]


def test_reject_missing_keyword_and_sign_override():
    with pytest.raises(ValueError):
        keyword_params("", geoobj="")
    with pytest.raises(ValueError):
        prepare_post({"keywords": "x", "sign": "override"},
                     {"channel": "chn"}, "secret", encode_body=lambda s: s)


def test_audit_exposes_partial_apk_request_without_calling_it_a_server_rejection():
    online = keyword_params("杭州西湖", geoobj="120|30|121|31", siv="")
    audit = audit_apk_context(online, {"channel": "chn", "siv": "ANDH170000"})
    assert set(audit["missingCommon"]) == COMMON_KEYS - {"channel", "siv"}
    assert audit["missingHeaders"] == ["ap-tid", "user-agent", "x-gen"]
    assert audit["overriddenCommon"] == ["siv"]

    complete = dict.fromkeys(COMMON_KEYS, "")
    complete["channel"] = "chn"
    audit = audit_apk_context({}, complete, {"x-gen": "runtime", "Ap-Tid": "runtime",
                                               "User-Agent": "Android 11"})
    assert audit == {"missingCommon": [], "missingHeaders": [], "overriddenCommon": []}


def test_keyword_audit_distinguishes_missing_and_wrong_fixed_parameters():
    complete = keyword_params("杭州西湖", geoobj="120|30|121|31")
    assert audit_keyword_params(complete) == {
        "missingFields": [], "changedFixedFields": [],
    }

    incomplete = {"keywords": "杭州西湖", "query_type": "SUG", "pagesize": "20"}
    audit = audit_keyword_params(incomplete)
    assert "geoobj" in audit["missingFields"]
    assert "user_loc" in audit["missingFields"]
    assert "user_city" in audit["missingFields"]
    assert audit["changedFixedFields"] == ["pagesize", "query_type"]


def test_virtual_v2_headers_are_a_separate_runtime_requirement():
    missing = audit_virtual_v2_headers({"Content-Type": "application/x-www-form-urlencoded"})
    assert set(missing) == VIRTUAL_V2_HEADERS
    assert audit_virtual_v2_headers({key.upper(): "runtime" for key in VIRTUAL_V2_HEADERS}) == []


def test_post_carries_runtime_common_headers_when_supplied():
    result = prepare_post(keyword_params("杭州", geoobj=""),
                          {"channel": "chn"}, "secret", encode_body=lambda s: s,
                          common_headers={"x-gen": "runtime", "Ap-Tid": "runtime"})
    assert result["headers"]["x-gen"] == "runtime"
    assert result["headers"]["Ap-Tid"] == "runtime"
    with pytest.raises(ValueError):
        prepare_post({}, {"channel": "chn"}, "secret", encode_body=lambda s: s,
                     common_headers={"content-type": "incorrect"})


def test_virtual_v2_receives_encrypted_form_body_not_plain_parameters():
    result = prepare_post(keyword_params("杭州", geoobj=""),
                          {"channel": "chn"}, "secret",
                          encode_body=lambda form: "ENC:" + form,
                          csid="fixed-id")
    encrypted = result["body"].decode("utf-8")
    factors = virtual_v2_factors_input(encrypted,
                                       timestamp_seconds=1_700_000_000,
                                       appkey="runtime-key")
    assert factors == {
        "data": "runtime-key&" + hashlib.md5(encrypted.encode()).hexdigest() + "&1700000000",
        "api": "/ws/mapapi/poi/infolite", "extendParas": {},
        "env": 0, "appkey": "runtime-key", "useWua": False,
    }
    assert hashlib.md5(encrypted.encode()).hexdigest() != hashlib.md5(
        encrypted.removeprefix("ENC:").encode()).hexdigest()
    with pytest.raises(ValueError):
        virtual_v2_factors_input(encrypted, timestamp_seconds=0, appkey="runtime-key")
    with pytest.raises(ValueError):
        virtual_v2_factors_input(encrypted, timestamp_seconds=1, appkey="runtime-key",
                                 path="/ws/mapapi/poi/tipslite")
