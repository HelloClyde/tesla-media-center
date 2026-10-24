"""Application-wide API authentication, request origin checks and login throttling."""
from collections import OrderedDict, deque
import math
import threading
import time
from urllib.parse import urlsplit

from flask import request, session
from ffvideo.utils import json_fail


class LoginThrottle:
    def __init__(self, limit=10, window=60, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.attempts = OrderedDict()
        self.lock = threading.Lock()

    def _recent(self, key):
        attempts = self.attempts.get(key, deque())
        cutoff = self.clock() - self.window
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts

    def retry_after(self, key):
        with self.lock:
            attempts = self._recent(key)
            return max(1, math.ceil(attempts[0] + self.window - self.clock())) if len(attempts) >= self.limit else 0

    def failed(self, key):
        with self.lock:
            attempts = self._recent(key)
            attempts.append(self.clock())
            self.attempts[key] = attempts
            self.attempts.move_to_end(key)
            while len(self.attempts) > 4096:
                self.attempts.popitem(last=False)

    def clear(self, key):
        with self.lock:
            self.attempts.pop(key, None)


def _origin(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)
    except ValueError:
        return None


def install_security(app):
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      MAX_CONTENT_LENGTH=40 * 1024 * 1024, MAX_FORM_MEMORY_SIZE=64 * 1024,
                      MAX_FORM_PARTS=10)
    app.extensions['login_throttle'] = LoginThrottle()

    @app.before_request
    def protect_api():
        if not request.path.startswith('/api/'):
            return None
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return json_fail('forbidden_origin', message='仅允许从 TMC 页面访问'), 403
        origin = request.headers.get('Origin')
        if origin:
            source, target = _origin(origin), _origin(request.host_url)
            # HTTPS is terminated by the reverse proxy. Its forwarded scheme
            # can only upgrade the matching host's default port, never its host.
            if (source and target and source[0] == 'https' and target[0] == 'http'
                    and source[1] == target[1] and source[2] == 443 and target[2] == 80
                    and request.headers.get('X-Forwarded-Proto') == 'https'):
                target = ('https', target[1], 443)
            loopback = {'localhost', '127.0.0.1', '::1'}
            # Vite changes Host when proxying to Flask; permit only the known
            # local development port, not arbitrary websites on other ports.
            development = (source and target and source[1] in loopback and target[1] in loopback
                           and source[0] == target[0] == 'http' and source[2] == 3000)
            if not source or not (source == target or development):
                return json_fail('forbidden_origin', message='仅允许从 TMC 页面访问'), 403
        if request.endpoint != 'login' and 'last_visit' not in session:
            return json_fail('need_login'), 401
        return None

    @app.after_request
    def protect_response(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
        return response
