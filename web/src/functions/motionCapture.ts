/** Browser device coordinates, not yet the Amap native installation frame.
 * W3C Device Motion: acceleration includes gravity (m/s²); beta/gamma/alpha
 * are rates around x/y/z, reported in degrees/s.
 */
export type MotionSample = {
  timestamp: number;
  elapsed: number;
  acceleration: [number, number, number];
  angularVelocity: [number, number, number];
  interval: number | null;
};
export type MotionGpsFix = {
  timestamp: number; longitude: number; latitude: number; accuracy: number;
  altitude: number | null; altitudeAccuracy: number | null;
  speed: number | null; heading: number | null;
};
export type MotionState = {
  status: 'idle' | 'permission' | 'waiting' | 'receiving' | 'unavailable' | 'denied' | 'stopped';
  message: string;
  count: number;
  incomplete: number;
  hz: number;
  latest: MotionSample | null;
};
export const initialMotionState = (): MotionState => ({
  status: 'idle', message: '尚未开始采集', count: 0, incomplete: 0, hz: 0, latest: null,
});
const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

export function readMotionSample(event: DeviceMotionEvent, elapsed: number, epoch: number): MotionSample | null {
  const a = event.accelerationIncludingGravity, r = event.rotationRate;
  if (!a || !r || !finite(a.x) || !finite(a.y) || !finite(a.z) ||
      !finite(r.beta) || !finite(r.gamma) || !finite(r.alpha)) return null;
  return { timestamp: epoch + elapsed, elapsed,
    acceleration: [a.x, a.y, a.z],
    angularVelocity: [r.beta, r.gamma, r.alpha].map(v => v * Math.PI / 180) as [number, number, number],
    interval: finite(event.interval) && event.interval > 0 ? event.interval : null };
}

export function createMotionCapture(state: MotionState, onSample?: (sample: MotionSample) => void) {
  let generation = 0, listening = false, timer: ReturnType<typeof setTimeout> | undefined;
  let epoch = 0, started = 0, first = 0, last = -1;
  const samples: MotionSample[] = [];
  const fixes: (MotionGpsFix & { elapsed: number })[] = [];
  function recordGps(fix: MotionGpsFix) {
    if (!listening || ![fix.timestamp, fix.longitude, fix.latitude, fix.accuracy].every(finite)
      || Math.abs(fix.longitude) > 180 || Math.abs(fix.latitude) > 90 || fix.accuracy < 0) return;
    for (const value of [fix.altitude, fix.altitudeAccuracy, fix.speed, fix.heading]) {
      if (value !== null && !finite(value)) return;
    }
    fixes.push({ timestamp: fix.timestamp, longitude: fix.longitude, latitude: fix.latitude,
      accuracy: fix.accuracy, altitude: fix.altitude, altitudeAccuracy: fix.altitudeAccuracy,
      speed: fix.speed, heading: fix.heading, elapsed: performance.now() - started });
    if (fixes.length > 3000) fixes.shift();
    return fixes.length;
  }
  function clean() {
    window.removeEventListener('devicemotion', receive);
    document.removeEventListener('visibilitychange', visibility);
    clearTimeout(timer); listening = false;
  }
  function stop() {
    generation++; clean();
    state.status = 'stopped'; state.message = '采集已停止';
  }
  function visibility() { if (document.hidden) stop(); }
  function armTimeout() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.status = 'unavailable';
      state.message = '未收到完整加速度和角速度；接口存在不代表车机提供传感器数据';
      state.hz = 0;
    }, 5000);
  }
  function receive(event: DeviceMotionEvent) {
    if (!listening) return;
    const elapsed = performance.now() - started;
    const sample = readMotionSample(event, elapsed, epoch);
    if (!sample) { state.incomplete++; return; }
    if (elapsed <= last) return;
    last = elapsed;
    if (!state.count) first = elapsed;
    state.count++;
    state.hz = elapsed > first ? (state.count - 1) * 1000 / (elapsed - first) : 0;
    state.latest = sample;
    state.status = 'receiving'; state.message = '正在接收完整传感器数据';
    samples.push(sample);
    if (samples.length > 3000) samples.shift();
    armTimeout(); onSample?.(sample);
  }
  async function start() {
    const id = ++generation; clean(); samples.length = 0; fixes.length = 0;
    Object.assign(state, initialMotionState());
    if (!window.isSecureContext || typeof window.DeviceMotionEvent === 'undefined') {
      state.status = 'unavailable'; state.message = '需要 HTTPS 或本机安全环境，并且浏览器支持运动传感器接口'; return;
    }
    const api = window.DeviceMotionEvent as typeof DeviceMotionEvent & { requestPermission?: () => Promise<string> };
    state.status = 'permission'; state.message = '正在请求运动传感器权限';
    try {
      const permission = api.requestPermission ? await api.requestPermission() : 'granted';
      if (id !== generation) return;
      if (permission !== 'granted') { state.status = 'denied'; state.message = '运动传感器权限未授予'; return; }
      if (document.hidden) { stop(); return; }
      started = performance.now(); epoch = Date.now(); first = 0; last = -1;
      listening = true;
      window.addEventListener('devicemotion', receive);
      document.addEventListener('visibilitychange', visibility);
      state.status = 'waiting'; state.message = '等待加速度和角速度，最长观察 5 秒';
      armTimeout();
    } catch {
      if (id !== generation) return;
      state.status = 'denied'; state.message = '无法获取运动传感器权限';
    }
  }
  function recording() {
    return { schema: 'tmc-browser-motion-v2', frame: 'device',
      accelerationUnit: 'm/s2', angularVelocityUnit: 'rad/s',
      timeSource: 'monotonic-receipt', epochAtStart: epoch,
      gps: { coordinateSource: 'browser-unconverted', headingUnit: 'degrees-clockwise-from-north',
        speedUnit: 'm/s', fixes: fixes.map(fix => ({ ...fix })) },
      samples: samples.map(s => ({ ...s,
        acceleration: [...s.acceleration], angularVelocity: [...s.angularVelocity] })) };
  }
  return { start, stop, recording, recordGps,
    elapsedNow: () => listening ? performance.now() - started : null };
}
