import os
import sqlite3
import time
import base64
import json
import math
import threading
from typing import Any

import requests
from flask import request
from loguru import logger

from config import get_config_by_key, put_config_by_key
from ffvideo.utils import json_fail, json_ok, login_check

DEFAULT_TESLA_API_BASE = 'https://owner-api.vn.cloud.tesla.cn'
DEFAULT_TESLA_AUTH_BASE = 'https://auth.tesla.com'
DEFAULT_TESLA_TOKEN_PATH = '/oauth2/v3'
DEFAULT_TESLA_CLIENT_ID = 'ownerapi'
DEFAULT_TESLA_DB_PATH = './db/tesla_history.sqlite3'
GLOBAL_TESLA_API_BASE = 'https://owner-api.teslamotors.com'
CHINA_TESLA_API_BASE = 'https://owner-api.vn.cloud.tesla.cn'
DEFAULT_TESLA_USER_AGENT = 'TeslaMediaCenter/1.0'
DEFAULT_TESLA_RETENTION_DAYS = 30
DEFAULT_TESLA_MAX_STORAGE_MB = 256
DEFAULT_TESLA_POLL_INTERVAL_SEC = 120
TESLA_TOKEN_REFRESH_AHEAD_SEC = 30 * 60
TESLA_IDLE_POLL_INTERVAL_SEC = 60
TESLA_DRIVING_POLL_INTERVAL_SEC = 10
tesla_sync_thread = None
tesla_sync_stop_event = threading.Event()


def get_tesla_db_path():
    return get_config_by_key('tesla_db_path', DEFAULT_TESLA_DB_PATH)


