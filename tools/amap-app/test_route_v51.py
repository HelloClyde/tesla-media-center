import struct
import unittest
from route_v51 import decode, fields, unpack, route_summary, service_area_name


def vi(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out) + bytes([value])


def msg(**items):
    out = b""
    for key, value in items.items():
        tag = int(key[1:])
        for v in value if isinstance(value, list) else [value]:
            out += vi(tag * 8 + (2 if isinstance(v, bytes) else 0))
            out += vi(len(v)) + v if isinstance(v, bytes) else vi(v)
    return out


def packed(values):
    previous, result = 0, b""
    for value in values:
        delta = round(value * 3600000) - previous
        previous += delta
        result += vi((delta << 1) ^ (delta >> 63))
    return result


def fixture(xs=(116.4, 116.401), ys=(39.9, 39.9), link_flags=None, facility=None, assistant_action=0,
            link_statuses=None, link_times=None, action=2, ring_flags=None, ring_entry=False,
            route_metadata=0, header_status=0):
    links = {} if link_flags is None else {'f3': msg(f6=link_flags, f8=msg(f1=0, f2=2))}
    if link_statuses is not None:
        links = {'f3': [msg(f2=round(8500 / len(link_statuses)), f3=status,
                            f8=msg(f1=index, f2=2),
                            **({'f5': link_times[index]} if link_times is not None
                               and link_times[index] is not None else {}))
                        for index, status in enumerate(link_statuses)]}
    if ring_flags is not None:
        links = {'f3': [msg(f6=flag, f8=msg(f1=index, f2=2))
                        for index, flag in enumerate(ring_flags)]}
    segment = msg(f1=action, f2=assistant_action, f4=msg(f1=packed(xs), f2=packed(ys)),
                  **links, **({'f5': msg(f1=200, f2=8500, f3=b'G60', f4=facility.encode())} if facility else {}))
    segments = [segment]
    if ring_entry:
        segments.insert(0, msg(f1=11, f2=0, f4=msg(f1=packed((xs[0] - .001, xs[0])),
                                                  f2=packed((ys[0], ys[0])))))
    protobuf = msg(f1=msg(f1=51, f3=header_status), f2=msg(f1=route_metadata, f5=b"", f7=msg(f1=8500 * len(segments), f10=segments)))
    size = 64 + len(protobuf)
    body = struct.pack('<IHI', 31, 1, size).ljust(32, b'\0')
    body += struct.pack('<HHII', 0, 1, len(protobuf), len(protobuf)).ljust(32, b'\0') + protobuf
    return struct.pack('<HQ', 200, size) + body


def road_link_fixture(base=9007199254740993, link_type=2):
    tunnel, surface = '环城隧道'.encode(), '环城路'.encode()
    names = tunnel + surface
    segments = []
    specs = [
        ((116.4, 116.4003, 116.4006), [
            msg(f1=0, f8=msg(f1=0, f2=2), f7=msg(f1=4, f2=7, f3=link_type, f9=msg(f1=0, f2=len(tunnel)))),
            msg(f1=2, f8=msg(f1=1, f2=2))]),
        ((116.4006, 116.4008, 116.401), [
            msg(f1=1, f8=msg(f1=0, f2=2), f7=msg(f1=2, f2=1, f9=msg(f1=len(tunnel), f2=len(surface)))),
            msg(f1=4, f8=msg(f1=1, f2=2), f7=msg(f2=5))]),
        ((116.4011, 116.4013), [msg(f1=3, f8=msg(f1=0, f2=2))])]
    for xs, links in specs:
        segments.append(msg(f3=links, f4=msg(f1=packed(xs), f2=packed((39.9,) * len(xs)))))
    protobuf = msg(f1=msg(f1=51, f3=0), f2=msg(f1=0, f5=names,
                    f7=msg(f1=12500, f9=base if isinstance(base, bytes) else struct.pack('<Q', base), f10=segments)))
    size = 64 + len(protobuf)
    body = struct.pack('<IHI', 31, 1, size).ljust(32, b'\0')
    body += struct.pack('<HHII', 0, 1, len(protobuf), len(protobuf)).ljust(32, b'\0') + protobuf
    return struct.pack('<HQ', 200, size) + body


