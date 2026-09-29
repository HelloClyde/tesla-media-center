"""Bounded decoder for the consumer App's 5.1 driving response.

The envelope and record headers follow DrivePathCodecImpl (32 bytes each).
Only the route record (type 1) is consumed; optional records remain opaque.
Coordinates are packed zigzag deltas in 1/3,600,000 degree units, with a
fresh absolute first coordinate for every segment. No missing geometry is
interpolated. Distances exposed here are measured along decoded geometry.
"""
import math
import struct

LIMIT = 16 * 1024 * 1024


def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            if value >= 1 << 64:
                raise ValueError("oversized varint")
            return value, offset
    raise ValueError("oversized varint")


def fields(data):
    if len(data) > LIMIT:
        raise ValueError("protobuf size")
    result, offset = {}, 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number or number >= 1 << 29:
            raise ValueError("invalid protobuf tag")
        if wire == 0:
            value, offset = varint(data, offset)
        else:
            if wire == 2:
                size, offset = varint(data, offset)
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
            else:
                raise ValueError("unsupported wire type")
            if offset + size > len(data):
                raise ValueError("truncated field")
            value = data[offset:offset + size]
            offset += size
        result.setdefault(number, []).append(value)
    return result


def one(message, key, default=None):
    values = message.get(key, [])
    if len(values) > 1:
        raise ValueError("duplicate singular field")
    return values[0] if values else default


def delta_values(data):
    offset, total, values = 0, 0, []
    while offset < len(data):
        value, offset = varint(data, offset)
        total += (value >> 1) ^ -(value & 1)
        values.append(total / 3600000)
        if len(values) > 100000:
            raise ValueError("too many coordinates")
    return values


def distance(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 12742000 * math.asin(min(1, math.sqrt(h)))


def unpack(raw):
    import zstandard
    if len(raw) < 74 or len(raw) > LIMIT:
        raise ValueError("response size")
    status, size = struct.unpack_from("<HQ", raw)
    if status != 200 or size > len(raw) - 10 or size < 64:
        raise ValueError("response envelope")
    body = raw[10:10 + size]
    version, count, declared = struct.unpack_from("<IHI", body)
    if version != 31 or declared != size or not 1 <= count <= 64:
        raise ValueError("unsupported route envelope")
    offset, route_data = 32, None
    for _ in range(count):
        if offset + 32 > len(body):
            raise ValueError("truncated record")
        compression, kind, packed, unpacked = struct.unpack_from("<HHII", body, offset)
        offset += 32
        if offset + packed > len(body) or unpacked > LIMIT:
            raise ValueError("record size")
        block = body[offset:offset + packed]
        offset += packed
        if kind != 1:
            continue
        if route_data is not None:
            raise ValueError("duplicate route record")
        if compression == 2:
            # Reject concatenated/trailing compressed data and decompression bombs.
            content_size = zstandard.frame_content_size(block)
            if content_size not in (zstandard.CONTENTSIZE_UNKNOWN, zstandard.CONTENTSIZE_ERROR) and content_size > LIMIT:
                raise ValueError("compressed frame size")
            route_data = zstandard.ZstdDecompressor().decompress(block, max_output_size=LIMIT, allow_extra_data=False)
        elif compression == 0:
            route_data = block
        else:
            raise ValueError("unsupported compression")
        if len(route_data) != unpacked:
            raise ValueError("unpacked size")
    if offset != len(body) or route_data is None:
        raise ValueError("incomplete route envelope")
    return route_data


def route_summary(route):
    # v5.1 route.7 is the planned travel time in seconds; route.4 is
    # the toll summary (1: minor currency units, 2: charged distance, 5: currency).
    duration = one(route, 7, None)
    duration = duration if type(duration) is int and 0 < duration <= 30 * 86400 else None
    tolls = currency = None
    if 4 in route:
        try:
            toll = fields(one(route, 4))
            amount = one(toll, 1, None)
            currency = one(toll, 5, b'CNY').decode('ascii')
            if type(amount) is int and 0 <= amount <= 100000000 and currency == 'CNY':
                tolls = amount / 100
            else:
                currency = None
        except (ValueError, TypeError, UnicodeError, AttributeError):
            currency = None
    return {'duration': duration, 'tolls': tolls, 'tollCurrency': currency}


def decode(raw, origin=None, destination=None):
    outer = fields(unpack(raw))
    header = fields(one(outer, 1, b""))
    if one(header, 1) != 51 or one(header, 3) != 0:
        raise ValueError("unsupported route version/status")
    message = fields(one(outer, 2, b""))
    if one(message, 1) != 0:
        raise ValueError("route failure")
    names = one(message, 5, b"")
    routes = []
    for route_raw in message.get(7, []):
        route = fields(route_raw)
        path, steps, measured, breaks = [], [], 0.0, []
        current_road = "道路"
        for segment_raw in route.get(10, []):
            segment = fields(segment_raw)
            coordinates = fields(one(segment, 4, b""))
            xs = delta_values(one(coordinates, 1, b""))
            ys = delta_values(one(coordinates, 2, b""))
            if len(xs) != len(ys) or len(xs) < 2:
                raise ValueError("incomplete segment geometry")
            points = [list(point) for point in zip(xs, ys)]
            if any(not -180 <= x <= 180 or not -90 <= y <= 90 for x, y in points):
                raise ValueError("coordinate bounds")
            # App geometries omit some junction connectors. Preserve separate
            # polylines instead of inventing a connector across an intersection.
            if path and distance(path[-1], points[0]) > 100:
                raise ValueError("discontinuous route geometry")
            links = [fields(item) for item in segment.get(3, [])]
            covered = 0
            for link in links:
                span = fields(one(link, 8, b""))
                start, count = one(span, 1, 0), one(span, 2, 0)
                if start != covered or count < 2 or start + count > len(points):
                    raise ValueError("link coordinate coverage")
                covered = start + count - 1
            if links and covered != len(points) - 1:
                raise ValueError("unused segment coordinates")
            for link in links:
                if 7 not in link:
                    continue
                attributes = fields(one(link, 7))
                span = fields(one(attributes, 9, b""))
                start, length = one(span, 1, 0), one(span, 2, 0)
                if start + length > len(names):
                    raise ValueError("road name bounds")
                if length:
                    current_road = names[start:start + length].decode("utf-8")
                    break
            if path and path[-1] == points[0]:
                start_index = len(path) - 1
                path.extend(points[1:])
            else:
                start_index = len(path)
                if path:
                    breaks.append(start_index)
                path.extend(points)
            length = sum(distance(a, b) for a, b in zip(points, points[1:]))
            steps.append({"road": current_road, "start": start_index, "end": len(path) - 1,
                          "distance": round(length, 1), "actionCode": one(segment, 1, 0)})
            measured += length
        if not steps or len(path) > 100000:
            raise ValueError("missing/oversized geometry")
        if origin and distance(origin, path[0]) > 1000:
            raise ValueError("route origin mismatch")
        if destination and distance(destination, path[-1]) > 1000:
            raise ValueError("route destination mismatch")
        reported = one(route, 1, 0) / 100
        if not reported or abs(reported - measured) > max(100, reported * .15):
            raise ValueError("route distance mismatch")
        labels = [one(fields(item), 2, b"").decode("utf-8") for item in route.get(12, [])]
        routes.append({"id": len(routes), "labels": labels, "path": path, "steps": steps, "breaks": breaks,
                       **route_summary(route), "distance": round(measured), "roads": list(dict.fromkeys(step["road"] for step in steps))})
    if not 1 <= len(routes) <= 10:
        raise ValueError("route count")
    return routes