def ensure_tesla_storage():
    db_path = get_tesla_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS tesla_vehicle_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vin TEXT NOT NULL,
                display_name TEXT,
                vehicle_state TEXT,
                latitude REAL,
                longitude REAL,
                heading REAL,
                speed REAL,
                shift_state TEXT,
                battery_level REAL,
                usable_battery_level REAL,
                charging_state TEXT,
                charge_limit_soc REAL,
                odometer REAL,
                locked INTEGER,
                inside_temp REAL,
                outside_temp REAL,
                is_climate_on INTEGER,
                sentry_mode INTEGER,
                timestamp_ms INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_tesla_vehicle_samples_vin_timestamp ON tesla_vehicle_samples(vin, timestamp_ms DESC)'
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS tesla_vehicles (
                vin TEXT PRIMARY KEY,
                vehicle_id TEXT,
                display_name TEXT,
                state TEXT,
                in_service INTEGER,
                calendar_enabled INTEGER,
                api_version TEXT,
                updated_at INTEGER NOT NULL
            )
            '''
        )
        conn.commit()


def tesla_settings_snapshot():
    return {
        'mode': get_config_by_key('tesla_mode', 'owner_api'),
        'clientId': get_config_by_key('tesla_client_id', ''),
        'apiBaseUrl': get_tesla_api_base_url(),
        'authBaseUrl': get_tesla_auth_base_url(),
        'tokenPath': get_tesla_token_path(),
        'accessToken': get_config_by_key('tesla_access_token', ''),
        'refreshToken': get_config_by_key('tesla_refresh_token', ''),
        'hasAccessToken': bool(get_config_by_key('tesla_access_token', '')),
        'hasRefreshToken': bool(get_config_by_key('tesla_refresh_token', '')),
        'dbPath': get_tesla_db_path(),
        'pollIntervalSec': get_tesla_poll_interval_sec(),
        'retentionDays': get_tesla_retention_days(),
        'maxStorageMb': get_tesla_max_storage_mb(),
    }


def get_tesla_access_token():
    return get_config_by_key('tesla_access_token', '')


def get_tesla_refresh_token():
    return get_config_by_key('tesla_refresh_token', '')


def get_tesla_retention_days():
    return int(get_config_by_key('tesla_retention_days', DEFAULT_TESLA_RETENTION_DAYS) or DEFAULT_TESLA_RETENTION_DAYS)


def get_tesla_max_storage_mb():
    return int(get_config_by_key('tesla_max_storage_mb', DEFAULT_TESLA_MAX_STORAGE_MB) or DEFAULT_TESLA_MAX_STORAGE_MB)


def get_tesla_poll_interval_sec():
    return int(get_config_by_key('tesla_poll_interval_sec', DEFAULT_TESLA_POLL_INTERVAL_SEC) or DEFAULT_TESLA_POLL_INTERVAL_SEC)


def get_tesla_api_base_url():
    configured = (get_config_by_key('tesla_api_base_url', '') or '').rstrip('/')
    if configured:
        return configured
    return CHINA_TESLA_API_BASE if get_tesla_region() == 'chinese' else GLOBAL_TESLA_API_BASE


def get_tesla_auth_base_url():
    auth_base = get_config_by_key('tesla_auth_base_url', DEFAULT_TESLA_AUTH_BASE) or DEFAULT_TESLA_AUTH_BASE
    auth_base = auth_base.rstrip('/')
    if auth_base == 'https://auth.tesla.cn':
        return DEFAULT_TESLA_AUTH_BASE
    return auth_base


def get_tesla_token_path():
    token_path = get_config_by_key('tesla_token_path', DEFAULT_TESLA_TOKEN_PATH) or DEFAULT_TESLA_TOKEN_PATH
    token_path = token_path.strip()
    if not token_path.startswith('/'):
        token_path = f'/{token_path}'
    if token_path.endswith('/token'):
        token_path = token_path[:-6] or DEFAULT_TESLA_TOKEN_PATH
    return token_path


def get_tesla_token_url():
    return f'{get_tesla_auth_base_url()}{get_tesla_token_path()}/token'


def decode_jwt_payload(token: str):
    parts = (token or '').split('.')
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = '=' * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload + padding).decode('utf-8'))
    except Exception:
        return None


def derive_issuer_url_from_access_token(access_token: str):
    token = access_token or ''
    if token.startswith('qts-') or token.startswith('eu-') or token.startswith('cn-'):
        return f'{get_tesla_auth_base_url()}{get_tesla_token_path()}'
    payload = decode_jwt_payload(token) or {}
    issuer = payload.get('iss')
    if isinstance(issuer, str) and issuer.startswith('https://'):
        return issuer.rstrip('/')
    return f'{get_tesla_auth_base_url()}{get_tesla_token_path()}'


def get_tesla_region(access_token: str | None = None):
    issuer_url = derive_issuer_url_from_access_token(access_token or get_tesla_access_token())
    try:
        host = issuer_url.split('://', 1)[1].split('/', 1)[0]
        tld = host.split('.')[-1]
        if tld == 'cn':
            return 'chinese'
    except Exception:
        pass
    return 'global'


def parse_tesla_error_message(resp: requests.Response):
    try:
        payload = resp.json()
    except Exception:
        payload = {}
    error = payload.get('error') or 'tesla_error'
    description = payload.get('error_description') or payload.get('message') or resp.text
    return error, description


def tesla_tokens_configured():
    return bool(get_tesla_access_token() or get_tesla_refresh_token())


def save_tesla_token_payload(payload: dict[str, Any]):
    if payload.get('access_token'):
        put_config_by_key('tesla_access_token', payload['access_token'])
    if payload.get('refresh_token'):
        put_config_by_key('tesla_refresh_token', payload['refresh_token'])
    expires_in = int(payload.get('expires_in', 0) or 0)
    if expires_in > 0:
        put_config_by_key('tesla_token_expires_at', int(time.time()) + expires_in - 60)


def clear_tesla_tokens():
    put_config_by_key('tesla_access_token', '')
    put_config_by_key('tesla_refresh_token', '')
    put_config_by_key('tesla_token_expires_at', 0)
    put_config_by_key('tesla_last_sync_at', 0)


def refresh_tesla_access_token_with_refresh_token(refresh_token: str, client_id: str | None = None, access_token: str | None = None):
    token = (refresh_token or '').strip()
    if not token:
        return None, ('refresh_token_missing', '缺少 Refresh Token')

    payload = {
        'grant_type': 'refresh_token',
        'scope': 'openid email offline_access',
        'client_id': client_id or get_config_by_key('tesla_client_id', DEFAULT_TESLA_CLIENT_ID) or DEFAULT_TESLA_CLIENT_ID,
        'refresh_token': token,
    }
    issuer_url = derive_issuer_url_from_access_token(access_token or get_tesla_access_token())
    token_url = f'{issuer_url}/token'
    logger.info(f'refresh tesla access token, token_url={token_url}, api_base_url={get_tesla_api_base_url()}')
    resp = requests.post(token_url, json=payload, timeout=20)
    if resp.status_code >= 400:
        error, description = parse_tesla_error_message(resp)
        logger.warning(f'tesla token refresh failed, status={resp.status_code}, body={resp.text}')
        if error == 'login_required':
            return None, ('invalid_refresh_token', f'Refresh Token 无效: {description}')
        return None, ('tesla_auth_error', f'Tesla 授权失败: {description}')

    token_payload = resp.json()
    return token_payload, None


def refresh_tesla_access_token(force=False):
    access_token = get_tesla_access_token()
    expires_at = int(get_config_by_key('tesla_token_expires_at', 0) or 0)
    if not force and access_token and expires_at > int(time.time()) + TESLA_TOKEN_REFRESH_AHEAD_SEC:
        return access_token

    refresh_token = get_tesla_refresh_token()
    client_id = get_config_by_key('tesla_client_id', DEFAULT_TESLA_CLIENT_ID) or DEFAULT_TESLA_CLIENT_ID
    if not refresh_token or not client_id:
        return access_token

    token_payload, error = refresh_tesla_access_token_with_refresh_token(refresh_token, client_id, access_token)
    if error:
        return access_token

    save_tesla_token_payload(token_payload)
    return token_payload.get('access_token', access_token)


def tesla_api_request(method: str, path: str, *, params=None, json_data=None, allow_retry=True):
    access_token = refresh_tesla_access_token()
    if not access_token:
        return None, ('not_authorized', 'Tesla 尚未授权')

    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': DEFAULT_TESLA_USER_AGENT,
        'Accept': 'application/json',
    }
    url = f'{get_tesla_api_base_url()}{path}'
    resp = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=25)
    if resp.status_code == 401 and allow_retry and get_tesla_refresh_token():
        access_token = refresh_tesla_access_token(force=True)
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
            resp = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=25)
    if resp.status_code >= 400:
        logger.warning(f'tesla api error, path={path}, status={resp.status_code}, body={resp.text}')
        if resp.status_code == 401:
            return None, ('not_authorized', 'Tesla 授权已失效，请重新连接')
        return None, ('tesla_api_error', f'Tesla 接口请求失败: {resp.status_code}')
    return resp.json(), None


def normalize_vehicle_record(vehicle: dict[str, Any]):
    return {
        'id': vehicle.get('id') or vehicle.get('vehicle_id'),
        'vehicleId': vehicle.get('vehicle_id') or vehicle.get('id'),
        'vin': vehicle.get('vin'),
        'displayName': vehicle.get('display_name') or vehicle.get('displayName') or vehicle.get('vin'),
        'state': vehicle.get('state'),
        'inService': vehicle.get('in_service'),
        'calendarEnabled': vehicle.get('calendar_enabled'),
        'apiVersion': vehicle.get('api_version'),
    }


def upsert_vehicle_cache(vehicle: dict[str, Any]):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            '''
            INSERT INTO tesla_vehicles(vin, vehicle_id, display_name, state, in_service, calendar_enabled, api_version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vin) DO UPDATE SET
              vehicle_id=excluded.vehicle_id,
              display_name=excluded.display_name,
              state=excluded.state,
              in_service=excluded.in_service,
              calendar_enabled=excluded.calendar_enabled,
              api_version=excluded.api_version,
              updated_at=excluded.updated_at
            ''',
            (
                vehicle.get('vin'),
                str(vehicle.get('vehicleId') or ''),
                vehicle.get('displayName'),
                vehicle.get('state'),
                1 if vehicle.get('inService') else 0 if vehicle.get('inService') is not None else None,
                1 if vehicle.get('calendarEnabled') else 0 if vehicle.get('calendarEnabled') is not None else None,
                vehicle.get('apiVersion'),
                int(time.time()),
            ),
        )
        conn.commit()


def cached_vehicles():
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT vin, vehicle_id, display_name, state, in_service, calendar_enabled, api_version, updated_at
            FROM tesla_vehicles
            ORDER BY updated_at DESC
            '''
        ).fetchall()
    return [{
        'vin': row['vin'],
        'id': row['vehicle_id'],
        'vehicleId': row['vehicle_id'],
        'displayName': row['display_name'],
        'state': row['state'],
        'inService': None if row['in_service'] is None else bool(row['in_service']),
        'calendarEnabled': None if row['calendar_enabled'] is None else bool(row['calendar_enabled']),
        'apiVersion': row['api_version'],
    } for row in rows]


