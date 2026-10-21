"""Web QR login retaining cookies from both passport response formats."""
import base64
import io
from urllib.parse import parse_qs, urljoin, urlsplit

from bilibili_api import Credential, HEADERS
import qrcode
import requests

PASSPORT = 'https://passport.bilibili.com/x/passport-login/web/qrcode/'
COOKIE_FIELDS = {'SESSDATA': 'sessdata', 'bili_jct': 'bili_jct',
                 'DedeUserID': 'dedeuserid', 'buvid3': 'buvid3'}


class BilibiliAuthError(ValueError):
    pass


def _trusted_passport_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.port in (None, 443)
                and parsed.hostname in ('passport.bilibili.com', 'passport.biligame.com', 'account.bilibili.com')
                and not parsed.username and not parsed.password)
    except ValueError:
        return False


class BilibiliQrLogin:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.key = None
        self.credential = None
        self.completion = None

    def close(self):
        self.session.close()

    def _get(self, url, **kwargs):
        try:
            return self.session.get(url, timeout=(5, 15), allow_redirects=False, **kwargs)
        except requests.RequestException:
            # Requests exception strings can contain the QR key or ticket URL.
            raise BilibiliAuthError('B站登录服务暂时不可用，请稍后重试') from None

    def _data(self, response):
        if response.status_code != 200:
            raise BilibiliAuthError(f'B站登录服务返回 HTTP {response.status_code}，请稍后重试')
        try:
            result = response.json()
        except ValueError:
            raise BilibiliAuthError('B站登录服务返回了非预期结果，请稍后重试') from None
        if not isinstance(result, dict) or result.get('code') != 0 or not isinstance(result.get('data'), dict):
            raise BilibiliAuthError('B站登录请求未成功，请重新生成二维码')
        return result['data']

    def generate_qrcode(self):
        with self._get(PASSPORT + 'generate', params={'source': 'main-fe-header'}) as response:
            data = self._data(response)
        url, key = data.get('url'), data.get('qrcode_key')
        if not isinstance(url, str) or not _trusted_passport_url(url) or not isinstance(key, str) or not key:
            raise BilibiliAuthError('B站未返回有效二维码，请稍后重试')
        self.key = key
        image = io.BytesIO()
        qrcode.make(url).save(image, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode('ascii')

    def _credentials(self, data):
        url = data.get('url') or ''
        if url and not _trusted_passport_url(url):
            raise BilibiliAuthError('B站返回了非预期的登录地址，请重新扫码')
        query = parse_qs(urlsplit(url).query)
        values = {field: query[name][0] for name, field in COOKIE_FIELDS.items() if query.get(name)}

        def collect():
            for cookie in self.session.cookies:
                if cookie.name in COOKIE_FIELDS and cookie.value:
                    values[COOKIE_FIELDS[cookie.name]] = cookie.value

        def complete():
            return all(values.get(name) for name in ('sessdata', 'bili_jct', 'dedeuserid'))

        # Current poll responses can carry Set-Cookie directly. Older responses
        # put cookies in the URL; ticket responses require the crossDomain hop.
        collect()
        if not complete() and url:
            for _ in range(5):
                if not _trusted_passport_url(url):
                    raise BilibiliAuthError('B站返回了非预期的登录跳转，请重新扫码')
                with self._get(url) as response:
                    collect()
                    if complete():
                        break
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get('Location', ''))
                    elif response.status_code == 200:
                        break
                    else:
                        raise BilibiliAuthError('获取B站登录凭据失败，请重新扫码')
        if not complete():
            raise BilibiliAuthError('扫码已确认，但未获取完整登录凭据，请重新生成二维码')
        return Credential(**values, ac_time_value=data.get('refresh_token') or '')

    def check_state(self):
        if self.credential is not None:
            return 'done'
        if self.key is None:
            raise BilibiliAuthError('请先生成登录二维码')
        data = self.completion
        if data is None:
            with self._get(PASSPORT + 'poll', params={'qrcode_key': self.key, 'source': 'main-fe-header'}) as response:
                data = self._data(response)
        code = data.get('code')
        if code in (86101, 86090, 86038):
            return {86101: 'scan', 86090: 'confirm', 86038: 'timeout'}[code]
        if code != 0:
            raise BilibiliAuthError('B站未确认登录，请重新扫码')
        # A successful QR key is single-use: retain the result rather than
        # polling again if the following ticket exchange temporarily fails.
        self.completion = data
        self.credential = self._credentials(data)
        return 'done'

    def get_credential(self):
        if self.credential is None:
            raise BilibiliAuthError('B站登录尚未完成')
        return self.credential
