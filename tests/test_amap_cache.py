import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from ffvideo.amap_cache import MapCache

class DiskCacheTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'cache.sqlite3'
        self.cache = MapCache(self.path)
        self.tile = {'x': 1, 'y': 2, 'surfaces': []}

    def test_restart_and_expiry(self):
        self.cache.write((3, 1, 2), self.tile, 0)
        other = MapCache(self.path)
        self.assertEqual(other.read([(3, 1, 2)])[0][(3, 1, 2)], self.tile)
        with patch('ffvideo.amap_cache.time.time', return_value=time.time() + 169 * 3600):
            self.assertEqual(other.read([(3, 1, 2)])[0], {})

    def test_settings_persist_and_clear_rejects_inflight(self):
        self.cache.status({'ttlHours': 24, 'maxMB': 16})
        self.assertEqual(MapCache(self.path).status()['ttlHours'], 24)
        generation = self.cache.status()['generation']
        self.cache.write((3, 1, 2), self.tile, generation)
        self.assertEqual(self.cache.status(clear=True)['count'], 0)
        self.cache.write((3, 1, 2), self.tile, generation)
        self.assertEqual(self.cache.status()['count'], 0)
        self.assertEqual(self.cache.status()['ttlHours'], 24)

    def test_capacity_lru_and_invalid_settings(self):
        for settings in [{'ttlHours': 0, 'maxMB': 512}, {'ttlHours': True, 'maxMB': 512}, {'ttlHours': 24, 'maxMB': 4097}]:
            with self.assertRaises(ValueError):
                self.cache.status(settings)
        self.cache.status({'ttlHours': 24, 'maxMB': 16})
        with self.cache.connect() as db:
            for i in range(3):
                db.execute('INSERT INTO tiles VALUES (?,?,?,?)', (str(i), time.time(), i, b'x' * 8 * 1024 * 1024))
        status = self.cache.status()
        self.assertEqual(status['count'], 2)
        self.assertLessEqual(status['usedBytes'], 16 * 1024 * 1024)
        with self.cache.connect() as db:
            self.assertIsNone(db.execute("SELECT key FROM tiles WHERE key='0'").fetchone())

    def test_partial_or_failed_tiles_not_persisted(self):
        for extra in [{'error': 'bad'}, {'missingLayers': ['surfaces']}]:
            self.cache.write((3, 1, 2), {**self.tile, **extra}, 0)
        self.assertEqual(self.cache.status()['count'], 0)