def extract_sample_from_vehicle_data(vin: str, display_name: str, vehicle_state: str, payload: dict[str, Any]):
    drive_state = payload.get('drive_state') or {}
    charge_state = payload.get('charge_state') or {}
    climate_state = payload.get('climate_state') or {}
    vehicle_state_data = payload.get('vehicle_state') or {}
    gui_settings = payload.get('gui_settings') or {}
    vehicle_config = payload.get('vehicle_config') or {}
    return {
        'vin': vin,
        'display_name': display_name,
        'vehicle_state': vehicle_state,
        'latitude': drive_state.get('latitude'),
        'longitude': drive_state.get('longitude'),
        'heading': drive_state.get('heading'),
        'speed': drive_state.get('speed'),
        'shift_state': drive_state.get('shift_state'),
        'battery_level': charge_state.get('battery_level'),
        'usable_battery_level': charge_state.get('usable_battery_level'),
        'charging_state': charge_state.get('charging_state'),
        'charge_limit_soc': charge_state.get('charge_limit_soc'),
        'odometer': vehicle_state_data.get('odometer') or gui_settings.get('gui_distance_units'),
        'locked': vehicle_state_data.get('locked'),
        'inside_temp': climate_state.get('inside_temp'),
        'outside_temp': climate_state.get('outside_temp'),
        'is_climate_on': climate_state.get('is_climate_on'),
        'sentry_mode': vehicle_state_data.get('sentry_mode'),
        'timestamp_ms': int(time.time() * 1000),
        'vehicle_config': vehicle_config,
    }


