"""Live browser camera/audio relay. No recordings or media files are created."""
import json
import re
import secrets
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from flask import g, jsonify, request, session
from flask_sock import Sock
from simple_websocket import ConnectionClosed

VIDEO, AUDIO = 1, 2
SAMPLE_RATE, AUDIO_SAMPLES = 16000, 640
MAX_MESSAGE = 256 * 1024
MAX_DEVICES, MAX_VIEWERS = 8, 4
DEVICE_ID = re.compile(r'^[a-zA-Z0-9_-]{12,64}$')


class RelayError(Exception):
    pass


class Outbox:
    """A slow browser cannot delay other clients or accumulate old footage."""
    def __init__(self):
        self.condition = threading.Condition()
        self.controls = deque(maxlen=16)
        self.audio = deque(maxlen=4)
        self.video = None
        self.closed = False

    def put(self, message):
        with self.condition:
            if self.closed:
                return
            if isinstance(message, dict):
                self.controls.append(json.dumps(message, ensure_ascii=False))
            elif message[0] == AUDIO:
                self.audio.append(message)
            else:
                self.video = message
            self.condition.notify()

    def get(self):
        with self.condition:
            self.condition.wait_for(lambda: self.closed or self.controls or self.audio or self.video is not None)
            if self.closed:
                return None
            if self.controls:
                return self.controls.popleft()
            if self.audio:
                return self.audio.popleft()
            message, self.video = self.video, None
            return message

    def close(self):
        with self.condition:
            self.closed = True
            self.controls.clear()
            self.audio.clear()
            self.video = None
            self.condition.notify_all()


@dataclass(eq=False)
class Peer:
    owner: str
    role: str
    device_id: str
    ws: object = None
    id: str = field(default_factory=lambda: secrets.token_hex(12))
    outbox: Outbox = field(default_factory=Outbox)
    budget: float = 2 * 1024 * 1024
    budget_at: float = field(default_factory=time.monotonic)
    video_at: float = 0


@dataclass
class Device:
    id: str
    name: str
    video: bool
    audio: bool
    publisher: Peer | None = None
    viewers: dict = field(default_factory=dict)
    talker: Peer | None = None
    last_frame: bytes | None = None
    offline_at: float = 0
    started_at: float = field(default_factory=time.time)

    def status(self):
        return {'id': self.id, 'name': self.name, 'video': self.video, 'audio': self.audio,
                'online': self.publisher is not None, 'viewers': len(self.viewers),
                'talking': self.talker is not None, 'talkerId': self.talker.id if self.talker else None,
                'startedAt': int(self.started_at * 1000)}


