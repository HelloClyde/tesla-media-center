import os
import sqlite3
import time
import base64
import json
import math
import threading
import asyncio
from typing import Any

import requests
import aiohttp
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
TESLA_ASLEEP_POLL_INTERVAL_SEC = 30 * 60
TESLA_DRIVING_POLL_INTERVAL_SEC = 2.5
TESLA_DEFAULT_POLL_INTERVAL_SEC = 15
TESLA_ONLINE_POLL_INTERVAL_SEC = 60
TESLA_CHARGING_POLL_INTERVAL_SEC = 5
TESLA_ASLEEP_PROBE_INTERVALS_SEC = [60]
TESLA_BACKOFF_INITIAL_SEC = 10
TESLA_BACKOFF_MAX_SEC = 30 * 60
TESLA_STREAM_TIMEOUT_SEC = 30
TESLA_VEHICLE_DATA_ENDPOINTS = (
    'charge_state;climate_state;closures_state;drive_state;gui_settings;'
    'location_data;vehicle_config;vehicle_state;vehicle_data_combo'
)
tesla_sync_thread = None
tesla_sync_stop_event = threading.Event()
tesla_sync_backoff_sec = 0
tesla_asleep_streak = 0
tesla_collection_mode = 'rest'
tesla_last_stream_result = ''
tesla_stream_phase = 'idle'


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
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(tesla_vehicle_samples)").fetchall()
        }
        if 'speed_unit' not in existing_columns:
            conn.execute('ALTER TABLE tesla_vehicle_samples ADD COLUMN speed_unit TEXT')
        if 'distance_unit' not in existing_columns:
            conn.execute('ALTER TABLE tesla_vehicle_samples ADD COLUMN distance_unit TEXT')
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


def get_tesla_wss_base_url():
    return 'wss://streaming.vn.cloud.tesla.cn' if get_tesla_region() == 'chinese' else 'wss://streaming.vn.teslamotors.com'


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


def normalize_distance_unit(gui_settings: dict[str, Any]):
    value = str(gui_settings.get('gui_distance_units') or '').lower()
    if 'km' in value:
        return 'km'
    if 'mile' in value or 'mi' in value:
        return 'mi'
    return 'km'


def convert_speed_to_kmh(speed: Any):
    if not isinstance(speed, (int, float)):
        return None
    return round(float(speed) * 1.609344, 1)


def convert_distance_to_km(distance: Any):
    if not isinstance(distance, (int, float)):
        return None
    return round(float(distance) * 1.609344, 2)


def normalize_sample_units(sample: dict[str, Any]):
    if not sample:
        return sample
    speed = sample.get('speed')
    speed_unit = sample.get('speed_unit')
    if isinstance(speed, (int, float)) and speed_unit != 'km/h':
        sample['speed'] = convert_speed_to_kmh(speed)
        sample['speed_unit'] = 'km/h'
    elif speed_unit is None and speed is not None:
        sample['speed_unit'] = 'km/h'
    odometer = sample.get('odometer')
    distance_unit = sample.get('distance_unit')
    if isinstance(odometer, (int, float)) and distance_unit != 'km':
        sample['odometer'] = convert_distance_to_km(odometer)
        sample['distance_unit'] = 'km'
    elif odometer is not None and not distance_unit:
        sample['distance_unit'] = 'km'
    elif not distance_unit:
        sample['distance_unit'] = 'km'
    return sample


def parse_stream_value(value: str):
    fields = value.split(',')
    columns = [
        'time', 'speed', 'odometer', 'soc', 'elevation', 'est_heading', 'est_lat', 'est_lng',
        'power', 'shift_state', 'range', 'est_range', 'heading'
    ]
    payload: dict[str, Any] = dict(zip(columns, fields))

    def to_int(name: str):
        raw = payload.get(name)
        if raw in ['', None]:
            payload[name] = None
            return
        try:
            payload[name] = int(raw)
        except Exception:
            payload[name] = None

    def to_float(name: str):
        raw = payload.get(name)
        if raw in ['', None]:
            payload[name] = None
            return
        try:
            payload[name] = float(raw)
        except Exception:
            payload[name] = None

    for key in ['speed', 'soc', 'elevation', 'est_heading', 'power', 'range', 'est_range', 'heading']:
        to_int(key)
    for key in ['odometer', 'est_lat', 'est_lng']:
        to_float(key)
    if payload.get('shift_state') == '':
        payload['shift_state'] = None
    return payload


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


