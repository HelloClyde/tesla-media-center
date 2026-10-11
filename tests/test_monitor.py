import json
import struct
import threading
import time
import unittest
from unittest.mock import patch

import requests
from flask import Flask, session
from simple_websocket import Client
from werkzeug.serving import make_server

from ffvideo.monitor import AUDIO, VIDEO, MonitorRelay, Outbox, RelayError, add_routes

DEVICE = 'test-vehicle-0001'
JPEG = b'\xff\xd8example\xff\xd9'


def packet(kind, data=None, sequence=1):
    return struct.pack('<BII', kind, sequence, 16000 if kind == AUDIO else 0) + (data if data is not None else b'\x01\x00' * 640)


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.broker = MonitorRelay()
        self.app = Flask(__name__)
        self.app.secret_key = 'monitor-test-only'
        add_routes(self.app, self.broker)
        self.client = self.app.test_client()

    def login(self):
        with self.client.session_transaction() as signed_session:
            signed_session['last_visit'] = 1

    def connect(self, role, owner, device=DEVICE):
        data = {'role': role, 'deviceId': device, 'name': '测试车辆', 'video': True, 'audio': True}
        return self.broker.attach(self.broker.consume(self.broker.issue(owner, data), owner))

    def test_auth_origin_and_ticket_bound_to_browser_and_consumed_once(self):
        self.assertEqual(self.client.get('/api/monitor/devices').status_code, 401)
        self.assertEqual(self.client.post('/api/monitor/ticket', json={}).status_code, 401)
        self.login()
        data = {'role': 'publisher', 'deviceId': DEVICE, 'name': '测试', 'video': True, 'audio': True}
        self.assertEqual(self.client.post('/api/monitor/ticket', json=data, headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/monitor/ticket', json=data, headers={'Origin': 'http://localhost:9090', 'Sec-Fetch-Site': 'same-site'}).status_code, 403)
        response = self.client.post('/api/monitor/ticket', json=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with self.client.session_transaction() as signed_session:
            owner = signed_session['monitor_client']
        token = response.json['data']['ticket']
        with self.assertRaises(RelayError):
            self.broker.consume(token, 'another-browser')
        self.assertEqual(self.broker.consume(token, owner)['role'], 'publisher')
        with self.assertRaises(RelayError):
            self.broker.consume(token, owner)
        token = self.broker.issue(owner, data)
        with patch('ffvideo.monitor.time.monotonic', return_value=time.monotonic() + 46):
            with self.assertRaises(RelayError):
                self.broker.consume(token, owner)

    def test_invalid_metadata_and_non_json_requests(self):
        self.login()
        data = {'role': 'publisher', 'deviceId': DEVICE, 'name': '车机', 'video': True, 'audio': True}
        for invalid in [[], None, {**data, 'deviceId': '../private'}, {**data, 'name': None},
                        {**data, 'name': 'x' * 41}, {**data, 'audio': 'true'}, {**data, 'video': False, 'audio': False}]:
            response = self.client.post('/api/monitor/ticket', data=json.dumps(invalid), content_type='application/json')
            self.assertIn(response.status_code, (400, 409))
        self.assertEqual(self.client.post('/api/monitor/ticket', data=json.dumps(data), content_type='text/plain').status_code, 400)
        self.assertEqual(self.client.post('/api/monitor/ticket', json={**data, 'padding': 'x' * 3000}).status_code, 400)

    def test_video_audio_routing_and_exclusive_return_talk(self):
        car = self.connect('publisher', 'car')
        owner = self.connect('viewer', 'owner')
        other = self.connect('viewer', 'other')
        video, sound = packet(VIDEO, JPEG), packet(AUDIO)
        self.broker.media(car, video)
        self.broker.media(car, sound)
        for peer in [owner, other]:
            self.assertEqual(peer.outbox.video, video)
            self.assertEqual(list(peer.outbox.audio), [sound])
        self.assertFalse(car.outbox.audio)
        self.broker.media(owner, sound)
        self.assertFalse(car.outbox.audio)
        self.broker.control(owner, {'type': 'talk_start'})
        self.broker.control(other, {'type': 'talk_start'})
        self.assertEqual(json.loads(other.outbox.controls[-1])['type'], 'talk_denied')
        self.broker.media(other, sound)
        self.assertFalse(car.outbox.audio)
        self.broker.media(owner, sound)
        self.assertEqual(list(car.outbox.audio), [sound])
        self.broker.detach(owner)
        self.assertIsNone(self.broker.devices[DEVICE].talker)
        self.broker.control(other, {'type': 'talk_start'})
        self.assertIs(self.broker.devices[DEVICE].talker, other)
        self.broker.control(other, {'type': 'talk_stop'})
        self.assertIsNone(self.broker.devices[DEVICE].talker)

    def test_devices_are_isolated_and_disconnect_recovers_without_old_frame(self):
        car = self.connect('publisher', 'car')
        owner = self.connect('viewer', 'owner')
        second_car = self.connect('publisher', 'second', 'test-vehicle-0002')
        second_owner = self.connect('viewer', 'second-owner', 'test-vehicle-0002')
        self.broker.media(car, packet(VIDEO, JPEG))
        self.assertIsNone(second_owner.outbox.video)
        self.broker.detach(car)
        self.assertIsNone(self.broker.devices[DEVICE].last_frame)
        self.assertFalse(json.loads(owner.outbox.controls[-1])['device']['online'])
        recovered = self.connect('publisher', 'car')
        self.assertTrue(json.loads(owner.outbox.controls[-1])['device']['online'])
        self.broker.media(recovered, packet(AUDIO))
        self.assertTrue(owner.outbox.audio)
        self.broker.detach(recovered, ended=True)
        self.assertTrue(json.loads(owner.outbox.controls[-1])['ended'])
        self.broker.detach(owner)
        self.assertNotIn(DEVICE, self.broker.devices)
        self.assertIs(self.broker.devices[second_car.device_id].publisher, second_car)

    def test_logout_revokes_only_matching_browser_and_pending_tickets(self):
        car = self.connect('publisher', 'car')
        owner = self.connect('viewer', 'owner')
        self.broker.control(owner, {'type': 'talk_start'})
        token = self.broker.issue('owner', {'role': 'viewer', 'deviceId': DEVICE})
        self.broker.revoke('owner')
        self.assertTrue(owner.outbox.closed)
        self.assertIs(self.broker.devices[DEVICE].publisher, car)
        self.assertIsNone(self.broker.devices[DEVICE].talker)
        with self.assertRaises(RelayError):
            self.broker.consume(token, 'owner')

    def test_queue_is_bounded_and_new_viewers_receive_latest_video(self):
        outbox = Outbox()
        for sequence in range(100):
            outbox.put(packet(VIDEO, JPEG, sequence))
            outbox.put(packet(AUDIO, sequence=sequence))
        self.assertEqual(len(outbox.audio), 4)
        self.assertEqual(struct.unpack_from('<I', outbox.video, 1)[0], 99)
        outbox.close()
        self.assertIsNone(outbox.get())
        car = self.connect('publisher', 'car')
        frame = packet(VIDEO, JPEG)
        self.broker.media(car, frame)
        owner = self.connect('viewer', 'owner')
        self.assertEqual(owner.outbox.video, frame)

    def test_malformed_media_viewer_video_and_capacity_are_rejected(self):
        car = self.connect('publisher', 'car')
        owner = self.connect('viewer', 'owner')
        for data in [b'', packet(VIDEO, b'not-jpeg'), packet(AUDIO, b'short'), packet(3), b'x' * (256 * 1024 + 1)]:
            with self.assertRaises(RelayError):
                self.broker.media(car, data)
        with self.assertRaises(RelayError):
            self.broker.media(owner, packet(VIDEO, JPEG))
        for index in range(3):
            self.connect('viewer', f'owner-{index}')
        with self.assertRaises(RelayError):
            self.connect('viewer', 'overflow')
        with self.assertRaises(RelayError):
            self.connect('publisher', 'duplicate')

    def test_real_websocket_relay_handshake_binary_and_return_audio(self):
        @self.app.post('/test/login')
        def login():
            session['last_visit'] = 1
            return '{}'

        server = make_server('127.0.0.1', 0, self.app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        sockets = []
        try:
            def connect(role):
                client = requests.Session()
                client.post(base + '/test/login', timeout=3).raise_for_status()
                data = {'role': role, 'deviceId': DEVICE, 'name': '车机', 'audio': True, 'video': True}
                token = client.post(base + '/api/monitor/ticket', json=data, timeout=3).json()['data']['ticket']
                cookie = '; '.join(f'{key}={value}' for key, value in client.cookies.items())
                ws = Client.connect(base.replace('http:', 'ws:') + '/api/monitor/stream',
                                    subprotocols=['tmc-monitor-v1', 'ticket.' + token],
                                    headers={'Cookie': cookie, 'Origin': base})
                sockets.append(ws)
                self.assertEqual(json.loads(ws.receive(timeout=2))['type'], 'ready')
                return ws

            def receive(ws, wanted):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    data = ws.receive(timeout=.2)
                    if data is not None and wanted(data):
                        return data
                self.fail('WebSocket relay did not deliver the expected message')

            car, owner = connect('publisher'), connect('viewer')
            frame, sound = packet(VIDEO, JPEG), packet(AUDIO)
            car.send(frame)
            self.assertEqual(receive(owner, lambda data: isinstance(data, bytes)), frame)
            car.send(sound)
            self.assertEqual(receive(owner, lambda data: isinstance(data, bytes)), sound)
            owner.send(json.dumps({'type': 'talk_start'}))
            receive(owner, lambda data: isinstance(data, str) and json.loads(data)['type'] == 'talk_granted')
            owner.send(sound)
            self.assertEqual(receive(car, lambda data: isinstance(data, bytes)), sound)
            car.send(json.dumps({'type': 'stop'}))
            receive(owner, lambda data: isinstance(data, str) and json.loads(data).get('ended'))
        finally:
            for ws in sockets:
                try:
                    ws.close()
                except Exception:
                    pass
            server.shutdown(); server.server_close()