class RouteV51Test(unittest.TestCase):
    def test_native_post_body_and_metadata_flag_are_not_route_failure(self):
        post = fixture(route_metadata=1)
        self.assertEqual(decode(post), decode(post[10:]))
        self.assertEqual(decode(post)[0]['path'], decode(fixture())[0]['path'])
        for metadata in (2, 255):
            with self.assertRaises(ValueError): decode(fixture(route_metadata=metadata))
        with self.assertRaises(ValueError): decode(fixture(header_status=1))
        with self.assertRaises(ValueError): decode(post[10:-1])

    def test_native_link_identity_name_inheritance_and_segment_geometry(self):
        route = decode(road_link_fixture())[0]
        links = route['roadLinks']
        self.assertEqual(route['breaks'], [5])
        self.assertEqual([(link['start'], link['end']) for link in links], [(0, 1), (1, 2), (2, 3), (3, 4), (5, 6)])
        self.assertEqual([link['id'] for link in links],
                         [str(9007199254740993 + delta) for delta in (0, 1, 0, 2, 0)])
        self.assertEqual([link['road'] for link in links], ['环城隧道', '环城隧道', '环城路', '', ''])
        self.assertEqual([link.get('roadProperty') for link in links], [7, 7, 1, 5, None])
        self.assertEqual([link.get('roadClass') for link in links], [4, 4, 2, 0, None])
        self.assertEqual([link.get('linkType') for link in links], [2, 2, 0, 0, None])

    def test_native_link_base_bounds_and_uint64_wrap(self):
        self.assertEqual(decode(road_link_fixture((1 << 64) - 1))[0]['roadLinks'][1]['id'], '0')
        with self.assertRaises(ValueError):
            decode(road_link_fixture(b'bad'))
        self.assertNotIn('id', decode(fixture(link_flags=4))[0]['roadLinks'][0])

    def test_native_link_type_word_inheritance_and_unknown_value(self):
        for value in (0, 1, 2, 3, 4, 100, 0xFFFFFFFF):
            with self.subTest(linkType=value):
                types = [link.get('linkType') for link in decode(road_link_fixture(link_type=value))[0]['roadLinks']]
                expected = -1 if value == 0xFFFFFFFF else value
                self.assertEqual(types, [expected, expected, 0, 0, None])
        for value in (1 << 32, b'invalid'):
            with self.assertRaises(ValueError): decode(road_link_fixture(link_type=value))

    def test_route_summary_units_and_missing_values(self):
        # Summary fields captured from the Hangzhou -> Shanghai response.
        route = fields(msg(f7=8460, f4=msg(f1=7100, f2=13551100, f5=b'CNY')))
        self.assertEqual(route_summary(route), {'duration': 8460, 'tolls': 71, 'tollCurrency': 'CNY'})
        self.assertEqual(route_summary({})['tolls'], None)
        self.assertEqual(route_summary(fields(msg(f4=msg(f1=0, f2=0))))['tolls'], 0)
        self.assertIsNone(route_summary(fields(msg(f7=0)))['duration'])
        self.assertIsNone(route_summary(fields(msg(f4=msg(f1=7100, f5=b'USD'))))['tolls'])

    def test_decodes_absolute_first_and_zigzag_deltas(self):
        route = decode(fixture())[0]
        self.assertEqual(route['path'], [[116.4, 39.9], [116.401, 39.9]])
        self.assertAlmostEqual(route['distance'], 85, delta=1)

    def test_negative_delta(self):
        self.assertEqual(decode(fixture(xs=(116.401, 116.4)))[0]['path'][-1][0], 116.4)

    def test_signalized_link_uses_bit_four_and_link_end(self):
        route = decode(fixture(link_flags=1028))[0]
        self.assertEqual(route['trafficLightCount'], 1)
        self.assertEqual(route['trafficLights'], [[116.401, 39.9]])
        self.assertEqual(decode(fixture(link_flags=8))[0]['trafficLightCount'], 0)

    def test_apk_link_status_maps_directly_to_congestion_geometry(self):
        route = decode(fixture(xs=(116.4, 116.4005, 116.401), ys=(39.9, 39.9, 39.9),
                               link_statuses=[2, 4]))[0]
        self.assertEqual([run['status'] for run in route['trafficRuns']], [2, 4])
        self.assertEqual(route['trafficRuns'][0]['path'], [[116.4, 39.9], [116.4005, 39.9]])
        self.assertAlmostEqual(route['trafficRuns'][0]['end'], route['trafficRuns'][1]['start'], delta=.1)
        self.assertEqual(decode(fixture(link_statuses=[1]))[0]['trafficRuns'], [])
        with self.assertRaises(ValueError):
            decode(fixture(link_statuses=[99]))
    def test_decodes_middle_fork_assistant_action(self):
        step = decode(fixture(assistant_action=6))[0]['steps'][0]
        self.assertEqual(step['actionCode'], 2)
        self.assertEqual(step['assistantActionCode'], 6)

    def test_merged_congestion_preserves_each_links_pass_time_in_seconds(self):
        route = decode(fixture(xs=(116.4, 116.4005, 116.401), ys=(39.9,) * 3,
                               link_statuses=[3, 3], link_times=[30, 300]))[0]
        run = route['trafficRuns'][0]
        self.assertEqual(len(route['trafficRuns']), 1)
        self.assertEqual(run['duration'], 330)
        self.assertEqual([time['duration'] for time in run['timings']], [30, 300])
        self.assertEqual(run['timings'][0]['start'], run['start'])
        self.assertEqual(run['timings'][0]['end'], run['timings'][1]['start'])
        self.assertEqual(run['timings'][1]['end'], run['end'])

    def test_missing_link_time_does_not_turn_into_a_partial_total(self):
        for invalid in (None, 0, 30 * 86400 + 1):
            run = decode(fixture(xs=(116.4, 116.4005, 116.401), ys=(39.9,) * 3,
                                 link_statuses=[3, 3], link_times=[invalid, 120]))[0]['trafficRuns'][0]
            self.assertIsNone(run['duration'])
            self.assertIsNone(run['timings'][0]['duration'])
            self.assertEqual(run['timings'][1]['duration'], 120)

    def test_ring_exit_ordinal_requires_complete_entry_and_native_exit_markers(self):
        for flags, expected in (([8], 1), ([8, 0, 8], 2), ([8, 0, 8, 0, 8, 0, 8], 4)):
            xs = tuple(116.4 + .001 * i / len(flags) for i in range(len(flags) + 1))
            route = decode(fixture(xs=xs, ys=(39.9,) * len(xs), action=12,
                                   ring_flags=flags, ring_entry=True))[0]
            self.assertEqual(route['steps'][1]['roundaboutExit'], expected)
            self.assertEqual(route['steps'][0]['actionCode'], 11)
        for action, entry, flags in ((12, False, [8]), (2, True, [8]), (12, True, [0])):
            self.assertNotIn('roundaboutExit', decode(fixture(action=action,
                             ring_entry=entry, ring_flags=flags))[0]['steps'][-1])

    def test_service_area_only_from_facility_label(self):
        self.assertEqual(decode(fixture(facility='长安服务区'))[0]['steps'][0]['serviceArea'], '长安服务区')
        self.assertEqual(decode(fixture(facility='某某停车区'))[0]['steps'][0]['serviceArea'], '某某停车区')
        self.assertNotIn('serviceArea', decode(fixture(facility='某某收费站'))[0]['steps'][0])
        self.assertIsNone(service_area_name(fields(msg(f5=b'\x0a\xff'))))

    def test_rejects_truncation(self):
        raw = fixture()
        for size in (0, 8, 31, 73, len(raw) - 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                decode(raw[:size])

    def test_rejects_mismatched_axes_and_wrong_destination(self):
        with self.assertRaises(ValueError):
            decode(fixture(ys=(39.9,)))
        with self.assertRaises(ValueError):
            decode(fixture(), destination=[120, 30])

    def test_rejects_invalid_protobuf_and_compression(self):
        for data in (b'\0', b'\x0a\x7f', b'\x08' + b'\xff' * 11):
            with self.assertRaises(ValueError):
                fields(data)
        raw = bytearray(fixture()); raw[42] = 99
        with self.assertRaises(ValueError):
            unpack(raw)

    def test_compressed_record_roundtrip(self):
        import zstandard
        data = unpack(fixture()); compressed = zstandard.ZstdCompressor().compress(data)
        size = 64 + len(compressed)
        raw = struct.pack('<HQ', 200, size) + struct.pack('<IHI', 31, 1, size).ljust(32, b'\0')
        raw += struct.pack('<HHII', 2, 1, len(compressed), len(data)).ljust(32, b'\0') + compressed
        self.assertEqual(decode(raw), decode(fixture()))
