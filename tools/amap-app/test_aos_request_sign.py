import hashlib

from aos_request_sign import sign, sign_input


def test_apk_field_order_and_fallback():
    original_fields = ["e_poiid", "_aosmd5", "channel", "user_loc"]
    assert sign_input(
        original_fields,
        {"e_poiid": "", "user_loc": "120.1,30.2"},
        {"channel": "chn", "e_poiid": "common"},
        "secret", {"e_poiid": "poi"},
    ) == "chnpoi120.1,30.2@secret"
    assert original_fields == ["e_poiid", "_aosmd5", "channel", "user_loc"]


def test_known_route_adapter_formula():
    fields = ["fromX", "fromY", "toX", "toY"]
    coordinates = dict(zip(fields, ["120.1", "30.2", "120.3", "30.4"]))
    expected = hashlib.md5(b"chn120.130.2120.330.4@secret").hexdigest().upper()
    assert sign(fields, coordinates, {"channel": "chn"}, "secret") == expected


def test_missing_and_unicode_values():
    expected = hashlib.md5("chn终点@secret".encode("utf-8")).hexdigest().upper()
    assert sign(["e_poiid", "user_loc"], {"e_poiid": "终点"}, {"channel": "chn"}, "secret") == expected


def test_eta_native_mask_0x491_signs_only_nonempty_channel_and_div():
    query = {
        "channel": "chn",
        "diu": "",
        "div": "ANDH170000",
        "sdk_version": "17.00.0.1007",
    }
    assert sign_input(
        ("channel", "diu", "div", "_aosmd5"), query, {}, "secret"
    ) == "chnANDH170000@secret"
