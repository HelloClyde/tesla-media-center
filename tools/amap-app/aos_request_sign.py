"""Reconstruct the APK's AosRequest sign-field assembly for local research.

The value digest matches the pinned App's existing, verified route adapter.
This module intentionally does not store or print the APK's signing material.
"""

import hashlib
from collections.abc import Mapping, Sequence


def sign_input(
    fields: Sequence[str],
    request_params: Mapping[str, str | None],
    common_params: Mapping[str, str | None],
    aos_key: str,
    extended_params: Mapping[str, str | None] | None = None,
) -> str:
    """Build AosRequest.buildHttpRequest's input to IAosEncryptor.sign.

    The APK moves channel to the front, removes _aosmd5, and looks up each
    value first in request params, then extended params, then common params.
    Empty values fall through to the next source; missing values append nothing.
    """
    ordered = list(fields)
    if "channel" in ordered:
        ordered.remove("channel")
    ordered.insert(0, "channel")
    if "_aosmd5" in ordered:
        ordered.remove("_aosmd5")
    extended_params = extended_params or {}
    values: list[str] = []
    for field in ordered:
        value = request_params.get(field)
        if not value:
            value = extended_params.get(field)
        if not value:
            value = common_params.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a string")
            values.append(value)
    return "".join(values) + "@" + aos_key


def sign(
    fields: Sequence[str],
    request_params: Mapping[str, str | None],
    common_params: Mapping[str, str | None],
    aos_key: str,
    extended_params: Mapping[str, str | None] | None = None,
) -> str:
    return hashlib.md5(
        sign_input(fields, request_params, common_params, aos_key, extended_params).encode("utf-8")
    ).hexdigest().upper()
