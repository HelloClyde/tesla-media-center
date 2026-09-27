"""Single persistent data root; legacy files are copied once, never removed."""
import json
import os
from pathlib import Path
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('TMC_DATA_DIR', ROOT / 'data')).resolve()


def data_path(*parts):
    return DATA_ROOT.joinpath(*parts)


def initialize_storage():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    marker = data_path('.migration-v1')
    if marker.exists():
        return
    legacy_config = ROOT / 'config.json'
    target_config = data_path('config.json')
    if not target_config.exists() and legacy_config.is_file():
        temporary = target_config.with_suffix('.migrating')
        shutil.copy2(legacy_config, temporary)
        temporary.replace(target_config)
    config = json.loads(target_config.read_text(encoding='utf-8')) if target_config.exists() else {}

    def copy_missing(source, target):
        source, target = Path(source).resolve(), Path(target).resolve()
        if source == target or not source.is_dir():
            return
        if target.is_relative_to(source):
            raise ValueError('Persistent data destination must not be inside its legacy source')
        target.mkdir(parents=True, exist_ok=True)
        for entry in source.iterdir():
            if entry.is_symlink():
                continue
            dest = target / entry.name
            if entry.is_dir():
                copy_missing(entry, dest)
            elif not dest.exists():
                temporary = dest.with_name(dest.name + '.tmc-migrating')
                shutil.copy2(entry, temporary)
                temporary.replace(dest)

    def old_path(key, default):
        path = Path(config.get(key) or default)
        return path if path.is_absolute() else ROOT / path

    for source, destination in [
        (ROOT / '.qqmusic', data_path('qqmusic')),
        (old_path('gba_path', 'roms/gba'), data_path('gba')),
        (old_path('gba_save_path', 'roms/gba/saves'), data_path('gba/saves')),
        (old_path('gba_state_path', 'roms/gba/states'), data_path('gba/states')),
        (ROOT / 'roms/gam4980', data_path('gam4980')),
        (old_path('bilibili_cache_dir', '/tmp/tesla-media-center/bilibili-cache'), data_path('bilibili-cache')),
    ]:
        copy_missing(source, destination)
    # SQLite backup also includes committed WAL pages, unlike a raw file copy.
    old_cache = Path(os.environ.get('TMC_AMAP_CACHE_DIR', ROOT / '.local-data/amap-cache')) / 'map.sqlite3'
    if not old_cache.exists():
        old_cache = Path('/var/cache/tmc/amap/map.sqlite3')
    new_cache = data_path('amap-cache/map.sqlite3')
    for source, destination in [(old_cache, new_cache),
                                (old_path('tesla_db_path', 'db/tesla_history.sqlite3'),
                                 data_path('tesla/tesla_history.sqlite3'))]:
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix('.migrating')
            with sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True) as src, sqlite3.connect(temporary) as dst:
                src.backup(dst)
            temporary.replace(destination)
    marker.write_text('Legacy data copied; originals retained.\n', encoding='utf-8')
