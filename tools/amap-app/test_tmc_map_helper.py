"""Version catalog reuse for short-lived APK map helpers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tmc_map_helper
import tmc_lane_helper


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def field(number, value):
    if isinstance(value, bytes):
        return varint(number * 8 + 2) + varint(len(value)) + value
    return varint(number * 8) + varint(value)


class VersionCatalogTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'bmd-version-v1.json'
        self.material = {'getAosChannel': 'test-channel', 'getAosKey': 'test-key'}
        self.raw = b''.join(field(1, field(1, kind) + field(2, kind + 100))
                            for kind in (0, 1, 2, 5, 6)) + field(5, b'https://render-prod-tile.amap.com')

    def test_cold_fetch_then_reuse_across_helpers(self):
        with patch.object(tmc_map_helper, 'download', return_value=self.raw) as download:
            first = tmc_map_helper.version_catalog(self.material, self.path)
            second = tmc_map_helper.version_catalog(self.material, self.path)
        self.assertEqual(first, second)
        self.assertEqual(first[1][5], 105)
        download.assert_called_once()
        self.assertNotIn('test-key', self.path.read_text(encoding='utf-8'))

    def test_expired_or_invalid_host_forces_refresh(self):
        self.path.write_text(json.dumps({'channel': 'test-channel', 'fetchedAt': 0,
                                         'host': 'https://render-prod-tile.amap.com',
                                         'versions': {str(k): k + 100 for k in (0, 1, 2, 5, 6)}}), encoding='utf-8')
        with patch.object(tmc_map_helper, 'download', return_value=self.raw) as download:
            tmc_map_helper.version_catalog(self.material, self.path)
        download.assert_called_once()
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        saved['host'] = 'https://example.org'
        self.path.write_text(json.dumps(saved), encoding='utf-8')
        with patch.object(tmc_map_helper, 'download', return_value=self.raw) as download:
            tmc_map_helper.version_catalog(self.material, self.path)
        download.assert_called_once()

    def test_bad_live_host_never_enters_cache(self):
        raw = b''.join(field(1, field(1, kind) + field(2, kind + 100))
                       for kind in (0, 1, 2, 5, 6)) + field(5, b'https://untrusted-host.example.com')
        with patch.object(tmc_map_helper, 'download', return_value=raw):
            with self.assertRaisesRegex(ValueError, 'unsupported tile host'):
                tmc_map_helper.version_catalog(self.material, self.path)
        self.assertFalse(self.path.exists())


class LaneVersionCatalogTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'lnds-version-v1.json'
        self.material = {'getAosChannel': 'test-channel', 'getAosKey': 'test-key'}
        self.raw = (field(1, field(1, 22) + field(2, 200))
                    + field(1, field(1, 23) + field(2, 201))
                    + field(5, b'https://render-prod-lnds.amap.com'))

    def test_one_version_request_serves_multiple_lane_tiles(self):
        with patch.object(tmc_map_helper, 'download', return_value=self.raw) as download:
            first = tmc_lane_helper.lnds_version_catalog(self.material, self.path)
            second = tmc_lane_helper.lnds_version_catalog(self.material, self.path)
        self.assertEqual(first, second)
        self.assertEqual(first[1], {22: 200, 23: 201})
        download.assert_called_once()

    def test_invalid_cached_version_refreshes(self):
        self.path.write_text(json.dumps({'channel': 'test-channel', 'fetchedAt': 0,
                                         'host': 'https://render-prod-lnds.amap.com',
                                         'versions': {'22': 200, '23': 201}}), encoding='utf-8')
        with patch.object(tmc_map_helper, 'download', return_value=self.raw) as download:
            tmc_lane_helper.lnds_version_catalog(self.material, self.path)
        download.assert_called_once()
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        saved['versions']['22'] = -1
        self.path.write_text(json.dumps(saved), encoding='utf-8')
        with patch.object(tmc_map_helper, 'download', return_value=self.raw) as download:
            tmc_lane_helper.lnds_version_catalog(self.material, self.path)
        download.assert_called_once()


if __name__ == '__main__':
    unittest.main()
