"""Session-isolated, temporary Tencent Video App QR authorization."""
import base64
import io
import secrets
import threading
import time
from urllib.parse import urlencode

import qrcode
import requests
from flask import request, session
from ffvideo.utils import login_check, json_ok, json_fail

BASE = 'https://pbaccess.video.qq.com/trpc.anywhere_door.account.'
HEADERS = {'Origin': 'https://v.qq.com', 'Referer': 'https://v.qq.com/', 'User-Agent': 'Mozilla/5.0'}


class Accounts:
    def __init__(self):
        self.entries = {}
        self.lock = threading.RLock()

    def entry(self):
        now = time.time()
        for key, value in list(self.entries.items()):
            if value['expires'] <= now:
                self.entries.pop(key, None)
        return self.entries.get(session.get('tencent_account'))

    def cookies(self):
        with self.lock:
            entry = self.entry()
            return dict(entry.get('cookies', {})) if entry else {}


def api(method, body, guid):
    with requests.post(BASE + method, params={'video_appid': '3000010',
                       'vversion_platform': '2', 'vdevice_guid': guid},
                       json=body, headers=HEADERS, timeout=(5, 12), allow_redirects=False) as response:
        response.raise_for_status()
        result = response.json()
    if result.get('ret', result.get('errorCode', -1)) != 0 or not isinstance(result.get('data'), dict):
        raise ValueError('腾讯登录接口暂不可用，请稍后重试')
    return result['data']


def add_routes(app):
    accounts = Accounts()
    app.extensions['tencent_accounts'] = accounts

    @app.before_request
    def guard_auth_mutations():
        if request.path.startswith('/api/tencent-video/auth') and request.method in ('POST', 'DELETE'):
            if request.headers.get('X-Requested-With') != 'TencentVideo':
                return json_fail('invalid_request', message='请从腾讯视频应用操作登录'), 403

    @app.after_request
    def no_store_auth(response):
        if request.path.startswith('/api/tencent-video/auth'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/api/tencent-video/auth', methods=['GET', 'DELETE'])
    @login_check
    def status():
        with accounts.lock:
            entry = accounts.entry()
            if request.method == 'DELETE':
                accounts.entries.pop(session.pop('tencent_account', None), None)
                entry = None
            result = json_ok({'loggedIn': bool(entry and entry.get('cookies')),
                              'nickname': entry.get('nickname', '') if entry else ''})
            result.headers['Cache-Control'] = 'no-store'
            return result

    @app.route('/api/tencent-video/auth/qrcode', methods=['POST'])
    @login_check
    def create():
        try:
            guid = secrets.token_hex(16)
            data = api('QRCode/GenQRCode', {'qrcode_id_type': 1, 'last_qr_code_id': ''}, guid)
            qr_id = data['qr_code_id']
            expires = min(float(data['expire_time']), time.time() + 300)
            if not isinstance(qr_id, str) or not qr_id or expires <= time.time():
                raise ValueError('二维码已过期，请刷新')
            url = 'https://m.v.qq.com/z/app/auth-page/index.html?' + urlencode({
                'qr_code_id': qr_id, 'qr_expire_at': int(expires * 1000), '_pc': 'web',
                '_env': '', 'ovscroll': 1, 'hideLoading': 'true', 'hideMoreButton': 1})
            image = io.BytesIO()
            qrcode.make(url).save(image, format='PNG')
            with accounts.lock:
                accounts.entry()
                if len(accounts.entries) >= 256:
                    raise ValueError('登录请求过多，请稍后重试')
                accounts.entries.pop(session.get('tencent_account'), None)
                key = secrets.token_urlsafe(32)
                session['tencent_account'] = key
                accounts.entries[key] = {'guid': guid, 'qr': qr_id, 'expires': expires}
            response = json_ok({'qrcode': 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode(),
                                'expiresAt': expires})
            response.headers['Cache-Control'] = 'no-store'
            return response
        except (ValueError, KeyError, TypeError, requests.RequestException):
            return json_fail('login_failed', message='生成腾讯视频登录二维码失败，请重试'), 502

    @app.route('/api/tencent-video/auth/qrcode/poll', methods=['POST'])
    @login_check
    def poll():
        with accounts.lock:
            entry = accounts.entry()
            if not entry:
                return json_fail('expired', message='二维码已过期，请刷新'), 410
            if entry.get('cookies'):
                return json_ok({'state': 'confirmed', 'nickname': entry['nickname']})
            if entry.get('polling') or time.time() - entry.get('lastPoll', 0) < 2:
                return json_ok({'state': 'pending'})
            entry['polling'] = True
            entry['lastPoll'] = time.time()
        try:
            data = api('QRCode/QRCodeStatus', {'qr_code_id': entry['qr']}, entry['guid'])
            state = int(data['status'])
            if state == 3:
                data = api('WebAccount/Login', {'main_login': '', 'device_info': {
                    'platform': '2', 'guid': entry['guid'], 'appid': '3000010', 'version': ''},
                    'login_request': {'login_type': 4, 'sign_info': {}, 'qr_code_login_request': {
                        'qr_code_id': entry['qr'], 'qq_app_id': '101483052', 'wx_app_id': 'wx5ed58254bc0d6b7f'}}}, entry['guid'])
                if data.get('error_code') != 0:
                    raise ValueError('授权交换失败')
                login = data['login_response']
                expires = min(float(login['vusession_expire_timestamp']), time.time() + 21600)
                if not login.get('vuid') or not login.get('vusession') or expires <= time.time():
                    raise ValueError('无效授权')
                with accounts.lock:
                    if accounts.entry() is not entry:
                        return json_fail('expired', message='登录已取消'), 410
                    entry.update(cookies={'vuserid': str(login['vuid']), 'vusession': login['vusession']},
                                 nickname=str((login.get('user_info') or {}).get('user_nick') or '腾讯视频用户')[:100],
                                 expires=expires)
                return json_ok({'state': 'confirmed', 'nickname': entry['nickname']})
            if state in (4, 5, 6):
                with accounts.lock:
                    if accounts.entry() is entry:
                        accounts.entries.pop(session.get('tencent_account'), None)
                return json_fail('expired', message='授权已取消或二维码已过期，请刷新'), 410
            return json_ok({'state': 'scanned' if state == 2 else 'pending'})
        except (ValueError, KeyError, TypeError, requests.RequestException):
            return json_fail('login_failed', message='腾讯授权未完成，请刷新重试；如遇风控请在官方客户端处理'), 502
        finally:
            with accounts.lock:
                entry['polling'] = False

    return accounts