def increase_tesla_backoff():
    global tesla_sync_backoff_sec
    tesla_sync_backoff_sec = min(
        TESLA_BACKOFF_MAX_SEC,
        tesla_sync_backoff_sec * 2 if tesla_sync_backoff_sec > 0 else TESLA_BACKOFF_INITIAL_SEC,
    )
    return tesla_sync_backoff_sec


def reset_tesla_backoff():
    global tesla_sync_backoff_sec
    tesla_sync_backoff_sec = 0


def increase_tesla_asleep_streak():
    global tesla_asleep_streak
    tesla_asleep_streak += 1
    return tesla_asleep_streak


def reset_tesla_asleep_streak():
    global tesla_asleep_streak
    tesla_asleep_streak = 0


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
        if resp.status_code == 403:
            return None, ('permission_denied', 'Tesla 账号权限不足或当前车辆不可访问')
        if resp.status_code == 429:
            return None, ('rate_limited', 'Tesla 接口限流，稍后自动重试')
        if resp.status_code == 451:
            return None, ('wrong_region', 'Tesla 接口区域不匹配，请检查 China / Global 配置')
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


def fetch_products_vehicles():
    data, error = tesla_api_request('GET', '/api/1/products')
    if error:
        return None, error
    products = data.get('response') or []
    logger.info(
        f'tesla products fetched, total={len(products)}, '
        f'vehicle_items={len([item for item in products if item.get("vehicle_id")])}'
    )
    vehicles = [normalize_vehicle_record(item) for item in products if item.get('vehicle_id')]
    for vehicle in vehicles:
        upsert_vehicle_cache(vehicle)
    return vehicles, None


def extract_vehicle_location(payload: dict[str, Any]):
    drive_state = payload.get('drive_state') or {}
    location_data = payload.get('location_data') or {}
    latitude = drive_state.get('latitude')
    longitude = drive_state.get('longitude')
    heading = drive_state.get('heading')

    if latitude is None:
        latitude = location_data.get('latitude')
    if longitude is None:
        longitude = location_data.get('longitude')
    if heading is None:
        heading = location_data.get('heading')

    return {
        'latitude': latitude,
        'longitude': longitude,
        'heading': heading,
    }


def extract_sample_from_vehicle_data(vin: str, display_name: str, vehicle_state: str, payload: dict[str, Any]):
    drive_state = payload.get('drive_state') or {}
    charge_state = payload.get('charge_state') or {}
    climate_state = payload.get('climate_state') or {}
    vehicle_state_data = payload.get('vehicle_state') or {}
    gui_settings = payload.get('gui_settings') or {}
    vehicle_config = payload.get('vehicle_config') or {}
    location = extract_vehicle_location(payload)
    return {
        'vin': vin,
        'display_name': display_name,
        'vehicle_state': vehicle_state,
        'latitude': location.get('latitude'),
        'longitude': location.get('longitude'),
        'heading': location.get('heading'),
        'speed': convert_speed_to_kmh(drive_state.get('speed')),
        'speed_unit': 'km/h',
        'shift_state': drive_state.get('shift_state'),
        'battery_level': charge_state.get('battery_level'),
        'usable_battery_level': charge_state.get('usable_battery_level'),
        'charging_state': charge_state.get('charging_state'),
        'charge_limit_soc': charge_state.get('charge_limit_soc'),
        'odometer': convert_distance_to_km(vehicle_state_data.get('odometer')),
        'distance_unit': 'km',
        'locked': vehicle_state_data.get('locked'),
        'inside_temp': climate_state.get('inside_temp'),
        'outside_temp': climate_state.get('outside_temp'),
        'is_climate_on': climate_state.get('is_climate_on'),
        'sentry_mode': vehicle_state_data.get('sentry_mode'),
        'timestamp_ms': int(time.time() * 1000),
        'vehicle_config': vehicle_config,
    }


