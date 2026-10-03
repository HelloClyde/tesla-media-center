"""Summarize local Amap elevated-fork evidence without exposing signed URLs.

The route and heap are research captures supplied by the caller. No network
request is sent, and device/session/signature values are never printed.
"""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlsplit

from native_body_codec import decode as decode_aos_query
from route_v51 import decode as decode_route


ENDPOINT = b"https://m5.amap.com/ws/transfer/auth/new_vector_cross/"
ELEVATED = ("高架", "快速", "立交")


def inspect_route(path):
    routes = decode_route(path.read_bytes())
    return [
        {
            "route": route_index,
            "distance_m": route["distance"],
            "elevated_steps": [
                {
                    "index": index,
                    "road": step["road"],
                    "action": step["actionCode"],
                    "assistant_action": step["assistantActionCode"],
                    "start": route["path"][step["start"]],
                    "end": route["path"][step["end"]],
                }
                for index, step in enumerate(route["steps"])
                if any(word in step["road"] for word in ELEVATED)
            ],
        }
        for route_index, route in enumerate(routes)
    ]


def inspect_heap(path):
    data = path.read_bytes()
    # HPROF byte arrays contain the live request URL, not necessarily an
    # HPROF UTF-8 string record. Stop at the first non-printable byte.
    pattern = re.compile(re.escape(ENDPOINT) + rb"[^\x00-\x20]{0,1800}")
    records = set()
    for match in pattern.finditer(data):
        url = match.group().decode("ascii", "replace")
        outer = parse_qs(urlsplit(url).query)
        if "in" not in outer:
            continue
        try:
            inner = dict(parse_qsl(decode_aos_query(outer["in"][0]),
                                   keep_blank_values=True))
        except (ValueError, KeyError):
            continue
        records.add((tuple(sorted(outer)), tuple(sorted(inner)),
                     inner.get("cross_ver", ""), inner.get("sdk_version", "")))
    return [
        {
            "endpoint": ENDPOINT.decode(),
            "outer_keys": outer,
            "inner_keys": inner,
            "cross_ver": cross_ver,
            "sdk_version": sdk_version,
        }
        for outer, inner, cross_ver, sdk_version in sorted(records)
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path)
    parser.add_argument("--heap", type=Path)
    args = parser.parse_args()
    if not args.route and not args.heap:
        parser.error("specify --route and/or --heap")
    result = {}
    if args.route:
        result["routes"] = inspect_route(args.route)
    if args.heap:
        result["live_cross_requests"] = inspect_heap(args.heap)
    print(json.dumps(result, ensure_ascii=False, indent=2))