class MonitorRelay:
    def __init__(self):
        self.lock = threading.RLock()
        self.devices = {}
        self.tickets = {}

    def issue(self, owner, data):
        role, device_id = data.get('role'), data.get('deviceId')
        if role not in ('publisher', 'viewer') or not isinstance(device_id, str) or not DEVICE_ID.fullmatch(device_id):
            raise RelayError('无效的监控设备')
        with self.lock:
            now = time.monotonic()
            self.tickets = {key: value for key, value in self.tickets.items() if value['expires'] > now}
            device = self.devices.get(device_id)
            if role == 'viewer' and (not device or not device.publisher):
                raise RelayError('车机尚未开启监控，或已离线')
            if role == 'publisher':
                if device and device.publisher:
                    raise RelayError('此设备已在监控，请先停止原连接')
                if not device and len(self.devices) >= MAX_DEVICES:
                    raise RelayError('在线监控设备已达到上限')
                if not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 40:
                    raise RelayError('设备名称须为 1–40 个字')
                if not isinstance(data.get('video'), bool) or not isinstance(data.get('audio'), bool) or not (data['video'] or data['audio']):
                    raise RelayError('请至少启用摄像头或麦克风')
            if role == 'viewer' and len(device.viewers) >= MAX_VIEWERS:
                raise RelayError('此设备的观看人数已达到上限')
            if len(self.tickets) >= 64:
                raise RelayError('连接请求过多，请稍后重试')
            token = secrets.token_urlsafe(32)
            self.tickets[token] = {'owner': owner, 'role': role, 'deviceId': device_id,
                                   'name': data['name'].strip() if role == 'publisher' else '', 'video': data.get('video'),
                                   'audio': data.get('audio'), 'expires': now + 45}
            return token

    def consume(self, token, owner):
        with self.lock:
            ticket = self.tickets.get(token)
            if not ticket or ticket['owner'] != owner or ticket['expires'] <= time.monotonic():
                raise RelayError('监控连接授权已失效，请重新连接')
            del self.tickets[token]
            return ticket

    def attach(self, ticket, ws=None):
        with self.lock:
            device_id, role = ticket['deviceId'], ticket['role']
            device = self.devices.get(device_id)
            if role == 'publisher':
                if device and device.publisher:
                    raise RelayError('设备已在监控')
                if not device:
                    if len(self.devices) >= MAX_DEVICES:
                        raise RelayError('在线设备已达到上限')
                    device = Device(device_id, ticket['name'], ticket['video'], ticket['audio'])
                    self.devices[device_id] = device
                device.name, device.video, device.audio = ticket['name'], ticket['video'], ticket['audio']
            elif not device or not device.publisher or len(device.viewers) >= MAX_VIEWERS:
                raise RelayError('设备不可连接，请刷新设备列表')
            peer = Peer(ticket['owner'], role, device_id, ws)
            if role == 'publisher':
                device.publisher = peer
                device.offline_at = 0
            else:
                device.viewers[peer.id] = peer
            peer.outbox.put({'type': 'ready', 'peerId': peer.id, 'role': role, 'device': device.status()})
            if role == 'viewer' and device.last_frame:
                peer.outbox.put(device.last_frame)
            self._status(device)
            return peer

    def _status(self, device, ended=False):
        message = {'type': 'state', 'device': device.status(), 'ended': ended}
        for peer in ([device.publisher] if device.publisher else []) + list(device.viewers.values()):
            peer.outbox.put(message)

    def detach(self, peer, ended=False):
        with self.lock:
            device = self.devices.get(peer.device_id)
            if not device:
                return
            if device.publisher is peer:
                device.publisher = None
                device.last_frame = None
                device.offline_at = time.monotonic()
                device.talker = None
            elif device.viewers.get(peer.id) is peer:
                del device.viewers[peer.id]
                if device.talker is peer:
                    device.talker = None
            else:
                return
            self._status(device, ended)
            if not device.publisher and not device.viewers:
                del self.devices[device.id]
            peer.outbox.close()

    def control(self, peer, message):
        with self.lock:
            device = self.devices.get(peer.device_id)
            if not device:
                raise RelayError('设备已离线')
            kind = message.get('type')
            if kind == 'ping':
                peer.outbox.put({'type': 'pong'})
            elif kind == 'talk_start' and peer.role == 'viewer':
                if not device.publisher:
                    peer.outbox.put({'type': 'talk_denied', 'message': '车机已离线'})
                elif device.talker and device.talker is not peer:
                    peer.outbox.put({'type': 'talk_denied', 'message': '其他车主正在对讲'})
                else:
                    device.talker = peer
                    peer.outbox.put({'type': 'talk_granted'})
                    self._status(device)
            elif kind == 'talk_stop' and peer.role == 'viewer':
                if device.talker is peer:
                    device.talker = None
                    self._status(device)
            elif kind != 'stop':
                raise RelayError('无效的监控消息')

    def media(self, peer, packet):
        if len(packet) < 9 or len(packet) > MAX_MESSAGE:
            raise RelayError('无效的音视频数据')
        kind, _, rate = struct.unpack_from('<BII', packet)
        if kind == VIDEO:
            if peer.role != 'publisher' or rate != 0 or packet[9:11] != b'\xff\xd8' or packet[-2:] != b'\xff\xd9':
                raise RelayError('无效的视频帧')
        elif kind != AUDIO or rate != SAMPLE_RATE or len(packet) != 9 + AUDIO_SAMPLES * 2:
            raise RelayError('无效的音频帧')
        now = time.monotonic()
        rate_limit = 1024 * 1024 if peer.role == 'publisher' else 64 * 1024
        peer.budget = min(rate_limit * 2, peer.budget + (now - peer.budget_at) * rate_limit)
        peer.budget_at = now
        if peer.budget < len(packet):
            raise RelayError('音视频发送速率过高')
        peer.budget -= len(packet)
        with self.lock:
            device = self.devices.get(peer.device_id)
            if not device:
                return
            if peer.role == 'publisher':
                if device.publisher is not peer:
                    return
                if kind == VIDEO:
                    if not device.video:
                        return
                    if now - peer.video_at < 1 / 15:
                        return
                    peer.video_at = now
                    device.last_frame = packet
                elif not device.audio:
                    return
                for viewer in device.viewers.values():
                    viewer.outbox.put(packet)
            elif device.talker is peer and device.publisher:
                device.publisher.outbox.put(packet)

    def list_devices(self):
        with self.lock:
            return [device.status() for device in self.devices.values() if device.publisher]

    def expired(self, peer):
        with self.lock:
            device = self.devices.get(peer.device_id)
            return not device or not device.publisher and time.monotonic() - device.offline_at > 60

    def revoke(self, owner):
        if not owner:
            return
        with self.lock:
            self.tickets = {key: value for key, value in self.tickets.items() if value['owner'] != owner}
            peers = [peer for device in self.devices.values()
                     for peer in ([device.publisher] if device.publisher else []) + list(device.viewers.values())
                     if peer.owner == owner]
            for peer in peers:
                self.detach(peer, ended=peer.role == 'publisher')
                if peer.ws:
                    try:
                        peer.ws.close(reason=1008, message='TMC 已登出')
                    except ConnectionClosed:
                        pass


