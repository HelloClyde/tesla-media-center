"""Build the APK dynamic-info endpoint's AJX URL signing parameters.

This does not claim that the JSON body contains a valid navigation session.
"""

from datetime import datetime

from aos_request_sign import sign


SIGN_FIELDS = ("channel", "e_poiid", "user_loc")


def app_epoch_seconds(when: datetime) -> int:
    """Mirror `gj0.k()`: local seconds since the device's 2011 epoch."""
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("device timezone required")
    base = datetime(2011, 1, 1, tzinfo=when.tzinfo)
    # Timestamp subtraction includes any offset/DST change since 2011; plain
    # subtraction of two datetimes sharing one tzinfo would use wall time.
    return int(when.timestamp() - base.timestamp())


def known_fresh_install_common(when: datetime, step_id: int = 1) -> dict[str, str]:
    """Return only APK-backed common values, not missing device/session data.

    A real App memoizes session and appstartid independently at startup. This
    fresh-process control uses one timestamp for both; it is not a captured
    request and does not reproduce SecurityGuard headers.
    """
    if type(step_id) is not int or step_id < 1:
        raise ValueError("invalid request step")
    uptime = str(app_epoch_seconds(when))
    return {"div": "ANDH170000", "siv": "ANDH170000", "dip": "10880",
            "dic": "C3060", "dib": "a", "aetraffic": "9", "dibv": "2005",
            "diu2": "", "buildABI": "arm64-v8a", "session": uptime,
            "appstartid": uptime, "stepid": str(step_id)}


def signed_query(channel: str, aos_key: str) -> dict[str, str]:
    """Return a minimal post-common-param query for a research probe.

    ``e_poiid`` and ``user_loc`` occur only in the JSON body. The native
    AosRequest signer does not read that body, so they contribute no values
    unless a caller explicitly supplies them as URL or extended parameters.
    The App supplies ``channel`` through its AOS common-param provider; other
    common params are intentionally omitted here and this is not a complete
    App wire request.
    """
    if not channel or not aos_key:
        raise ValueError("missing AOS signing material")
    # AosRequest.getAosCommonParam(true) adds output=json for AOS requests.
    query = {"channel": channel, "output": "json"}
    query["sign"] = sign(SIGN_FIELDS, {}, {"channel": channel}, aos_key)
    return query
