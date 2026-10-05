import json

import pytest

from search_response import SearchResponseError, parse_infolite


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode()


def test_extracts_navigable_pois_and_skips_cards():
    places = parse_infolite(raw({"code": 1, "poi_list": [
        {"id": "A", "name": "西湖", "address": "杭州", "longitude": "120.15", "latitude": "30.25"},
        {"id": "card", "name": "广告", "item_type": "card", "longitude": 120, "latitude": 30},
        {"id": "A", "name": "重复", "longitude": 120, "latitude": 30},
        {"id": "missing", "name": "联想词"},
    ]}))
    assert places == [{"id": "A", "name": "西湖", "address": "杭州", "location": [120.15, 30.25]}]


@pytest.mark.parametrize("value", [
    b"<html>blocked</html>", b"{}", raw({"code": 0, "message": "failed", "poi_list": []}),
    raw({"code": 1}), raw({"code": 1, "poi_list": {}}),
    raw({"code": 1, "poi_list": [{"id": "a", "name": "X", "longitude": "NaN", "latitude": 30}]}),
])
def test_rejects_non_success_or_unusable_response(value):
    with pytest.raises(SearchResponseError):
        parse_infolite(value)


def test_empty_success_is_not_an_error():
    assert parse_infolite(raw({"code": "1", "poi_list": []})) == []


def test_keeps_first_valid_apk_entrance_separate_from_poi_center():
    places = parse_infolite(raw({"code": 1, "poi_list": [{
        "id": "A", "name": "西湖入口", "longitude": 120.15, "latitude": 30.25,
        "entrances": [{"longitude": "bad", "latitude": 30.25},
                      {"longitude": 120.151, "latitude": 30.251}],
    }]}))
    assert places == [{"id": "A", "name": "西湖入口", "address": "",
                       "location": [120.15, 30.25], "entrance": [120.151, 30.251]}]


def test_bounded_input():
    with pytest.raises(SearchResponseError):
        parse_infolite(b"x" * (1024 * 1024 + 1))
