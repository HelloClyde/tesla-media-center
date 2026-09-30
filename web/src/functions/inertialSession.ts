/** Single-use ordered transport with explicit native/browser input negotiation. */
export type InertialSample = {
  timestamp: number; gyro: number[]; acceleration: number[];
  gps?: { timestamp: number; longitude: number; latitude: number; altitude: number;
    speed: number; direction: number; position_sigma: number };
};
export type BrowserInertialSample = {
  elapsed: number; angularVelocity: number[]; acceleration: number[];
  gps?: { elapsed: number; longitude: number; latitude: number; altitude: number;
    speed: number; heading: number | null; accuracy: number };
};
export type InertialResult = { state: number; accepted: number; timestamp: number;
  output: null | { timestamp: number; longitude: number; latitude: number; altitude: number;
    state: number; missing_fix: boolean; quality: number; source: string;
    estimated_accuracy?: number; speed?: number; heading?: number | null } };
const base = '/api/amap-app/inertial/sessions';
function validResult(value: InertialResult) {
  if (!Number.isInteger(value?.state)) return false;
  const point = value.output;
  if (point === null) return true;
  return point && [point.timestamp, point.longitude, point.latitude, point.altitude, point.quality].every(Number.isFinite)
    && Number.isInteger(point.state) && typeof point.missing_fix === 'boolean'
    && point.source === 'amap-vdr-ordinary' && point.timestamp > 0
    && Math.abs(point.longitude) <= 180 && Math.abs(point.latitude) <= 90;
}
class SessionError extends Error {
  constructor(message: string, public retryable = false) { super(message); }
}

export function createInertialSession(onResult: (result: InertialResult) => void,
  onError: (message: string) => void, request: typeof fetch = fetch,
  format: 'native' | 'browser' = 'native') {
  let id: string | undefined, started = false, stopped = false, busy = false, sequence = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const queue: (InertialSample | BrowserInertialSample)[] = [];
  async function call(path: string, method: string, body?: string) {
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await request(path, { method, body, signal: controller.signal,
        credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json' } });
      if (!response.ok) {
        const failure = await response.json().catch(() => null);
        throw new SessionError(typeof failure?.message === 'string' ? failure.message
          : `惯性服务请求失败（${response.status}）`, response.status === 503);
      }
      const envelope = await response.json();
      if (envelope?.status !== 'ok') throw new SessionError(envelope?.message || '惯性服务未授权或返回错误');
      return envelope.data;
    } catch (error) {
      if (error instanceof SessionError) throw error;
      throw new SessionError('惯性服务连接失败', true);
    } finally { clearTimeout(deadline); }
  }
  async function close(sessionId: string) {
    try { await call(`${base}/${encodeURIComponent(sessionId)}`, 'DELETE'); }
    catch { /* The server also expires abandoned sessions after 120 seconds. */ }
  }
  function stop() {
    stopped = true; queue.length = 0; clearTimeout(timer);
    // Close after any in-flight batch: the server serializes engine mutation.
    if (id && !busy) { const closing = id; id = undefined; void close(closing); }
  }
  function fail(error: unknown) {
    if (stopped) return;
    stop(); onError(error instanceof Error ? error.message : '惯性会话失败');
  }
  async function drain() {
    if (busy || stopped || !id || !queue.length) return;
    busy = true;
    const batch = queue.splice(0, 100);
    const body = JSON.stringify({ sequence, samples: batch });
    try {
      let response;
      try { response = await call(`${base}/${encodeURIComponent(id)}`, 'POST', body); }
      catch (error) {
        if (stopped || !(error instanceof SessionError) || !error.retryable) throw error;
        // Reuse the identical sequence and bytes after ambiguous delivery.
        response = await call(`${base}/${encodeURIComponent(id)}`, 'POST', body);
      }
      if (stopped) return;
      const last = batch[batch.length - 1];
      const timestamp = 'elapsed' in last ? Math.floor(last.elapsed) + 1 : last.timestamp;
      if (response?.sequence !== sequence || response?.result?.accepted !== batch.length
          || response?.result?.timestamp !== timestamp
          || !validResult(response.result)) {
        throw new SessionError('惯性服务批次确认不匹配');
      }
      sequence++;
      onResult(response.result);
    } catch (error) { fail(error); }
    finally {
      busy = false;
      if (stopped && id) { const closing = id; id = undefined; void close(closing); }
      else if (queue.length) schedule();
    }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(() => { void drain(); }, 200); }
  async function start() {
    if (started || stopped) return false;
    started = true;
    try {
      const created = await call(base, 'POST', JSON.stringify({ format }));
      if (typeof created?.id !== 'string' || !created.id || created.nextSequence !== 0) {
        throw new SessionError('惯性服务会话响应无效');
      }
      if (stopped) { void close(created.id); return false; }
      id = created.id;
      if ((created.format ?? 'native') !== format) throw new SessionError('惯性服务输入协议不匹配');
      return true;
    } catch (error) { fail(error); return false; }
  }
  function push(sample: InertialSample | BrowserInertialSample) {
    if (stopped || !id) return false;
    if (('elapsed' in sample) !== (format === 'browser')) {
      fail(new SessionError('惯性样本协议不匹配')); return false;
    }
    if (queue.length >= 250) { fail(new SessionError('惯性数据发送积压，已停止会话')); return false; }
    queue.push('elapsed' in sample
      ? { ...sample, angularVelocity: [...sample.angularVelocity], acceleration: [...sample.acceleration],
          ...(sample.gps ? { gps: { ...sample.gps } } : {}) }
      : { ...sample, gyro: [...sample.gyro], acceleration: [...sample.acceleration],
          ...(sample.gps ? { gps: { ...sample.gps } } : {}) });
    if (!busy && queue.length === 1) schedule();
    return true;
  }
  return { start, push, stop };
}
