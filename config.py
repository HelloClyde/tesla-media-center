import json
import os
import secrets
import tempfile
import threading
from storage import data_path, initialize_storage

initialize_storage()

_config_path = data_path('config.json')
_config_lock = threading.RLock()
if not _config_path.exists():
    password = os.environ.get('TMC_PASSWORD') or secrets.token_urlsafe(16)
    _config_path.write_text(json.dumps({'password': password}), encoding='utf-8')
    if not os.environ.get('TMC_PASSWORD'):
        print('TMC initial login password: ' + password, flush=True)

def read_config():
    with open(_config_path, 'r', encoding='utf-8') as f:
        content = f.read()
        return json.loads(content)

def write_config(config_dict):
    with _config_lock:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=_config_path.parent, delete=False) as wf:
                temporary = wf.name
                json.dump(config_dict, wf, indent=4)
                wf.flush()
                os.fsync(wf.fileno())
            os.replace(temporary, _config_path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

def get_all_config_safe():
    config = read_config()
    config['amap_traffic_configured'] = bool(config.get('amap_traffic_key') or os.environ.get('TMC_AMAP_TRAFFIC_KEY'))
    config.pop('amap_traffic_key', None)
    config.pop('password', None)
    config.pop('secret_key', None)
    config.pop('bilibili_sessdata', None)
    config.pop('bilibili_bili_jct', None)
    config.pop('bilibili_buvid3', None)
    config.pop('bilibili_dedeuserid', None)
    config.pop('bilibili_ac_time_value', None)
    config.pop('tesla_client_secret', None)
    config.pop('tesla_access_token', None)
    config.pop('tesla_refresh_token', None)
    return config

def put_config_by_key(key, value):
    with _config_lock:
        config = read_config()
        config[key] = value
        write_config(config_dict=config)

def get_config_by_key(key, default_value=None):
    config = read_config()
    if key in config:
        return config[key]
    else:
        return default_value