def insert_vehicle_sample(sample: dict[str, Any]):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            '''
            INSERT INTO tesla_vehicle_samples (
                vin, display_name, vehicle_state, latitude, longitude, heading, speed, shift_state,
                battery_level, usable_battery_level, charging_state, charge_limit_soc, odometer,
                locked, inside_temp, outside_temp, is_climate_on, sentry_mode, timestamp_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                sample.get('vin'),
                sample.get('display_name'),
                sample.get('vehicle_state'),
                sample.get('latitude'),
                sample.get('longitude'),
                sample.get('heading'),
                sample.get('speed'),
                sample.get('shift_state'),
                sample.get('battery_level'),
                sample.get('usable_battery_level'),
                sample.get('charging_state'),
                sample.get('charge_limit_soc'),
                sample.get('odometer'),
                1 if sample.get('locked') else 0 if sample.get('locked') is not None else None,
                sample.get('inside_temp'),
                sample.get('outside_temp'),
                1 if sample.get('is_climate_on') else 0 if sample.get('is_climate_on') is not None else None,
                1 if sample.get('sentry_mode') else 0 if sample.get('sentry_mode') is not None else None,
                sample.get('timestamp_ms'),
                int(time.time()),
            ),
        )
        conn.commit()


def prune_tesla_storage():
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    retention_cutoff_ms = int(time.time() * 1000) - get_tesla_retention_days() * 24 * 3600 * 1000
    with sqlite3.connect(db_path) as conn:
        conn.execute('DELETE FROM tesla_vehicle_samples WHERE timestamp_ms < ?', (retention_cutoff_ms,))
        conn.commit()
        try:
            conn.execute('VACUUM')
        except Exception:
            logger.warning('tesla sqlite vacuum failed after retention prune')

    max_bytes = get_tesla_max_storage_mb() * 1024 * 1024
    if os.path.exists(db_path) and os.path.getsize(db_path) > max_bytes:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                '''
                DELETE FROM tesla_vehicle_samples
                WHERE id IN (
                  SELECT id FROM tesla_vehicle_samples
                  ORDER BY timestamp_ms ASC
                  LIMIT 1000
                )
                '''
            )
            conn.commit()
            try:
                conn.execute('VACUUM')
            except Exception:
                logger.warning('tesla sqlite vacuum failed after size prune')


def clear_tesla_storage():
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute('DELETE FROM tesla_vehicle_samples')
        conn.execute('DELETE FROM tesla_vehicles')
        conn.commit()
        conn.execute('VACUUM')


def tesla_storage_stats():
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        sample_count = conn.execute('SELECT COUNT(*) AS c FROM tesla_vehicle_samples').fetchone()['c']
        vehicle_count = conn.execute('SELECT COUNT(*) AS c FROM tesla_vehicles').fetchone()['c']
        range_row = conn.execute(
            'SELECT MIN(timestamp_ms) AS min_ts, MAX(timestamp_ms) AS max_ts FROM tesla_vehicle_samples'
        ).fetchone()
    return {
        'dbPath': db_path,
        'dbSizeMb': round((os.path.getsize(db_path) if os.path.exists(db_path) else 0) / 1024 / 1024, 2),
        'sampleCount': sample_count,
        'vehicleCount': vehicle_count,
        'oldestTimestampMs': range_row['min_ts'],
        'latestTimestampMs': range_row['max_ts'],
        'retentionDays': get_tesla_retention_days(),
        'maxStorageMb': get_tesla_max_storage_mb(),
        'pollIntervalSec': get_tesla_poll_interval_sec(),
        'backgroundSyncRunning': tesla_sync_thread is not None and tesla_sync_thread.is_alive(),
    }


def latest_vehicle_sample(vin: str):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            '''
            SELECT * FROM tesla_vehicle_samples
            WHERE vin = ?
            ORDER BY timestamp_ms DESC
            LIMIT 1
            ''',
            (vin,),
        ).fetchone()
    return dict(row) if row else None


def recent_vehicle_track(vin: str, limit: int = 500):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT vin, display_name, latitude, longitude, heading, speed, shift_state, battery_level, vehicle_state, timestamp_ms
            FROM tesla_vehicle_samples
            WHERE vin = ? AND latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY timestamp_ms DESC
            LIMIT ?
            ''',
            (vin, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def recent_vehicle_samples(vin: str, limit: int = 2000):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT vin, display_name, latitude, longitude, heading, speed, shift_state, battery_level,
                   usable_battery_level, charging_state, charge_limit_soc, odometer, vehicle_state, timestamp_ms
            FROM tesla_vehicle_samples
            WHERE vin = ?
            ORDER BY timestamp_ms DESC
            LIMIT ?
            ''',
            (vin, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def tesla_point_distance_km(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]:
        return 0.0
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_trip_sample(sample: dict[str, Any]):
    shift_state = (sample.get('shift_state') or '').upper()
    speed = sample.get('speed')
    return shift_state in ['D', 'R', 'N'] or (isinstance(speed, (int, float)) and speed > 0)


def build_trip_sessions(vin: str, limit: int = 2000):
    samples = recent_vehicle_samples(vin, limit)
    sessions = []
    current = None
    last_active_sample = None
    idle_gap_ms = 5 * 60 * 1000
    hard_gap_ms = 15 * 60 * 1000

    def finalize_session():
        nonlocal current
        if not current or len(current['samples']) < 2:
            current = None
            return
        trip_samples = current['samples']
        distance_km = 0.0
        max_speed = 0.0
        for prev, cur in zip(trip_samples, trip_samples[1:]):
            distance_km += tesla_point_distance_km(prev.get('latitude'), prev.get('longitude'), cur.get('latitude'), cur.get('longitude'))
            speed = cur.get('speed')
            if isinstance(speed, (int, float)):
                max_speed = max(max_speed, float(speed))

        start = trip_samples[0]
        end = trip_samples[-1]
        sessions.append({
            'vin': vin,
            'displayName': end.get('display_name') or start.get('display_name'),
            'startTimeMs': start.get('timestamp_ms'),
            'endTimeMs': end.get('timestamp_ms'),
            'durationSec': max(0, int((end.get('timestamp_ms') - start.get('timestamp_ms')) / 1000)),
            'distanceKm': round(distance_km, 2),
            'maxSpeed': round(max_speed, 1),
            'startBatteryLevel': start.get('battery_level'),
            'endBatteryLevel': end.get('battery_level'),
            'startPosition': {'latitude': start.get('latitude'), 'longitude': start.get('longitude')},
            'endPosition': {'latitude': end.get('latitude'), 'longitude': end.get('longitude')},
            'pointCount': len(trip_samples),
            'samples': trip_samples,
        })
        current = None

    for sample in samples:
        active = is_trip_sample(sample)
        ts = sample.get('timestamp_ms') or 0
        if active:
            if current is None:
                current = {'samples': [sample]}
            else:
                previous_ts = current['samples'][-1].get('timestamp_ms') or 0
                if ts - previous_ts > hard_gap_ms:
                    finalize_session()
                    current = {'samples': [sample]}
                else:
                    current['samples'].append(sample)
            last_active_sample = sample
            continue

        if current is not None and last_active_sample is not None:
            if ts - (last_active_sample.get('timestamp_ms') or 0) <= idle_gap_ms:
                current['samples'].append(sample)
            else:
                finalize_session()
                last_active_sample = None

    finalize_session()
    sessions.reverse()
    return sessions


def has_active_vehicle_motion():
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT vin, speed, shift_state, vehicle_state, timestamp_ms
            FROM tesla_vehicle_samples
            WHERE timestamp_ms >= ?
            GROUP BY vin
            ORDER BY timestamp_ms DESC
            ''',
            (int(time.time() * 1000) - 2 * 60 * 1000,),
        ).fetchall()

    for row in rows:
        shift_state = (row['shift_state'] or '').upper()
        speed = row['speed']
        vehicle_state = (row['vehicle_state'] or '').lower()
        if shift_state in ['D', 'R', 'N']:
            return True
        if isinstance(speed, (int, float)) and speed > 0:
            return True
        if vehicle_state == 'driving':
            return True
    return False