def extract_sample_from_stream_data(vin: str, display_name: str, vehicle_state: str, stream_data: dict[str, Any], previous: dict[str, Any] | None = None):
    previous = previous or {}
    timestamp_ms = stream_data.get('time')
    if not isinstance(timestamp_ms, int):
        timestamp_ms = int(time.time() * 1000)
    return normalize_sample_units({
        'vin': vin,
        'display_name': display_name,
        'vehicle_state': vehicle_state or previous.get('vehicle_state') or 'online',
        'latitude': stream_data.get('est_lat'),
        'longitude': stream_data.get('est_lng'),
        'heading': stream_data.get('heading'),
        'speed': convert_speed_to_kmh(stream_data.get('speed')),
        'speed_unit': 'km/h',
        'shift_state': stream_data.get('shift_state'),
        'battery_level': stream_data.get('soc') if stream_data.get('soc') is not None else previous.get('battery_level'),
        'usable_battery_level': previous.get('usable_battery_level'),
        'charging_state': previous.get('charging_state'),
        'charge_limit_soc': previous.get('charge_limit_soc'),
        'odometer': round(float(stream_data.get('odometer')), 2) * 1.609344 if isinstance(stream_data.get('odometer'), (int, float)) else previous.get('odometer'),
        'distance_unit': 'km',
        'locked': previous.get('locked'),
        'inside_temp': previous.get('inside_temp'),
        'outside_temp': previous.get('outside_temp'),
        'is_climate_on': previous.get('is_climate_on'),
        'sentry_mode': previous.get('sentry_mode'),
        'timestamp_ms': timestamp_ms,
    })


