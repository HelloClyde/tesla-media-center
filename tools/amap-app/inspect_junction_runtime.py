"""Summarize local Amap elevated-fork evidence without exposing signed URLs.

The route and heap are research captures supplied by the caller. No network
request is sent, and device/session/signature values are never printed.
"""

import argparse
import json
import re
import zlib
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlsplit

from dynamic_route_links import decode_v51_link_deltas
from native_body_codec import decode as decode_aos_query
from route_v51 import decode as decode_route
from route_v51 import fields, one, unpack


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


def compare_live_link_windows(route_path, heap_path):
    """Check native route-link decoding against live App lane request IDs.

    The gzip JSON is the App's lane-suggestion request, not a cross-image
    response. A contiguous identity check confirms the underlying link IDs
    without exposing their values or conflating the two endpoints.
    """
    envelope = fields(unpack(route_path.read_bytes()))
    message = fields(one(envelope, 2, b""))
    route_ids = []
    for route_blob in message.get(7, []):
        route = fields(route_blob)
        base = int.from_bytes(one(route, 9, b""), "little")
        deltas = [
            one(fields(link_blob), 1)
            for segment_blob in route.get(10, [])
            for link_blob in fields(segment_blob).get(3, [])
        ]
        route_ids.append(decode_v51_link_deltas(base, deltas))
    data = heap_path.read_bytes()
    windows = set()
    for match in re.finditer(rb"\x1f\x8b\x08", data):
        try:
            stream = zlib.decompressobj(31)
            payload = stream.decompress(data[match.start():match.start() + 2_000_000], 8_000_000)
            if not stream.eof or not payload.startswith(b"{"):
                continue
            body = json.loads(payload)
        except (zlib.error, json.JSONDecodeError):
            continue
        links = body.get("linkInfos") if isinstance(body, dict) else None
        if isinstance(links, list) and links and all(
                isinstance(link, dict) and type(link.get("linkId")) is int for link in links):
            windows.add(tuple(link["linkId"] for link in links))
    matches = []
    for window in windows:
        for route_index, ids in enumerate(route_ids):
            start = next((index for index in range(len(ids) - len(window) + 1)
                          if tuple(ids[index:index + len(window)]) == window), None)
            if start is not None:
                matches.append({"route": route_index, "route_links": len(ids),
                                "live_window_links": len(window), "start_link": start,
                                "exact_contiguous_match": True})
    return sorted(matches, key=lambda item: (item["route"], item["start_link"],
                                             item["live_window_links"]))


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
    if args.route and args.heap:
        result["live_lane_link_matches"] = compare_live_link_windows(args.route, args.heap)
    print(json.dumps(result, ensure_ascii=False, indent=2))
