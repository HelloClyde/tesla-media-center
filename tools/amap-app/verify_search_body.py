"""Offline check of the pinned APK's keyword-search form-body codec.

Uses synthetic context only. This verifies serialization and the APK's string
codec round trip; it does not generate SecurityGuard headers or send a request.
"""

from __future__ import annotations

import json
from pathlib import Path

from native_body_codec import decode, encode
from search_request import keyword_params, prepare_post


def verify(asset_dir: Path | None = None) -> dict[str, object]:
    fields = keyword_params(
        "杭州西湖", geoobj="120|30|121|31",
        user_loc="120.1,30.2", user_city="330100", siv="research",
    )
    common = {"channel": "research", "div": "research", "siv": "research"}
    original: list[str] = []

    def encode_form(form: str) -> str:
        original.append(form)
        return encode(form, asset_dir)

    post = prepare_post(fields, common, "research", encode_body=encode_form,
                        csid="research")
    encoded = post["body"].decode("utf-8")
    if len(original) != 1 or decode(encoded, asset_dir) != original[0]:
        raise RuntimeError("APK search-body codec round trip failed")
    return {
        "path": post["path"],
        "formFields": len(original[0].split("&")),
        "encodedBytes": len(post["body"]),
        "roundTrip": True,
        "networkRequestSent": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))
