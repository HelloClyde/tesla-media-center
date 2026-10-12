"""Synthetic schema/bounds checks; these are not captured live warnings."""
import json

import pytest

from vehicle_warning_push import decode_warning_interaction, MAX_RECORDS, MAX_PUSH_BYTES


def interaction(scene="curveMeet", *, meta=None, show=None, record=None):
    body = {"metaInfo": meta if meta is not None else {
        "pushId": "synthetic-case", "pushType": 1, "pushTime": "unverified-clock"},
        "data": {"v2xSafe": {"show": show if show is not None else {
            "sceneType": scene, "warningLevel": 2, "sceneData": "opaque"}}}}
    return json.dumps({"interactionHorus": [record if record is not None else {
        "bizType": 1, "bizData": json.dumps(body)}]})


@pytest.mark.parametrize("scene", ["curveMeet", "nodeMeet", "rearFastCar", "rearFastTruckRemind"])
def test_known_warning_schema_preserves_native_fields_without_inventing_data(scene):
    result = decode_warning_interaction(interaction(scene))[0]
    assert result.scene_type == scene
    assert result.push_id == "synthetic-case"
    assert result.push_type == 1
    assert result.push_time == "unverified-clock"
    assert result.warning_level == 2
    assert result.scene_data == "opaque"
    assert not hasattr(result, "point")
    assert not hasattr(result, "expires_at")


def test_other_module_and_missing_show_are_not_warnings():
    assert decode_warning_interaction(interaction("unknown")) == []
    assert decode_warning_interaction(interaction(show={})) == []
    assert decode_warning_interaction(json.dumps({"interactionHorus": []})) == []


def test_metadata_is_push_metadata_not_the_separate_path_metadata():
    assert decode_warning_interaction(interaction(meta={"pathId": "123", "traceId": "abc"})) == []
    assert decode_warning_interaction(interaction(meta={"pushId": ""})) == []


@pytest.mark.parametrize("record", [None, {}, {"bizType": "trafficserviceJson", "bizData": "{}"},
                                   {"bizType": True, "bizData": "{}"},
                                   {"bizType": 1, "bizData": "{"},
                                   {"bizType": 1, "bizData": "[]"}])
def test_malformed_record_is_ignored(record):
    assert decode_warning_interaction(json.dumps({"interactionHorus": [record]})) == []


@pytest.mark.parametrize("value", [True, "2", 2**31, float("nan")])
def test_warning_level_does_not_coerce_invalid_values(value):
    assert decode_warning_interaction(interaction(show={"sceneType": "rearFastCar", "warningLevel": value})) == []


def test_missing_optional_fields_are_not_defaulted_to_live_values():
    result = decode_warning_interaction(interaction(meta={"pushId": "synthetic-case"},
        show={"sceneType": "rearFastCar"}))[0]
    assert result.push_type is result.push_time is result.warning_level is result.scene_data is None


@pytest.mark.parametrize("value", ["[]", "{}", "{", " " * (MAX_PUSH_BYTES + 1),
                                   json.dumps({"interactionHorus": [{}] * (MAX_RECORDS + 1)})],
                         ids=["array", "missing-records", "bad-json", "too-many-bytes", "too-many-records"])
def test_invalid_and_oversized_envelope_is_rejected(value):
    with pytest.raises(ValueError):
        decode_warning_interaction(value)