def get_recommended_poll_interval_sec():
    return TESLA_DRIVING_POLL_INTERVAL_SEC if has_active_vehicle_motion() else TESLA_IDLE_POLL_INTERVAL_SEC


def tesla_user_profile():
    data, error = tesla_api_request('GET', '/api/1/users/me')
    if error:
        return None
    resp = data.get('response') or data
    return {
        'email': resp.get('email'),
        'fullName': resp.get('full_name') or resp.get('name'),
        'profileImageUrl': resp.get('profile_image_url'),
    }


def sync_vehicle(vin: str, display_name: str, state: str):
    vehicles_data, vehicles_error = tesla_api_request('GET', '/api/1/products')
    if vehicles_error:
        return {'vin': vin, 'displayName': display_name, 'state': state, 'error': vehicles_error[1]}

    products = vehicles_data.get('response') or vehicles_data or []
    target = next((item for item in products if item.get('vin') == vin or str(item.get('vehicle_id') or '') == str(vin)), None)
    vehicle_id = target.get('id') if target else None
    if not vehicle_id:
        return {'vin': vin, 'displayName': display_name, 'state': state, 'error': 'Tesla 未返回该车辆的在线数据入口'}

    data, error = tesla_api_request('GET', f'/api/1/vehicles/{vehicle_id}/vehicle_data')
    if error:
        if state in ['asleep', 'offline']:
            sample = {
                'vin': vin,
                'display_name': display_name,
                'vehicle_state': state,
                'timestamp_ms': int(time.time() * 1000),
            }
            insert_vehicle_sample(sample)
            return {'vin': vin, 'displayName': display_name, 'state': state, 'sample': sample, 'warning': error[1]}
        return {'vin': vin, 'displayName': display_name, 'state': state, 'error': error[1]}
    payload = data.get('response') or data
    sample = extract_sample_from_vehicle_data(vin, display_name, state, payload)
    insert_vehicle_sample(sample)
    return {
        'vin': vin,
        'displayName': display_name,
        'state': state,
        'sample': sample,
    }


