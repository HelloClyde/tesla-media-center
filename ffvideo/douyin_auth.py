"""Temporary, session-isolated login through the official Douyin QR panel."""
import copy
import logging
import re
import secrets
import threading
import time

from flask import request, session
from ffvideo.utils import login_check, json_ok, json_fail

logger = logging.getLogger(__name__)


class Accounts:
    def __init__(self):
        self.lock = threading.RLock()
        self.entries = {}
        self.slots = threading.BoundedSemaphore(2)

    def entry(self):
        now = time.time()
        for key, entry in list(self.entries.items()):
            if entry['expires'] <= now:
                entry['cancel'].set()
                self.entries.pop(key, None)
        return self.entries.get(session.get('douyin_account'))

    def credentials(self):
        with self.lock:
            entry = self.entry()
            return copy.deepcopy(entry.get('cookies', [])) if entry else []

    def update(self, entry, **values):
        with self.lock:
            if not entry['cancel'].is_set():
                entry.update(values)

    @staticmethod
    def http_cookies(client):
        return [
            {'name': cookie.name, 'value': cookie.value, 'domain': cookie.domain,
             'path': cookie.path or '/', 'secure': cookie.secure,
             'httpOnly': cookie.has_nonstandard_attr('HttpOnly')}
            for cookie in client.cookies.jar
            if cookie.domain.lstrip('.') in ('douyin.com', 'www.douyin.com', 'login.douyin.com')
        ]

    def run_http(self, entry):
        client = None
        stage = 'visitor'
        try:
            from tools.douyin.visitor_probe import (create_visitor_session, get_qrcode,
                                                     check_qrcode, finish_qrcode_login)
            client = create_visitor_session()
            stage = 'qrcode'
            qr = get_qrcode(client)
            image = qr['qrcode']
            if not image.startswith('data:image/'):
                image = 'data:image/png;base64,' + image
            self.update(entry, state='waiting', qrcode=image,
                        message='请使用抖音 App 扫码，并在手机上确认登录')
            while not entry['cancel'].is_set() and time.time() < entry['expires']:
                if time.time() - entry['touched'] > 45:
                    break
                stage = 'poll'
                data = check_qrcode(client, qr['token'], qr.get('is_frontier', False))
                state = data.get('status')
                if isinstance(state, int):
                    state = str(state)
                if data.get('redirect_url') or state in ('3', 'confirmed'):
                    redirect = data.get('redirect_url')
                    if redirect:
                        stage = 'redirect'
                        finish_qrcode_login(client, redirect)
                    cookies = self.http_cookies(client)
                    if any(c['name'] == 'sessionid' and c['value'] and
                           c['domain'].lstrip('.') in ('douyin.com', 'www.douyin.com')
                           for c in cookies):
                        self.update(entry, cookies=cookies, state='confirmed', qrcode='',
                                    message='已登录', expires=time.time() + 86400)
                    else:
                        logger.warning('Douyin QR confirmation lacked shared session cookie; redirect=%s', bool(redirect))
                        self.update(entry, state='error', qrcode='',
                                    message='扫码已确认，但登录凭据未返回；请刷新二维码重试')
                    return
                elif state in ('2', 'scanned'):
                    self.update(entry, message='已扫码，请在手机上确认登录')
                elif state in ('4', '5', 'refused', 'expired'):
                    break
                elif state not in ('1', 'new', None):
                    self.update(entry, state='error', qrcode='', message='抖音返回未知扫码状态，请重试')
                    return
                time.sleep(2)
            self.update(entry, state='expired', qrcode='', message='二维码已过期，请刷新')
        except Exception as error:
            # Never log QR tokens, redirect URLs or cookie values.
            code = re.search(r'code=([0-9]{1,8})', str(error)) if isinstance(error, ValueError) else None
            logger.warning('Douyin QR login failed stage=%s error=%s code=%s',
                           stage, type(error).__name__, code.group(1) if code else 'unknown')
            self.update(entry, state='error', qrcode='',
                        message='抖音登录验证失败，请刷新二维码重试')
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                self.slots.release()

    def run(self, entry):
        return self.run_http(entry)


def add_routes(app):
    accounts = Accounts()
    app.extensions['douyin_accounts'] = accounts

    @app.before_request
    def douyin_auth_guard():
        if request.path.startswith('/api/douyin/auth') and request.method in ('POST', 'DELETE'):
            if request.headers.get('X-Requested-With') != 'Douyin':
                return json_fail('invalid_request', message='请从抖音应用操作登录'), 403

    @app.after_request
    def douyin_auth_no_store(response):
        if request.path.startswith('/api/douyin/auth'):
            response.headers['Cache-Control'] = 'private, no-store'
        return response

    @app.route('/api/douyin/auth', methods=['GET', 'DELETE'])
    @login_check
    def douyin_auth_status():
        with accounts.lock:
            entry = accounts.entry()
            if request.method == 'DELETE':
                if entry: entry['cancel'].set()
                accounts.entries.pop(session.pop('douyin_account', None), None)
                entry = None
            return json_ok({'loggedIn': bool(entry and entry.get('cookies'))})

    @app.route('/api/douyin/auth/qrcode', methods=['POST'])
    @login_check
    def douyin_auth_start():
        with accounts.lock:
            old = accounts.entry()
            if old and old.get('cookies'):
                return json_ok({'state': 'confirmed'})
            if not accounts.slots.acquire(blocking=False):
                return json_fail('busy', message='登录服务正在忙，请稍后重试'), 503
            if old: old['cancel'].set()
            accounts.entries.pop(session.get('douyin_account'), None)
            key = secrets.token_urlsafe(32)
            entry = {'state': 'loading', 'qrcode': '', 'message': '正在生成二维码…',
                     'expires': time.time() + 180, 'touched': time.time(), 'cancel': threading.Event()}
            accounts.entries[key] = entry
            session['douyin_account'] = key
            threading.Thread(target=accounts.run, args=(entry,), daemon=True).start()
            return json_ok({'state': 'loading'})

    @app.route('/api/douyin/auth/qrcode', methods=['GET', 'DELETE'])
    @login_check
    def douyin_auth_poll():
        with accounts.lock:
            entry = accounts.entry()
            if not entry:
                return json_ok({'state': 'expired', 'message': '二维码已过期，请刷新'})
            if request.method == 'DELETE':
                if not entry.get('cookies'):
                    entry['cancel'].set()
                    accounts.entries.pop(session.pop('douyin_account', None), None)
                return json_ok({})
            entry['touched'] = time.time()
            return json_ok({k: entry[k] for k in ('state', 'qrcode', 'message')})
    return accounts
