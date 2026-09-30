"""Temporary, session-isolated login through the official Douyin QR panel."""
import base64
import copy
import os
import secrets
import threading
import time

from flask import request, session
from ffvideo.utils import login_check, json_ok, json_fail
from ffvideo.douyin_browser import allowed_media


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

    def run(self, entry):
        try:
            from playwright.sync_api import sync_playwright, TimeoutError
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel=os.environ.get('TMC_DOUYIN_BROWSER_CHANNEL', 'chromium'), headless=True)
                try:
                    context = browser.new_context(viewport={'width': 1280, 'height': 800}, locale='zh-CN', service_workers='block')
                    context.route('**/*', lambda route: route.abort() if route.request.resource_type == 'media' or allowed_media(route.request.url) else route.continue_())
                    page = context.new_page()
                    page.goto('https://www.douyin.com/jingxuan', wait_until='domcontentloaded', timeout=30000)
                    qr = page.locator('#douyin_login_comp_scan_code img[src^="data:image/"]').first
                    if not qr.is_visible():
                        try:
                            page.get_by_role('button', name='登录', exact=True).click(timeout=10000)
                        except TimeoutError:
                            # The official page can open its panel while the click waits.
                            if not qr.is_visible():
                                raise
                    qr.wait_for(state='visible', timeout=30000)
                    image = 'data:image/png;base64,' + base64.b64encode(qr.screenshot(timeout=10000)).decode()
                    self.update(entry, state='waiting', qrcode=image, message='请使用抖音 App 扫码，并在手机上确认登录')
                    while not entry['cancel'].is_set() and time.time() < entry['expires']:
                        if time.time() - entry['touched'] > 45:
                            break
                        cookies = [c for c in context.cookies() if c['domain'].lstrip('.') in ('douyin.com', 'www.douyin.com')]
                        if any(c['name'] == 'sessionid' and c['value'] for c in cookies):
                            self.update(entry, cookies=cookies, state='confirmed', qrcode='', message='已登录', expires=time.time() + 86400)
                            return
                        if page.locator('iframe[src*="/verifycenter/captcha/"]').count():
                            self.update(entry, state='error', qrcode='', message='抖音要求额外安全验证，请稍后重新扫码')
                            return
                        if page.get_by_text('二维码已失效', exact=False).count() or page.get_by_text('二维码已过期', exact=False).count():
                            break
                        page.wait_for_timeout(1000)
                    self.update(entry, state='expired', qrcode='', message='二维码已过期，请刷新')
                finally:
                    browser.close()
        except Exception:
            # Browser errors can include URLs/tokens; never expose them to clients.
            self.update(entry, state='error', qrcode='', message='官方登录页面加载失败，请重试；如持续失败，请检查服务端浏览器组件')
        finally:
            self.slots.release()


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
