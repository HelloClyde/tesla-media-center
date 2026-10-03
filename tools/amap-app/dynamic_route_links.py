"""APK native dynamic-info route_links wire encoding.

The native event's first link is an unsigned 64-bit decimal ID; subsequent
entries are signed 64-bit decimal deltas from the preceding ID. Saved 5.1
route responses also expose a base and ZigZag deltas that recover stable
candidate link IDs across alternate paths and different origins. Direct
identity with the native event still needs confirmation.
"""

from collections.abc import Iterable, Sequence


U64 = 1 << 64


def encode_link_ids(link_ids: Iterable[int]) -> list[str]:
    encoded: list[str] = []
    previous = 0
    for index, current in enumerate(link_ids):
        if isinstance(current, bool) or not isinstance(current, int) or not 0 <= current < U64:
            raise ValueError("link ID outside unsigned 64-bit range")
        if index == 0:
            encoded.append(str(current))
        else:
            delta = (current - previous) % U64
            encoded.append(str(delta if delta < (1 << 63) else delta - U64))
        previous = current
    return encoded


def encode_segment_link_ids(segments: Sequence[Sequence[int]]) -> list[str]:
    """Mirror the native event's per-segment link-ID string construction.

    The first segment starts with an absolute unsigned ID. Later segments
    start with a signed delta from the first included link ID; remaining IDs
    in each segment are deltas from their predecessor. The caller must supply
    the route's selected segment range and its actual native link IDs.
    """
    if not segments or any(not segment for segment in segments):
        raise ValueError("empty route segment")
    anchor = segments[0][0]
    if isinstance(anchor, bool) or not isinstance(anchor, int) or not 0 <= anchor < U64:
        raise ValueError("link ID outside unsigned 64-bit range")
    result: list[str] = []
    for segment_index, segment in enumerate(segments):
        previous = anchor
        encoded: list[str] = []
        for link_index, current in enumerate(segment):
            if isinstance(current, bool) or not isinstance(current, int) or not 0 <= current < U64:
                raise ValueError("link ID outside unsigned 64-bit range")
            if segment_index == 0 and link_index == 0:
                encoded.append(str(current))
            else:
                delta = (current - previous) % U64
                encoded.append(str(delta if delta < (1 << 63) else delta - U64))
            previous = current
        result.append(",".join(encoded))
    return result


def encode_link_boundary_properties(segments: Sequence[Sequence[tuple[int, int]]]) -> list[str]:
    """Format each segment's first/last link properties as the Horus event does.

    The two integers come from link virtual slots +0xf0 and +0xe8. This
    formatter does not establish how a 5.1 route populates those slots.
    """
    if not segments or any(not segment for segment in segments):
        raise ValueError("empty route segment")
    result: list[str] = []
    for segment in segments:
        selected = [segment[0]] if len(segment) == 1 else [segment[0], segment[-1]]
        encoded: list[str] = []
        for pair in selected:
            if not isinstance(pair, tuple) or len(pair) != 2 or any(
                type(value) is not int or not -(1 << 31) <= value < (1 << 31) for value in pair
            ):
                raise ValueError("invalid link boundary property")
            encoded.append(f"{pair[0]}-{pair[1]}")
        result.append(",".join(encoded))
    return result


def encode_link_adcodes(segments: Sequence[Sequence[int]]) -> dict[str, str]:
    """Encode the Horus `links_adcode` map from effective per-link codes.

    Link positions are one-based across the selected segment window. A run is
    written as ``start,end``; multiple runs for a code join with ``-``. The
    native builder skips a zero-code run on a transition, but flushes the
    final run even when its code is zero.
    """
    if not segments or any(not segment for segment in segments):
        raise ValueError("empty route segment")
    codes: list[int] = []
    for segment in segments:
        for code in segment:
            if type(code) is not int or not 0 <= code <= 0xFFFFFFFF:
                raise ValueError("invalid link adcode")
            codes.append(code)
    runs: dict[int, list[str]] = {}
    previous, start = 0, 0
    for position, code in enumerate(codes, 1):
        if code != previous:
            if previous:
                runs.setdefault(previous, []).append(f"{start},{position - 1}")
            previous, start = code, position
    runs.setdefault(previous, []).append(f"{start},{len(codes)}")
    return {str(code): "-".join(runs[code]) for code in sorted(runs)}


def decode_link_ids(encoded: Sequence[str]) -> list[int]:
    decoded: list[int] = []
    previous = 0
    for index, text in enumerate(encoded):
        if not isinstance(text, str) or not text or text.strip() != text:
            raise ValueError("invalid link ID text")
        value = int(text, 10)
        if index == 0:
            if not 0 <= value < U64:
                raise ValueError("first link ID outside unsigned 64-bit range")
            current = value
        else:
            if not -(1 << 63) <= value < (1 << 63):
                raise ValueError("link delta outside signed 64-bit range")
            current = (previous + value) % U64
        decoded.append(current)
        previous = current
    return decoded


def decode_v51_link_deltas(base: int, encoded_deltas: Iterable[int]) -> list[int]:
    """Recover candidate link IDs from a 5.1 route base and ZigZag deltas.

    The saved route corpus confirms that exact shared links converge to the
    same IDs across route alternatives and different origins. The mapping to
    the native interaction event still needs direct confirmation.
    """
    if isinstance(base, bool) or not isinstance(base, int) or not 0 <= base < U64:
        raise ValueError("invalid 5.1 link base")
    current = base
    result: list[int] = []
    for raw in encoded_deltas:
        if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw < U64:
            raise ValueError("invalid 5.1 link delta")
        current = (current + ((raw >> 1) ^ -(raw & 1))) % U64
        result.append(current)
        if len(result) > 100000:
            raise ValueError("too many 5.1 links")
    return result
