export const VIDEO = 1, AUDIO = 2, SAMPLE_RATE = 16000, AUDIO_SAMPLES = 640;
export type RelayPhase = 'idle' | 'connecting' | 'connected' | 'reconnecting';
export interface MonitorDevice {
  id: string; name: string; video: boolean; audio: boolean; online: boolean;
  viewers: number; talking: boolean; talkerId: string | null; startedAt: number;
}
export interface RelayControl { type: string; device?: MonitorDevice; peerId?: string; ended?: boolean; message?: string }
interface Options {
  role: 'publisher' | 'viewer'; deviceId: string; name?: string; video?: boolean; audio?: boolean;
}
interface Hooks {
  status(phase: RelayPhase, message: string): void;
  control(message: RelayControl): void;
  media(kind: number, payload: Uint8Array): void;
  fatal(message: string): void;
}

async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/monitor/' + path, {
    method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal,
    ...(body ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {}),
  });
  let result;
  try { result = await response.json(); }
  catch { throw Error(response.status === 404 ? '服务器尚未启用监控，请更新 TMC 后端' : `监控服务响应异常（HTTP ${response.status}）`); }
  if (!response.ok || result.status !== 'ok') {
    const error = new Error(result.message || '监控服务暂时不可用') as Error & {status: number};
    error.status = response.status; throw error;
  }
  return result.data;
}
export function listMonitorDevices(signal?: AbortSignal) { return api<{devices: MonitorDevice[]}>('devices', undefined, signal); }

export function mediaPacket(kind: number, sequence: number, payload: Uint8Array) {
  const packet = new Uint8Array(9 + payload.byteLength), header = new DataView(packet.buffer);
  header.setUint8(0, kind); header.setUint32(1, sequence, true);
  header.setUint32(5, kind === AUDIO ? SAMPLE_RATE : 0, true);
  packet.set(payload, 9); return packet.buffer;
}

export class MonitorConnection {
  private ws?: WebSocket;
  private controller?: AbortController;
  private timer?: ReturnType<typeof setTimeout>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private enabled = false;
  private generation = 0;
  private sequence = 0;
  private retries = 0;
  private lastMessage = 0;
  phase: RelayPhase = 'idle';
  constructor(private options: Options, private hooks: Hooks) {}
  private status(phase: RelayPhase, text: string) { this.phase = phase; this.hooks.status(phase, text); }

  async start() {
    this.enabled = true;
    try { await this.open(); } catch (error) { this.stop(); throw error; }
  }
  private async open() {
    const generation = ++this.generation;
    this.status(this.retries ? 'reconnecting' : 'connecting', this.retries ? '连接中断，正在重连…' : '正在连接 TMC…');
    const controller = new AbortController(); this.controller = controller;
    const deadline = setTimeout(() => controller.abort(), 10000);
    let ticket: string;
    try { ({ticket} = await api<{ticket: string}>('ticket', this.options, controller.signal)); }
    finally { clearTimeout(deadline); }
    if (!this.enabled || generation !== this.generation) throw Error('连接已取消');
    const url = new URL('/api/monitor/stream', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(url.href, ['tmc-monitor-v1', 'ticket.' + ticket]);
    ws.binaryType = 'arraybuffer'; this.ws = ws;
    await new Promise<void>((resolve, reject) => {
      let ready = false;
      const timeout = setTimeout(() => { reject(Error('监控连接超时，请检查服务器 WebSocket 转发配置')); ws.close(); }, 10000);
      ws.onmessage = event => {
        if (!this.enabled || generation !== this.generation) return;
        this.lastMessage = Date.now();
        if (typeof event.data === 'string') {
          let message: RelayControl;
          try { message = JSON.parse(event.data); } catch { return; }
          if (message.type === 'ready') {
            ready = true; clearTimeout(timeout); this.retries = 0;
            this.status('connected', '已连接'); resolve();
            this.heartbeat = setInterval(() => {
              if (Date.now() - this.lastMessage > 30000 || ws.bufferedAmount > 512 * 1024) ws.close();
              else this.sendControl({type: 'ping'});
            }, 10000);
          }
          this.hooks.control(message);
        } else if (event.data instanceof ArrayBuffer && event.data.byteLength >= 9) {
          const header = new DataView(event.data), kind = header.getUint8(0);
          if (kind === VIDEO || kind === AUDIO && header.getUint32(5, true) === SAMPLE_RATE) {
            this.hooks.media(kind, new Uint8Array(event.data, 9));
          }
        }
      };
      ws.onclose = event => {
        clearTimeout(timeout);
        if (generation !== this.generation || !this.enabled) return;
        clearInterval(this.heartbeat); this.heartbeat = undefined;
        if (!ready) { reject(Error(event.reason || '监控连接失败，请检查服务器 WebSocket 转发配置')); return; }
        if (event.code === 1008) { this.stop(); this.hooks.fatal(event.reason || '监控授权已失效，请重新登录'); return; }
        this.retry();
      };
      ws.onerror = () => { if (!ready) reject(Error('监控连接失败，请检查服务器 WebSocket 转发配置')); };
    });
  }
  private retry() {
    if (!this.enabled) return;
    this.status('reconnecting', '连接中断，正在重连…');
    const delay = Math.min(15000, 1000 * 2 ** Math.min(this.retries++, 4));
    this.timer = setTimeout(async () => {
      try { await this.open(); }
      catch (error) {
        if (!this.enabled) return;
        if ((error as {status?: number}).status === 401 || (error as {status?: number}).status === 403) {
          this.stop(); this.hooks.fatal((error as Error).message);
        } else this.retry();
      }
    }, delay);
  }
  sendControl(message: {type: string}) {
    if (this.ws?.readyState === WebSocket.OPEN && this.ws.bufferedAmount < 64 * 1024) this.ws.send(JSON.stringify(message));
  }
  sendMedia(kind: number, payload: Uint8Array) {
    if (this.phase !== 'connected' || this.ws?.readyState !== WebSocket.OPEN) return false;
    // Old video/audio are discarded before sending, rather than building up delay.
    if (this.ws.bufferedAmount > (kind === VIDEO ? 96 : 48) * 1024) return false;
    if (payload.byteLength + 9 > 256 * 1024) return false;
    this.ws.send(mediaPacket(kind, this.sequence++ >>> 0, payload)); return true;
  }
  stop() {
    this.enabled = false; ++this.generation;
    clearTimeout(this.timer); clearInterval(this.heartbeat); this.controller?.abort();
    if (this.ws?.readyState === WebSocket.OPEN) this.sendControl({type: 'stop'});
    this.ws?.close(); this.ws = undefined;
    this.status('idle', '未连接');
  }
}
