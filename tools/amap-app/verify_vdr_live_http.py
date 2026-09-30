"""Opt-in Node/jsdom -> loopback HTTP -> actual translated VDR verification.

Uses synthetic motion/profile and actual APK coefficients, not a vehicle/browser
hardware run. No changes to the production server or its stored configuration.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flask import Flask
from werkzeug.serving import make_server, WSGIRequestHandler
from ffvideo.amap_inertial import add_amap_inertial_routes
from ffvideo.amap_inertial_runtime import configure_inertial_runtime


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def verify(apk, node):
    root = Path(__file__).resolve().parents[2]
    profile = dict(schema='tmc-vdr-profile-v1', apk=str(Path(apk).resolve()), registry141=0,
        installation=dict(rotation=[[1,0,0],[0,1,0],[0,0,1]], acceleration_sign=1,
                          accuracy_to_sigma=1, maximum_gap=80),
        recovery_variance='native-constructor',
        observation_flags=dict(flag1=False, flag2=False))
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'synthetic-profile.json'
        path.write_text(json.dumps(profile), encoding='utf-8')
        app.config['AMAP_VDR_PROFILE'] = str(path)
        configure_inertial_runtime(app)
    if not callable(app.config.get('AMAP_VDR_FACTORY')):
        raise RuntimeError('Experimental runtime failed to load')
    add_amap_inertial_routes(app)
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = os.environ.copy()
    environment['TMC_VDR_TEST_URL'] = f'http://127.0.0.1:{server.server_port}'
    cookie = app.session_interface.get_signing_serializer(app).dumps({'last_visit': 1})
    environment['TMC_VDR_TEST_COOKIE'] = 'session=' + cookie
    # WSL needs explicit forwarding for a Windows Node child; these are ephemeral
    # test values, never the application's real login cookie or configuration.
    environment['WSLENV'] = ':'.join(filter(None, [environment.get('WSLENV'),
        'TMC_VDR_TEST_URL', 'TMC_VDR_TEST_COOKIE']))
    try:
        completed = subprocess.run([node, 'node_modules/vitest/vitest.mjs', '--environment', 'jsdom',
            '--root', 'src/', '--run', 'functions/inertialLiveHttp.test.ts'],
            cwd=root / 'web', env=environment, timeout=90)
        return completed.returncode == 0
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('--node', required=True)
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.apk, args.node) else 1)
