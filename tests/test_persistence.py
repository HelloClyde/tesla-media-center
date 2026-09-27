import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import storage


class PersistenceTest(unittest.TestCase):
    def test_failed_config_replace_keeps_previous_config(self):
        import config
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'config.json'
            path.write_text('{"secret_key":"retained"}')
            with patch.object(config, '_config_path', path):
                with patch('config.os.replace', side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):
                        config.put_config_by_key('new_setting', True)
                self.assertEqual(config.read_config(), {'secret_key': 'retained'})
                config.put_config_by_key('new_setting', True)
                self.assertEqual(config.read_config(), {'secret_key': 'retained', 'new_setting': True})
                self.assertEqual(len(list(Path(temp).iterdir())), 1)

    def test_legacy_migration_preserves_config_saves_database_and_existing_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'old'
            root.mkdir()
            dest = Path(temp) / 'data'
            config = {'secret_key': 'unchanged', 'gba_path': 'custom-games'}
            (root / 'config.json').write_text(json.dumps(config))
            for folder, name in [('custom-games', 'game.gba'), ('roms/gba/saves', 'game.sav'),
                                 ('roms/gba/states', 'game.state'), ('roms/gam4980', 'game.gam'),
                                 ('.qqmusic', 'credential')]:
                path = root / folder
                path.mkdir(parents=True, exist_ok=True)
                (path / name).write_bytes(b'legacy')
            cache = root / 'old-cache'
            cache.mkdir()
            with sqlite3.connect(cache / 'map.sqlite3') as db:
                db.execute('CREATE TABLE example (value TEXT)')
                db.execute("INSERT INTO example VALUES ('retained')")
            with patch.object(storage, 'ROOT', root), patch.object(storage, 'DATA_ROOT', dest), patch.dict('os.environ', {'TMC_AMAP_CACHE_DIR': str(cache)}):
                storage.initialize_storage()
                self.assertEqual(json.loads((dest / 'config.json').read_text()), config)
                for name in ['gba/game.gba', 'gba/saves/game.sav', 'gba/states/game.state', 'gam4980/game.gam', 'qqmusic/credential']:
                    self.assertEqual((dest / name).read_bytes(), b'legacy')
                with sqlite3.connect(dest / 'amap-cache/map.sqlite3') as db:
                    self.assertEqual(db.execute('SELECT value FROM example').fetchone()[0], 'retained')
                (dest / 'gba/game.gba').write_bytes(b'new')
                storage.initialize_storage()
                self.assertEqual((dest / 'gba/game.gba').read_bytes(), b'new')
                self.assertEqual((root / 'custom-games/game.gba').read_bytes(), b'legacy')