def insert_vehicle_sample(sample: dict[str, Any]):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        latest = conn.execute(
            '''
            SELECT *
            FROM tesla_vehicle_samples
            WHERE vin = ?
            ORDER BY timestamp_ms DESC
            LIMIT 1
            ''',
            (sample.get('vin'),),
        ).fetchone()

        if latest:
            latest = dict(latest)
            timestamp_gap_ms = abs(int(sample.get('timestamp_ms') or 0) - int(latest.get('timestamp_ms') or 0))
            same_snapshot = (
                latest.get('vehicle_state') == sample.get('vehicle_state') and
                latest.get('shift_state') == sample.get('shift_state') and
                latest.get('charging_state') == sample.get('charging_state') and
                latest.get('battery_level') == sample.get('battery_level') and
                latest.get('speed') == sample.get('speed') and
                latest.get('odometer') == sample.get('odometer') and
                latest.get('latitude') == sample.get('latitude') and
                latest.get('longitude') == sample.get('longitude')
            )
            if same_snapshot and timestamp_gap_ms <= 60 * 1000:
                conn.execute(
                    '''
                    UPDATE tesla_vehicle_samples
                    SET display_name = ?, heading = ?, usable_battery_level = ?, charge_limit_soc = ?,
                        speed_unit = ?, distance_unit = ?, locked = ?, inside_temp = ?, outside_temp = ?,
                        is_climate_on = ?, sentry_mode = ?, timestamp_ms = ?, created_at = ?
                    WHERE id = ?
                    ''',
                    (
                        sample.get('display_name'),
                        sample.get('heading'),
                        sample.get('usable_battery_level'),
                        sample.get('charge_limit_soc'),
                        sample.get('speed_unit'),
                        sample.get('distance_unit'),
                        1 if sample.get('locked') else 0 if sample.get('locked') is not None else None,
                        sample.get('inside_temp'),
                        sample.get('outside_temp'),
                        1 if sample.get('is_climate_on') else 0 if sample.get('is_climate_on') is not None else None,
                        1 if sample.get('sentry_mode') else 0 if sample.get('sentry_mode') is not None else None,
                        sample.get('timestamp_ms'),
                        int(time.time()),
                        latest.get('id'),
                    ),
                )
                conn.commit()
                return

        conn.execute(
            '''
            INSERT INTO tesla_vehicle_samples (
                vin, display_name, vehicle_state, latitude, longitude, heading, speed, shift_state,
                battery_level, usable_battery_level, charging_state, charge_limit_soc, odometer, speed_unit, distance_unit,
                locked, inside_temp, outside_temp, is_climate_on, sentry_mode, timestamp_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                sample.get('speed_unit'),
                sample.get('distance_unit'),
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


def latest_position_sample(vin: str):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            '''
            SELECT *
            FROM tesla_vehicle_samples
            WHERE vin = ? AND latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY timestamp_ms DESC
            LIMIT 1
            ''',
            (vin,),
        ).fetchone()
    return normalize_sample_units(dict(row)) if row else None


def restore_last_known_position(sample: dict[str, Any] | None, vin: str):
    if not sample:
        return sample
    if sample.get('latitude') is not None and sample.get('longitude') is not None:
        return sample
    last_position = latest_position_sample(vin)
    if not last_position:
        return sample
    sample['latitude'] = last_position.get('latitude')
    sample['longitude'] = last_position.get('longitude')
    sample['heading'] = sample.get('heading') if sample.get('heading') is not None else last_position.get('heading')
    return sample


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


def delete_trip_samples(vin: str, start_ms: int, end_ms: int):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        deleted = conn.execute(
            'DELETE FROM tesla_vehicle_samples WHERE vin = ? AND timestamp_ms >= ? AND timestamp_ms <= ?',
            (vin, start_ms, end_ms),
        ).rowcount
        conn.commit()
    return deleted


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
        'effectivePollIntervalSec': get_recommended_poll_interval_sec(),
        'currentBackoffSec': tesla_sync_backoff_sec,
        'backgroundSyncRunning': tesla_sync_thread is not None and tesla_sync_thread.is_alive(),
        'collectionMode': tesla_collection_mode,
        'lastStreamResult': tesla_last_stream_result,
        'streamPhase': tesla_stream_phase,
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
    return restore_last_known_position(normalize_sample_units(dict(row)) if row else None, vin)


def recent_vehicle_track(vin: str, limit: int = 500):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        start_ms = request.args.get('startMs')
        end_ms = request.args.get('endMs')
        clauses = ['vin = ?', 'latitude IS NOT NULL', 'longitude IS NOT NULL']
        params: list[Any] = [vin]
        if start_ms:
            clauses.append('timestamp_ms >= ?')
            params.append(int(start_ms))
        if end_ms:
            clauses.append('timestamp_ms <= ?')
            params.append(int(end_ms))
        params.append(limit)
        rows = conn.execute(
            f'''
            SELECT id, vin, display_name, latitude, longitude, heading, speed, speed_unit, shift_state, battery_level, vehicle_state, timestamp_ms
            FROM tesla_vehicle_samples
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp_ms DESC
            LIMIT ?
            ''',
            tuple(params),
        ).fetchall()
    return [normalize_sample_units(dict(row)) for row in reversed(rows)]


def recent_vehicle_samples(vin: str, limit: int = 2000):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT id, vin, display_name, latitude, longitude, heading, speed, speed_unit, shift_state, battery_level,
                   usable_battery_level, charging_state, charge_limit_soc, odometer, distance_unit, vehicle_state, timestamp_ms
            FROM tesla_vehicle_samples
            WHERE vin = ?
            ORDER BY timestamp_ms DESC
            LIMIT ?
            ''',
            (vin, limit),
        ).fetchall()
    return [normalize_sample_units(dict(row)) for row in reversed(rows)]


