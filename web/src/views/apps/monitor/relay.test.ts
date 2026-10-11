import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AUDIO, VIDEO, MonitorConnection, mediaPacket } from './relay';

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 1; bufferedAmount = 0; send = vi.fn(); close = vi.fn();
  onmessage?: (event: {data: unknown}) => void; onclose?: (event: {code: number; reason: string}) => void;
  constructor(public url: string, public protocols: string[]) { Socket.instances.push(this); }
  ready() { this.onmessage?.({data: JSON.stringify({type: 'ready', peerId: 'owner'})}); }
}
beforeEach(() => {
  vi.useFakeTimers(); Socket.instances = []; vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ({status: 'ok', data: {ticket: 'private-ticket'}})})));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
function client() {
  const hooks = {status: vi.fn(), control: vi.fn(), media: vi.fn(), fatal: vi.fn()};
  return {connection: new MonitorConnection({role: 'viewer', deviceId: 'test-vehicle-0001'}, hooks), hooks};
}
it('authenticates in the protocol header and does not expose tickets in the URL', async () => {
  const {connection, hooks} = client(); const started = connection.start(); await vi.advanceTimersByTimeAsync(0);
  const ws = Socket.instances[0];
  expect(ws.url).toContain('/api/monitor/stream'); expect(ws.url).not.toContain('private-ticket');
  expect(ws.protocols).toEqual(['tmc-monitor-v1', 'ticket.private-ticket']);
  ws.ready(); await started; expect(connection.phase).toBe('connected');
  ws.onmessage?.({data: mediaPacket(AUDIO, 1, new Uint8Array(1280))});
  expect(hooks.media).toHaveBeenCalledWith(AUDIO, expect.any(Uint8Array));
  connection.stop(); expect(ws.close).toHaveBeenCalled();
});
it('drops media under congestion rather than queueing delayed frames', async () => {
  const {connection} = client(); const started = connection.start(); await vi.advanceTimersByTimeAsync(0);
  const ws = Socket.instances[0]; ws.ready(); await started;
  expect(connection.sendMedia(VIDEO, new Uint8Array(20))).toBe(true);
  ws.bufferedAmount = 100 * 1024;
  expect(connection.sendMedia(VIDEO, new Uint8Array(20))).toBe(false);
  expect(connection.sendMedia(AUDIO, new Uint8Array(1280))).toBe(false);
  expect(ws.send).toHaveBeenCalledTimes(1);
  ws.bufferedAmount = 0;
  expect(connection.sendMedia(VIDEO, new Uint8Array(256 * 1024))).toBe(false);
  connection.stop();
});
it('does not open a socket when stopped during ticket acquisition', async () => {
  let finish!: (value: unknown) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve; })));
  const {connection} = client(); const started = connection.start().catch(error => error);
  connection.stop(); finish({ok: true, json: async () => ({status: 'ok', data: {ticket: 'late'}})});
  expect((await started).message).toContain('取消'); expect(Socket.instances).toHaveLength(0);
});
it('reconnects after loss, but stops permanently when authorization is revoked', async () => {
  const {connection, hooks} = client(); const started = connection.start(); await vi.advanceTimersByTimeAsync(0);
  const first = Socket.instances[0]; first.ready(); await started;
  first.onclose?.({code: 1006, reason: ''}); expect(connection.phase).toBe('reconnecting');
  await vi.advanceTimersByTimeAsync(1000); const second = Socket.instances[1]; second.ready();
  await vi.advanceTimersByTimeAsync(0); expect(connection.phase).toBe('connected');
  second.onclose?.({code: 1008, reason: 'TMC 已登出'});
  expect(hooks.fatal).toHaveBeenCalledWith('TMC 已登出');
  await vi.advanceTimersByTimeAsync(20000); expect(Socket.instances).toHaveLength(2);
});
