"""Summarize local Amap elevated-fork evidence without exposing signed URLs.

The route and heap are research captures supplied by the caller. No network
request is sent, and device/session/signature values are never printed.
"""

import argparse
import json
import mmap
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


def route_link_records(route_path):
    """Decode ordered link IDs and action values from each 5.1 route."""
    envelope = fields(unpack(route_path.read_bytes()))
    message = fields(one(envelope, 2, b""))
    results = []
    for route_blob in message.get(7, []):
        route = fields(route_blob)
        base = int.from_bytes(one(route, 9, b""), "little")
        deltas = []
        main_actions = []
        assist_actions = []
        segment_link_counts = []
        for segment_blob in route.get(10, []):
            segment = fields(segment_blob)
            links = segment.get(3, [])
            if not links:
                raise ValueError("route segment without links")
            deltas.extend(one(fields(link_blob), 1) for link_blob in links)
            main_actions.extend([0] * (len(links) - 1) + [one(segment, 1, 0)])
            assist_actions.extend([0] * (len(links) - 1) + [one(segment, 2, 0)])
            segment_link_counts.append(len(links))
        results.append({"ids": decode_v51_link_deltas(base, deltas),
                        "main_actions": main_actions,
                        "assist_actions": assist_actions,
                        "segment_link_counts": segment_link_counts})
    return results


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
    route_ids = [route["ids"] for route in route_link_records(route_path)]
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


def inspect_original_v4_bodies(route_path, disk_path):
    """Find native V4 cross requests in a local, read-only emulator disk image.

    Guest memory may be present in the virtual disk's physical pages. Match
    decoded route-link IDs without publishing account, device or session IDs.
    This does not imply that the matching HTTP response was captured.
    """
    routes = route_link_records(route_path)

    needle = b'{"protocolVer":"4.0"'
    unique = set()
    matches = []
    with disk_path.open("rb") as source, mmap.mmap(source.fileno(), 0,
                                                   access=mmap.ACCESS_READ) as image:
        cursor = 0
        while (offset := image.find(needle, cursor)) != -1:
            cursor = offset + len(needle)
            # The native body is under 1 KiB in observed samples; cap parsing
            # to prevent unrelated guest-memory strings from consuming memory.
            sample = image[offset:offset + 16_384].decode("utf-8", "replace")
            try:
                body, _ = json.JSONDecoder().raw_decode(sample)
            except json.JSONDecodeError:
                continue
            path = body.get("pathInfo", {})
            deltas = path.get("linkids", [])
            first = path.get("firstLinkID")
            if type(first) is not int or not isinstance(deltas, list) or not deltas:
                continue
            ids = []
            current = first
            for delta in deltas:
                if type(delta) is not int:
                    break
                current += delta
                ids.append(current)
            if len(ids) != len(deltas):
                continue
            key = (body.get("naviID"), tuple(ids))
            if key in unique:
                continue
            unique.add(key)
            for route_index, route in enumerate(routes):
                route_ids = route["ids"]
                start = next((index for index in range(len(route_ids) - len(ids) + 1)
                              if route_ids[index:index + len(ids)] == ids), None)
                if start is not None:
                    main = path.get("mainActions")
                    assist = path.get("assistActions")
                    main_expected = route["main_actions"][start:start + len(ids)]
                    assist_expected = route["assist_actions"][start:start + len(ids)]
                    matches.append({"route": route_index,
                                    "route_links": len(route_ids),
                                    "cross_request_links": len(ids),
                                    "start_link": start,
                                    "first_segment": path.get("firstSegIndex"),
                                    "segment_link_counts": path.get("segments"),
                                    "cross_type": body.get("crossType"),
                                    "dimensions": [body.get("width"), body.get("height")],
                                    "main_actions_exact": main == main_expected,
                                    "assistant_actions_matching": sum(
                                        x == y for x, y in zip(assist, assist_expected))
                                        if isinstance(assist, list) and len(assist) == len(ids) else 0,
                                    "body_fields": sorted(body),
                                    "path_fields": sorted(path),
                                    "exact_contiguous_match": True})
    return {"v4_bodies_found": len(unique),
            "route_matches": sorted(matches, key=lambda item: (item["route"],
                                                                item["start_link"]))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path)
    parser.add_argument("--heap", type=Path)
    parser.add_argument("--disk-image", type=Path,
                        help="optional local BlueStacks VHDX; read-only scan")
    args = parser.parse_args()
    if not args.route and not args.heap:
        parser.error("specify --route and/or --heap")
    if args.disk_image and not args.route:
        parser.error("--disk-image requires --route")
    result = {}
    if args.route:
        result["routes"] = inspect_route(args.route)
    if args.heap:
        result["live_cross_requests"] = inspect_heap(args.heap)
    if args.route and args.heap:
        result["live_lane_link_matches"] = compare_live_link_windows(args.route, args.heap)
    if args.route and args.disk_image:
        result["original_v4_cross_bodies"] = inspect_original_v4_bodies(
            args.route, args.disk_image)
    print(json.dumps(result, ensure_ascii=False, indent=2))