def sync_all_vehicles(target_vin: str | None = None):
    data, error = tesla_api_request('GET', '/api/1/products')
    if error:
        return None, error
    products = data.get('response') or []
    logger.info(f'tesla products fetched, total={len(products)}, vehicle_items={len([item for item in products if item.get("vehicle_id")])}')
    vehicles = [normalize_vehicle_record(item) for item in products if item.get('vehicle_id')]
    for vehicle in vehicles:
        upsert_vehicle_cache(vehicle)
    if target_vin:
        vehicles = [item for item in vehicles if item.get('vin') == target_vin]
    synced = [sync_vehicle(item['vin'], item['displayName'], item.get('state')) for item in vehicles if item.get('vin')]
    put_config_by_key('tesla_last_sync_at', int(time.time()))
    prune_tesla_storage()
    return synced, None


def tesla_background_sync_loop():
    logger.info('tesla background sync thread started')
    while not tesla_sync_stop_event.is_set():
        try:
            refresh_tesla_access_token()
            if tesla_tokens_configured():
                synced, error = sync_all_vehicles()
                if error:
                    logger.warning(f'tesla background sync failed: {error}')
                else:
                    logger.info(f'tesla background sync finished, items={len(synced or [])}')
            prune_tesla_storage()
        except Exception as e:
            logger.exception(f'tesla background sync exception: {e}')
        tesla_sync_stop_event.wait(get_recommended_poll_interval_sec())


