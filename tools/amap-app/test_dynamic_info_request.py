import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from dynamic_info_request import app_epoch_seconds, known_fresh_install_common, signed_query


def test_body_only_fields_are_not_present_in_url_or_sign():
    query = signed_query("chn", "secret")
    assert query == {
        "channel": "chn", "output": "json",
        "sign": hashlib.md5(b"chn@secret").hexdigest().upper(),
    }


def test_declared_sign_keys_without_query_values_do_not_change_sign():
    query = signed_query("chn", "secret")
    assert "e_poiid" not in query
    assert "user_loc" not in query
    assert query["sign"] == hashlib.md5(b"chn@secret").hexdigest().upper()


@pytest.mark.parametrize("channel,key", [("", "secret"), ("chn", "")])
def test_missing_signing_material_rejected(channel, key):
    with pytest.raises(ValueError):
        signed_query(channel, key)


def test_apk_local_epoch_and_known_fresh_install_common_values():
    shanghai = timezone(timedelta(hours=8))
    when = datetime(2011, 1, 1, 0, 0, 42, tzinfo=shanghai)
    assert app_epoch_seconds(when) == 42
    common = known_fresh_install_common(when, step_id=3)
    assert common["session"] == common["appstartid"] == "42"
    assert common["stepid"] == "3"
    assert common["diu2"] == ""
    assert common["div"] == common["siv"] == "ANDH170000"
    assert common["dibv"] == "2005"
    assert "diu" not in common  # The APK reads this from its device state.
    assert app_epoch_seconds(datetime(2011, 7, 1, tzinfo=ZoneInfo("America/New_York"))) == 181 * 86400 - 3600


def test_apk_epoch_requires_device_timezone_and_positive_step():
    with pytest.raises(ValueError):
        app_epoch_seconds(datetime(2026, 10, 2))
    with pytest.raises(ValueError):
        known_fresh_install_common(datetime.now(timezone.utc), 0)