relay = MonitorRelay()


def add_routes(app, broker=None):
    broker = broker or relay
    app.config['SOCK_SERVER_OPTIONS'] = {'ping_interval': 20, 'max_message_size': MAX_MESSAGE,
                                        'subprotocols': ['tmc-monitor-v1']}
    sock = Sock(app)

    def result(data=None, message='', code=200, status='ok'):
        response = jsonify(status=status, data=data, message=message)
        response.headers['Cache-Control'] = 'no-store'
        return response, code

    @app.before_request
    def protect_monitor():
        if not request.path.startswith('/api/monitor/'):
            return None
        if 'last_visit' not in session:
            return result(message='请先登录 TMC', code=401, status='need_login')
        if request.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
            return result(message='监控仅允许从 TMC 页面连接', code=403, status='fail')
        origin = request.headers.get('Origin')
        if origin:
            source, target = urlsplit(origin).hostname, urlsplit(request.host_url).hostname
            loopback = {'localhost', '127.0.0.1', '::1'}
            if not source or not (source == target or source in loopback and target in loopback):
                return result(message='监控仅允许从 TMC 页面连接', code=403, status='fail')
        if request.path == '/api/monitor/stream':
            protocols = [value.strip() for value in request.headers.get('Sec-WebSocket-Protocol', '').split(',')]
            token = next((value[7:] for value in protocols if value.startswith('ticket.')), '')
            try:
                if 'tmc-monitor-v1' not in protocols:
                    raise RelayError('无效的监控协议')
                g.monitor_ticket = broker.consume(token, session.get('monitor_client'))
            except RelayError as error:
                return result(message=str(error), code=403, status='fail')

    @app.get('/api/monitor/devices')
    def monitor_devices():
        return result({'devices': broker.list_devices(), 'maxViewers': MAX_VIEWERS})

    @app.post('/api/monitor/ticket')
    def monitor_ticket():
        if not request.is_json or request.content_length is None or request.content_length > 2048:
            return result(message='无效的连接请求', code=400, status='fail')
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return result(message='无效的连接请求', code=400, status='fail')
        if 'monitor_client' not in session:
            session['monitor_client'] = secrets.token_hex(24)
        try:
            return result({'ticket': broker.issue(session['monitor_client'], data)})
        except RelayError as error:
            return result(message=str(error), code=409, status='fail')

    @sock.route('/api/monitor/stream')
    def monitor_stream(ws):
        peer, sender, ended = None, None, False
        try:
            peer = broker.attach(g.monitor_ticket, ws)

            def send_loop():
                try:
                    while (message := peer.outbox.get()) is not None:
                        ws.send(message)
                except (ConnectionClosed, OSError):
                    try:
                        ws.close()
                    except (ConnectionClosed, OSError):
                        pass

            sender = threading.Thread(target=send_loop, name='tmc-monitor-send', daemon=True)
            sender.start()
            last_seen = time.monotonic()
            while True:
                if peer.outbox.closed or broker.expired(peer):
                    break
                message = ws.receive(timeout=1)
                if message is None:
                    if peer.outbox.closed or time.monotonic() - last_seen > 35:
                        break
                    continue
                last_seen = time.monotonic()
                if isinstance(message, bytes):
                    broker.media(peer, message)
                else:
                    if len(message) > 512:
                        raise RelayError('监控控制消息过长')
                    try:
                        control = json.loads(message)
                    except ValueError:
                        raise RelayError('无效的监控消息')
                    if not isinstance(control, dict):
                        raise RelayError('无效的监控消息')
                    if control.get('type') == 'stop':
                        ended = peer.role == 'publisher'
                        break
                    broker.control(peer, control)
        except RelayError as error:
            ws.close(reason=1008, message=str(error))
        except (ConnectionClosed, OSError):
            pass
        finally:
            if peer:
                broker.detach(peer, ended)
                peer.outbox.close()
            try:
                ws.close()
            except (ConnectionClosed, OSError):
                pass
            if sender:
                sender.join(timeout=1)