def start_tesla_background_sync():
    global tesla_sync_thread
    ensure_tesla_storage()
    if tesla_sync_thread is not None and tesla_sync_thread.is_alive():
        return
    tesla_sync_stop_event.clear()
    tesla_sync_thread = threading.Thread(target=tesla_background_sync_loop, daemon=True, name='tesla-background-sync')
    tesla_sync_thread.start()


def add_tesla_route(app):
    ensure_tesla_storage()

    @app.route('/api/tesla/settings', methods=['GET'])
    @login_check
    def tesla_settings():
        return json_ok(tesla_settings_snapshot())

    @app.route('/api/tesla/settings', methods=['POST'])
    @login_check
    def update_tesla_settings():
        data = request.json or {}
        mode = str(data.get('mode') or get_config_by_key('tesla_mode', 'owner_api') or 'owner_api').strip()
        client_id = str(data.get('clientId') or get_config_by_key('tesla_client_id', DEFAULT_TESLA_CLIENT_ID) or DEFAULT_TESLA_CLIENT_ID).strip()
        api_base_url = str(data.get('apiBaseUrl') or get_tesla_api_base_url() or DEFAULT_TESLA_API_BASE).strip()
        auth_base_url = str(data.get('authBaseUrl') or get_tesla_auth_base_url() or DEFAULT_TESLA_AUTH_BASE).strip()
        token_path = str(data.get('tokenPath') or get_tesla_token_path() or DEFAULT_TESLA_TOKEN_PATH).strip()
        access_token = str(data.get('accessToken') or '').strip()
        refresh_token = str(data.get('refreshToken') or '').strip()

        put_config_by_key('tesla_mode', mode)
        put_config_by_key('tesla_client_id', client_id or DEFAULT_TESLA_CLIENT_ID)
        normalized_api_base_url = (api_base_url or DEFAULT_TESLA_API_BASE).rstrip('/')
        if normalized_api_base_url == 'https://owner-api.teslamotors.com':
            normalized_api_base_url = DEFAULT_TESLA_API_BASE
        put_config_by_key('tesla_api_base_url', normalized_api_base_url)
        normalized_auth_base_url = (auth_base_url or DEFAULT_TESLA_AUTH_BASE).rstrip('/')
        if normalized_auth_base_url == 'https://auth.tesla.cn':
            normalized_auth_base_url = DEFAULT_TESLA_AUTH_BASE
        put_config_by_key('tesla_auth_base_url', normalized_auth_base_url)
        normalized_token_path = token_path or DEFAULT_TESLA_TOKEN_PATH
        if not normalized_token_path.startswith('/'):
            normalized_token_path = f'/{normalized_token_path}'
        if normalized_token_path.endswith('/token'):
            normalized_token_path = normalized_token_path[:-6] or DEFAULT_TESLA_TOKEN_PATH
        put_config_by_key('tesla_token_path', normalized_token_path)
        put_config_by_key('tesla_poll_interval_sec', max(30, int(data.get('pollIntervalSec') or get_tesla_poll_interval_sec())))
        put_config_by_key('tesla_retention_days', max(1, int(data.get('retentionDays') or get_tesla_retention_days())))
        put_config_by_key('tesla_max_storage_mb', max(16, int(data.get('maxStorageMb') or get_tesla_max_storage_mb())))

        if refresh_token:
            token_payload, error = refresh_tesla_access_token_with_refresh_token(refresh_token, client_id, access_token)
            if error:
                return json_fail(error[0], message=error[1]), 400
            save_tesla_token_payload(token_payload)
        elif access_token:
            put_config_by_key('tesla_access_token', access_token)
            put_config_by_key('tesla_refresh_token', '')
            put_config_by_key('tesla_token_expires_at', 0)
        else:
            clear_tesla_tokens()

        return json_ok(tesla_settings_snapshot())

    @app.route('/api/tesla/storage', methods=['GET'])
    @login_check
    def tesla_storage():
        return json_ok(tesla_storage_stats())

    @app.route('/api/tesla/storage/clear', methods=['POST'])
    @login_check
    def tesla_storage_clear():
        clear_tesla_storage()
        return json_ok(tesla_storage_stats())

    @app.route('/api/tesla/auth/status', methods=['GET'])
    @login_check
    def tesla_auth_status():
        profile = tesla_user_profile() if tesla_tokens_configured() else None
        return json_ok({
            'configured': bool(get_tesla_access_token() or get_tesla_refresh_token()),
            'authorized': bool(profile),
            'profile': profile,
            'lastSyncAt': int(get_config_by_key('tesla_last_sync_at', 0) or 0),
        })

    @app.route('/api/tesla/auth/logout', methods=['POST'])
    @login_check
    def tesla_auth_logout():
        clear_tesla_tokens()
        return json_ok({'authorized': False})

    @app.route('/api/tesla/vehicles', methods=['GET'])
    @login_check
    def tesla_vehicles():
        vehicles = cached_vehicles()
        if len(vehicles) == 0 and tesla_tokens_configured():
            data, error = tesla_api_request('GET', '/api/1/products')
            if error:
                return json_fail(error[0], message=error[1]), 400 if error[0] == 'not_authorized' else 502
            products = data.get('response') or []
            logger.info(f'tesla vehicles request, total_products={len(products)}, vehicle_items={len([item for item in products if item.get("vehicle_id")])}')
            vehicles = [normalize_vehicle_record(item) for item in products if item.get('vehicle_id')]
            for vehicle in vehicles:
                upsert_vehicle_cache(vehicle)
        for vehicle in vehicles:
            latest = latest_vehicle_sample(vehicle['vin']) if vehicle.get('vin') else None
            if latest:
                vehicle['latestSample'] = latest
        return json_ok(vehicles)

    @app.route('/api/tesla/sync', methods=['POST'])
    @login_check
    def tesla_sync():
        data = request.json or {}
        vin = data.get('vin')
        synced, error = sync_all_vehicles(vin)
        if error:
            return json_fail(error[0], message=error[1]), 400 if error[0] == 'not_authorized' else 502
        return json_ok({'items': synced, 'lastSyncAt': int(get_config_by_key('tesla_last_sync_at', 0) or 0)})

    @app.route('/api/tesla/history/track', methods=['GET'])
    @login_check
    def tesla_track():
        vin = request.args.get('vin', '')
        limit = min(2000, max(10, int(request.args.get('limit', '500'))))
        if not vin:
            return json_fail('vin_required', message='缺少 VIN'), 400
        return json_ok({
            'vin': vin,
            'points': recent_vehicle_track(vin, limit),
            'latest': latest_vehicle_sample(vin),
        })

    @app.route('/api/tesla/history/trips', methods=['GET'])
    @login_check
    def tesla_trips():
        vin = request.args.get('vin', '')
        limit = min(5000, max(100, int(request.args.get('limit', '2000'))))
        if not vin:
            return json_fail('vin_required', message='缺少 VIN'), 400
        trips = build_trip_sessions(vin, limit)
        return json_ok({
            'vin': vin,
            'items': trips,
        })
