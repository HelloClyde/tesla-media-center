"""Versioned SQLite map cache with persistent policy and bounded compressed data."""
from contextlib import contextmanager
import json
import sqlite3
import threading
import time
import zlib
from pathlib import Path

VERSION = 'bmd-17.00.0.2005-v3-road-levels'

class MapCache:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA auto_vacuum=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY, hours INTEGER, mb INTEGER, generation INTEGER)')
        db.execute('INSERT OR IGNORE INTO policy VALUES (1, 168, 512, 0)')
        db.execute('CREATE TABLE IF NOT EXISTS tiles (key TEXT PRIMARY KEY, created REAL, accessed REAL, data BLOB)')
        db.commit()
        try:
            with db:
                yield db
        finally:
            db.close()

    def prune(self, db):
        hours, mb, _ = db.execute('SELECT hours, mb, generation FROM policy').fetchone()
        db.execute('DELETE FROM tiles WHERE created < ?', (time.time() - hours * 3600,))
        total = db.execute('SELECT COALESCE(SUM(length(data)),0) FROM tiles').fetchone()[0]
        limit = mb * 1024 * 1024
        if total <= limit:
            return
        for key, size in db.execute('SELECT key, length(data) FROM tiles ORDER BY accessed ASC').fetchall():
            if total <= limit:
                break
            db.execute('DELETE FROM tiles WHERE key=?', (key,))
            total -= size

    def status(self, settings=None, clear=False):
        with self.lock, self.connect() as db:
            if settings is not None:
                hours, mb = settings.get('ttlHours'), settings.get('maxMB')
                if type(hours) is not int or not 1 <= hours <= 2160 or type(mb) is not int or not 16 <= mb <= 4096:
                    raise ValueError('缓存时间须为 1–2160 小时，容量须为 16–4096 MB')
                db.execute('UPDATE policy SET hours=?, mb=?, generation=generation+1', (hours, mb))
            if clear:
                db.execute('DELETE FROM tiles')
                db.execute('UPDATE policy SET generation=generation+1')
            self.prune(db)
            hours, mb, generation = db.execute('SELECT hours, mb, generation FROM policy').fetchone()
            count, used = db.execute('SELECT COUNT(*),COALESCE(SUM(length(data)),0) FROM tiles').fetchone()
            return dict(ttlHours=hours, maxMB=mb, generation=generation, count=count, usedBytes=used)

    def read(self, keys):
        found = {}
        with self.lock, self.connect() as db:
            self.prune(db)
            generation = db.execute('SELECT generation FROM policy').fetchone()[0]
            for key in keys:
                identity = VERSION + '/' + '/'.join(map(str, key))
                row = db.execute('SELECT data FROM tiles WHERE key=?', (identity,)).fetchone()
                if row:
                    try:
                        found[key] = json.loads(zlib.decompress(row[0]))
                        db.execute('UPDATE tiles SET accessed=? WHERE key=?', (time.time(), identity))
                    except (ValueError, zlib.error):
                        db.execute('DELETE FROM tiles WHERE key=?', (identity,))
            return found, generation

    def write(self, key, tile, generation):
        if tile.get('error') or tile.get('missingLayers'):
            return
        data = zlib.compress(json.dumps(tile, ensure_ascii=False).encode(), 3)
        with self.lock, self.connect() as db:
            current, mb = db.execute('SELECT generation, mb FROM policy').fetchone()
            if generation != current or len(data) > mb * 1024 * 1024:
                return
            identity = VERSION + '/' + '/'.join(map(str, key))
            db.execute('INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)', (identity, time.time(), time.time(), data))
            self.prune(db)