def paged_vehicle_samples(vin: str, page: int = 1, page_size: int = 50):
    ensure_tesla_storage()
    db_path = get_tesla_db_path()
    offset = max(0, (page - 1) * page_size)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            'SELECT COUNT(*) AS c FROM tesla_vehicle_samples WHERE vin = ?',
            (vin,),
        ).fetchone()['c']
        rows = conn.execute(
            '''
            SELECT id, vin, display_name, vehicle_state, latitude, longitude, heading, speed, speed_unit,
                   shift_state, battery_level, usable_battery_level, charging_state, charge_limit_soc,
                   odometer, distance_unit, locked, inside_temp, outside_temp, is_climate_on, sentry_mode,
                   timestamp_ms, created_at
            FROM tesla_vehicle_samples
            WHERE vin = ?
            ORDER BY timestamp_ms DESC
            LIMIT ? OFFSET ?
            ''',
            (vin, page_size, offset),
        ).fetchall()
    return {
        'items': [normalize_sample_units(dict(row)) for row in rows],
        'total': total,
        'page': page,
        'pageSize': page_size,
    }


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
        start_odo = start.get('odometer')
        end_odo = end.get('odometer')
        track_point_count = len([
            sample for sample in trip_samples
            if sample.get('latitude') is not None and sample.get('longitude') is not None
        ])
        if isinstance(start_odo, (int, float)) and isinstance(end_odo, (int, float)) and end_odo >= start_odo:
            distance_km = float(end_odo) - float(start_odo)
        sessions.append({
            'vin': vin,
            'displayName': end.get('display_name') or start.get('display_name'),
            'startTimeMs': start.get('timestamp_ms'),
            'endTimeMs': end.get('timestamp_ms'),
            'durationSec': max(0, int((end.get('timestamp_ms') - start.get('timestamp_ms')) / 1000)),
            'distanceKm': round(distance_km, 2),
            'maxSpeed': round(max_speed, 1),
            'speedUnit': 'km/h',
            'startBatteryLevel': start.get('battery_level'),
            'endBatteryLevel': end.get('battery_level'),
            'startPosition': {'latitude': start.get('latitude'), 'longitude': start.get('longitude')},
            'endPosition': {'latitude': end.get('latitude'), 'longitude': end.get('longitude')},
            'pointCount': track_point_count,
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


def has_stream_candidates(vehicles: list[dict[str, Any]] | None = None):
    source = vehicles if vehicles is not None else cached_vehicles()
    return any((vehicle.get('state') or '').lower() == 'online' for vehicle in source)


def get_recommended_poll_interval_sec(vehicles: list[dict[str, Any]] | None = None):
    base_interval = TESLA_DEFAULT_POLL_INTERVAL_SEC
    vehicles = vehicles if vehicles is not None else cached_vehicles()
    latest_samples = [latest_vehicle_sample(vehicle.get('vin')) for vehicle in vehicles if vehicle.get('vin')]

    for sample in latest_samples:
        if not sample:
            continue
        shift_state = (sample.get('shift_state') or '').upper()
        speed = sample.get('speed')
        if shift_state in ['D', 'R', 'N'] or (isinstance(speed, (int, float)) and speed > 0):
            base_interval = TESLA_DRIVING_POLL_INTERVAL_SEC
            break

    if base_interval != TESLA_DRIVING_POLL_INTERVAL_SEC:
        for sample in latest_samples:
            if not sample:
                continue
            charging_state = (sample.get('charging_state') or '').lower()
            if charging_state and charging_state not in ['disconnected', 'complete', 'stopped', '']:
                base_interval = TESLA_CHARGING_POLL_INTERVAL_SEC
                break

    if base_interval == TESLA_DEFAULT_POLL_INTERVAL_SEC:
        if any((vehicle.get('state') or '').lower() in ['online'] for vehicle in vehicles):
            base_interval = TESLA_ONLINE_POLL_INTERVAL_SEC
        elif vehicles and all((vehicle.get('state') or '').lower() in ['asleep', 'offline'] for vehicle in vehicles):
            streak = min(tesla_asleep_streak, len(TESLA_ASLEEP_PROBE_INTERVALS_SEC) - 1)
            base_interval = TESLA_ASLEEP_PROBE_INTERVALS_SEC[streak]

    return max(base_interval, tesla_sync_backoff_sec)


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


def fetch_vehicle_brief(vehicle_id: str):
    return tesla_api_request('GET', f'/api/1/vehicles/{vehicle_id}')


def fetch_vehicle_with_state(vehicle_id: str):
    return tesla_api_request(
        'GET',
        f'/api/1/vehicles/{vehicle_id}/vehicle_data',
        params={'endpoints': TESLA_VEHICLE_DATA_ENDPOINTS},
    )


def sync_vehicle(vin: str, display_name: str, state: str):
    vehicles_data, vehicles_error = tesla_api_request('GET', '/api/1/products')
    if vehicles_error:
        return {'vin': vin, 'displayName': display_name, 'state': state, 'error': vehicles_error[1]}

    products = vehicles_data.get('response') or vehicles_data or []
    target = next((item for item in products if item.get('vin') == vin or str(item.get('vehicle_id') or '') == str(vin)), None)
    vehicle_id = target.get('id') if target else None
    if not vehicle_id:
        return {'vin': vin, 'displayName': display_name, 'state': state, 'error': 'Tesla 未返回该车辆的在线数据入口'}

    if state in ['online', 'driving']:
        data, error = fetch_vehicle_with_state(vehicle_id)
        if error and error[0] == 'vehicle_unavailable':
            data, error = fetch_vehicle_brief(vehicle_id)
    else:
        data, error = fetch_vehicle_brief(vehicle_id)
        if not error:
            response = data.get('response') or data or {}
            fetched_state = (response.get('state') or state or '').lower()
            if fetched_state == 'online':
                data, error = fetch_vehicle_with_state(vehicle_id)

    if error:
        # Keep the local timeline fresh even when Tesla only returns the coarse
        # products state but the detailed vehicle_data fetch is temporarily unavailable.
        sample = {
            'vin': vin,
            'display_name': display_name,
            'vehicle_state': state,
            'timestamp_ms': int(time.time() * 1000),
        }
        sample = restore_last_known_position(sample, vin)
        insert_vehicle_sample(sample)
        if state in ['asleep', 'offline']:
            return {'vin': vin, 'displayName': display_name, 'state': state, 'sample': sample, 'warning': error[1]}
        logger.warning(f'tesla vehicle_data fetch failed after products state update, vin={vin}, state={state}, error={error}')
        return {'vin': vin, 'displayName': display_name, 'state': state, 'sample': sample, 'warning': error[1]}

    payload = data.get('response') or data
    resolved_state = (payload.get('state') or state or 'unknown').lower()
    sample = extract_sample_from_vehicle_data(vin, display_name, resolved_state, payload)
    if sample.get('latitude') is None or sample.get('longitude') is None:
        logger.warning(
            f'tesla vehicle_data missing coordinates, vin={vin}, '
            f'state={resolved_state}, '
            f'drive_lat={((payload.get("drive_state") or {}).get("latitude"))}, '
            f'drive_lng={((payload.get("drive_state") or {}).get("longitude"))}, '
            f'loc_lat={((payload.get("location_data") or {}).get("latitude"))}, '
            f'loc_lng={((payload.get("location_data") or {}).get("longitude"))}'
        )
    sample = restore_last_known_position(sample, vin)
    insert_vehicle_sample(sample)
    return {
        'vin': vin,
        'displayName': display_name,
        'state': resolved_state,
        'sample': sample,
    }


def sync_all_vehicles(target_vin: str | None = None):
    vehicles, error = fetch_products_vehicles()
    if error:
        return None, error
    if target_vin:
        vehicles = [item for item in vehicles if item.get('vin') == target_vin]
    synced = [sync_vehicle(item['vin'], item['displayName'], item.get('state')) for item in vehicles if item.get('vin')]
    put_config_by_key('tesla_last_sync_at', int(time.time()))
    prune_tesla_storage()
    return synced, None


async def stream_vehicle_updates_once(vehicle: dict[str, Any], timeout_sec: int = TESLA_STREAM_TIMEOUT_SEC):
    global tesla_stream_phase
    access_token = refresh_tesla_access_token()
    if not access_token:
        tesla_stream_phase = 'not_authorized'
        return 'not_authorized'

    vehicle_id = str(vehicle.get('vehicleId') or vehicle.get('id') or '')
    vin = vehicle.get('vin')
    if not vehicle_id or not vin:
        tesla_stream_phase = 'invalid_vehicle'
        return 'invalid_vehicle'

    url = f'{get_tesla_wss_base_url()}/streaming/'
    subscribe_payload = {
        'msg_type': 'data:subscribe_oauth',
        'token': access_token,
        'value': 'speed,odometer,soc,elevation,est_heading,est_lat,est_lng,power,shift_state,range,est_range,heading',
        'tag': vehicle_id,
    }
    timeout = aiohttp.ClientTimeout(sock_connect=15, sock_read=timeout_sec + 5, total=None)
    last_data_at = time.time()
    previous = latest_vehicle_sample(vin) or {}
    updates = 0

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers={'User-Agent': DEFAULT_TESLA_USER_AGENT}) as session:
            tesla_stream_phase = 'connecting'
            async with session.ws_connect(url, heartbeat=20) as ws:
                await ws.send_json(subscribe_payload)
                tesla_stream_phase = 'subscribed'
                logger.info(f'tesla streaming connected, vin={vin}, vehicle_id={vehicle_id}')
                while not tesla_sync_stop_event.is_set():
                    try:
                        msg = await ws.receive(timeout=1)
                    except asyncio.TimeoutError:
                        if time.time() - last_data_at >= timeout_sec:
                            tesla_stream_phase = 'inactive'
                            logger.info(f'tesla streaming inactive timeout, vin={vin}')
                            return 'inactive'
                        continue

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(msg.data)
                        msg_type = payload.get('msg_type')
                        if msg_type == 'control:hello':
                            continue
                        if msg_type == 'data:update' and payload.get('tag') == vehicle_id and isinstance(payload.get('value'), str):
                            tesla_stream_phase = 'updates'
                            stream_data = parse_stream_value(payload['value'])
                            sample = extract_sample_from_stream_data(vin, vehicle.get('displayName'), vehicle.get('state'), stream_data, previous)
                            insert_vehicle_sample(sample)
                            previous = sample
                            updates += 1
                            last_data_at = time.time()
                            continue
                        if msg_type == 'data:error' and payload.get('tag') == vehicle_id:
                            error_type = payload.get('error_type')
                            value = payload.get('value')
                            tesla_stream_phase = f'error:{error_type or "unknown"}'
                            logger.warning(f'tesla streaming error, vin={vin}, type={error_type}, value={value}')
                            if error_type == 'vehicle_disconnected':
                                return 'vehicle_disconnected'
                            if error_type == 'client_error' and isinstance(value, str) and 'validate token' in value.lower():
                                return 'tokens_expired'
                            if error_type == 'vehicle_error' and value == 'Vehicle is offline':
                                return 'vehicle_offline'
                            return 'stream_error'
                    elif msg.type in [aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR]:
                        tesla_stream_phase = 'closed'
                        logger.warning(f'tesla streaming closed, vin={vin}, type={msg.type}')
                        return 'closed'
    except Exception as e:
        tesla_stream_phase = 'exception'
        logger.warning(f'tesla streaming exception, vin={vin}, error={e}')
        return 'stream_exception'

    return 'updates' if updates > 0 else 'inactive'


def stream_active_vehicles_once():
    vehicles = [vehicle for vehicle in cached_vehicles() if vehicle.get('vin') and vehicle.get('state') not in ['asleep', 'offline']]
    if not vehicles:
        return None, ('no_stream_candidates', '没有可用的在线车辆用于流式采集')
    results = []
    for vehicle in vehicles:
        result = asyncio.run(stream_vehicle_updates_once(vehicle))
        results.append({'vin': vehicle.get('vin'), 'result': result})
    return results, None


def tesla_background_sync_loop():
    global tesla_collection_mode
    global tesla_last_stream_result
    global tesla_stream_phase
    logger.info('tesla background sync thread started')
    while not tesla_sync_stop_event.is_set():
        try:
            refresh_tesla_access_token()
            if tesla_tokens_configured():
                vehicles, products_error = fetch_products_vehicles()
                if products_error:
                    raise Exception(products_error[1])
                used_streaming = False
                stream_results = None
                if has_stream_candidates(vehicles):
                    stream_results, stream_error = stream_active_vehicles_once()
                    if stream_error:
                        tesla_last_stream_result = stream_error[0]
                        tesla_stream_phase = f'fallback:{stream_error[0]}'
                        logger.warning(f'tesla streaming skipped: {stream_error}')
                    else:
                        logger.info(f'tesla streaming finished: {stream_results}')
                        tesla_last_stream_result = ','.join(
                            f'{item.get("vin")}:{item.get("result")}' for item in (stream_results or [])
                        )
                        used_streaming = any(item.get('result') == 'updates' for item in (stream_results or []))
                        if used_streaming:
                            tesla_collection_mode = 'streaming'
                        else:
                            tesla_stream_phase = f'fallback:{tesla_last_stream_result or "inactive"}'
                else:
                    tesla_stream_phase = 'no_online_vehicle'

                if not used_streaming:
                    tesla_collection_mode = 'rest'
                    synced = [sync_vehicle(item['vin'], item['displayName'], item.get('state')) for item in vehicles if item.get('vin')]
                    error = None
                    if error:
                        backoff = increase_tesla_backoff()
                        logger.warning(f'tesla background sync failed: {error}, backoff={backoff}s')
                    else:
                        put_config_by_key('tesla_last_sync_at', int(time.time()))
                        prune_tesla_storage()
                        reset_tesla_backoff()
                        logger.info(f'tesla background sync finished, items={len(synced or [])}')
                else:
                    reset_tesla_backoff()
            else:
                tesla_collection_mode = 'idle'
                tesla_last_stream_result = ''
                tesla_stream_phase = 'idle'
                reset_tesla_backoff()

            vehicles = cached_vehicles()
            if vehicles and all((vehicle.get('state') or '').lower() in ['asleep', 'offline'] for vehicle in vehicles):
                increase_tesla_asleep_streak()
            else:
                reset_tesla_asleep_streak()
            prune_tesla_storage()
        except Exception as e:
            backoff = increase_tesla_backoff()
            logger.exception(f'tesla background sync exception: {e}')
            logger.warning(f'tesla background sync backoff={backoff}s')
        tesla_sync_stop_event.wait(get_recommended_poll_interval_sec(cached_vehicles()))


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

    @app.route('/api/tesla/history/trips', methods=['DELETE'])
    @login_check
    def tesla_trip_delete():
        data = request.json or {}
        vin = str(data.get('vin') or '').strip()
        start_ms = int(data.get('startTimeMs') or 0)
        end_ms = int(data.get('endTimeMs') or 0)
        if not vin or start_ms <= 0 or end_ms <= 0:
            return json_fail('trip_required', message='缺少行程标识'), 400
        deleted = delete_trip_samples(vin, start_ms, end_ms)
        prune_tesla_storage()
        return json_ok({'deletedCount': deleted})

    @app.route('/api/tesla/history/raw', methods=['GET'])
    @login_check
    def tesla_raw_history():
        vin = request.args.get('vin', '')
        page = max(1, int(request.args.get('page', '1')))
        page_size = min(200, max(10, int(request.args.get('pageSize', '50'))))
        if not vin:
            return json_fail('vin_required', message='缺少 VIN'), 400
        return json_ok(paged_vehicle_samples(vin, page, page_size))
