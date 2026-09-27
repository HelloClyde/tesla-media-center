import unittest

from lane_render import inspect_response, version_catalog


def integer(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out) + bytes([value])


def field(key, value):
    if isinstance(value, int):
        return integer(key << 3) + integer(value)
    return integer(key << 3 | 2) + integer(len(value)) + value


def response(identity=123, inner=123, kind=23):
    data = field(1, inner) + field(2, b'opaque')
    block = field(1, data) + field(2, len(data))
    return field(1, identity) + field(2, kind) + field(5, block)


class LaneRenderTests(unittest.TestCase):
    def test_catalog(self):
        entries = b''.join(field(1, field(1, k) + field(2, 100)) for k in (22, 23))
        host = b'https://render-prod-lnds.amap.com'
        self.assertEqual(version_catalog(entries + field(5, host)),
                         (host.decode(), {22: 100, 23: 100}))
        for bad in (entries + field(5, b'https://example.org'),
                    field(5, host), entries + field(5, host) + field(5, host)):
            with self.assertRaises(ValueError):
                version_catalog(bad)

    def test_opaque_payload_retained(self):
        payload, report = inspect_response(response(), 123, 23)
        self.assertEqual(payload, field(1, 123) + field(2, b'opaque'))
        self.assertFalse(report['geometryDecoded'])
        self.assertEqual(report['fieldCounts'], {'1': 1, '2': 1})

    def test_identity_and_truncation(self):
        for raw in (response(identity=124), response(inner=124), response(kind=22),
                    response()[:-1]):
            with self.assertRaises(ValueError):
                inspect_response(raw, 123, 23)

    def test_empty_is_not_geometry(self):
        payload, report = inspect_response(field(1, 123) + field(2, 22), 123, 22)
        self.assertEqual(payload, b'')
        self.assertFalse(report['geometryDecoded'])


if __name__ == '__main__':
    unittest.main()
